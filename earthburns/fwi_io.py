"""Read yearly FWI NetCDF files lazily and serve them day by day on the canonical grid."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import xarray as xr

from earthburns.grid import to_canonical

FWI_NAME_CANDIDATES = ("fwi", "FWI", "fwi_era5", "fwinx", "fire_weather_index")
TIME_NAMES = ("time", "Time", "TIME", "t")
_YEAR_IN_NAME = re.compile(r"(19|20)\d{2}")
# "days since 1900-01-01" (CF) and the malformed "days_since_Jan11900" shipped by Dryad.
_CF_SINCE = re.compile(r"^\s*days?\s+since\s+(\d{4})-(\d{1,2})-(\d{1,2})", re.I)
_TERSE_SINCE = re.compile(r"^\s*days?_since_([A-Za-z]{3})(\d{1,2})(\d{4})\s*$", re.I)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
)}


def find_fwi_variable(ds: xr.Dataset, allow_unnamed: bool = False) -> str:
    """Name of the FWI variable in ``ds``.

    Only a known FWI name is accepted by default. Falling back to "the only 3-D
    variable" would happily stream a fine-fuel-moisture or drought-code field as
    if it were the Fire Weather Index and produce plausible but wrong thresholds,
    so that fallback has to be asked for explicitly.
    """
    for name in FWI_NAME_CANDIDATES:
        if name in ds.data_vars:
            return name
    three_d = [v for v in ds.data_vars if ds[v].ndim == 3]
    if allow_unnamed and len(three_d) == 1:
        return three_d[0]
    raise ValueError(
        f"no FWI variable among {list(ds.data_vars)}; expected one of {FWI_NAME_CANDIDATES}"
        + (f" (3-D candidates: {three_d})" if three_d else "")
    )


def year_from_filename(path: Path) -> int | None:
    m = _YEAR_IN_NAME.search(Path(path).name)
    return int(m.group(0)) if m else None


def epoch_from_units(units: str) -> np.datetime64 | None:
    """Origin of a "days since <date>" unit string, or None if it is not one.

    Accepts the CF spelling and the terse ``days_since_Jan11900`` used by the Dryad
    FWI files, which no CF decoder recognises (xarray leaves the axis numeric).
    """
    if m := _CF_SINCE.match(units or ""):
        y, mo, d = (int(g) for g in m.groups())
        return np.datetime64(f"{y:04d}-{mo:02d}-{d:02d}", "D")
    if m := _TERSE_SINCE.match(units or ""):
        mon, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        if mon in _MONTHS:
            return np.datetime64(f"{year:04d}-{_MONTHS[mon]:02d}-{day:02d}", "D")
    return None


def find_day_offsets(ds: xr.Dataset, time_dim: str) -> tuple[np.ndarray, np.datetime64] | None:
    """A 1-D companion variable holding day offsets from an epoch, if the file has one."""
    for name in ds.variables:
        var = ds[name]
        if var.dims != (time_dim,) or not np.issubdtype(var.dtype, np.number):
            continue
        epoch = epoch_from_units(str(var.attrs.get("units", "")))
        if epoch is not None:
            return np.rint(np.asarray(var.values, dtype=np.float64)).astype(np.int64), epoch
    return None


def _as_day(value: object) -> np.datetime64:
    try:
        return np.datetime64(value, "D")  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return np.datetime64(str(value)[:10], "D")  # cftime and friends


def _datetime_axis(
    da: xr.DataArray, year: int | None, name: str, offsets: tuple[np.ndarray, np.datetime64] | None
) -> np.ndarray:
    """Return the time axis as datetime64[D].

    Three shapes occur in practice: a decoded datetime axis, a companion variable of
    day offsets from an epoch (the Dryad files, whose unit string no CF decoder
    accepts), and a bare day-of-year index anchored on the file's year (GEFF-ERA5).
    """
    if offsets is not None:
        values, epoch = offsets
        if values.size != da.sizes["time"]:
            raise ValueError(f"{name}: {values.size} day offsets for {da.sizes['time']} steps")
        return epoch + values.astype("timedelta64[D]")

    t = da["time"].values if "time" in da.coords else None
    if t is None:
        raise ValueError(f"{name}: the time dimension carries neither dates nor day offsets")
    if np.issubdtype(t.dtype, np.datetime64):
        return t.astype("datetime64[D]")
    if t.dtype == object:
        return np.array([_as_day(v) for v in t], dtype="datetime64[D]")
    if year is None:
        raise ValueError(f"{name}: numeric time axis and no year to anchor it on")
    doy = np.rint(np.asarray(t, dtype=np.float64)).astype(np.int64)
    if np.any(doy < 1) or np.any(doy > 366) or np.any(np.diff(doy) != 1):
        raise ValueError(f"{name}: numeric time axis is not a contiguous day-of-year index")
    return np.datetime64(f"{year}-01-01", "D") + (doy - 1).astype("timedelta64[D]")


def _check_axis(dates: np.ndarray, name: str) -> None:
    """Days must be strictly consecutive: a gap or a repeat means a damaged file."""
    if dates.size == 0:
        raise ValueError(f"{name}: empty time axis")
    steps = np.diff(dates.astype("datetime64[D]")).astype(np.int64)
    if steps.size and not np.all(steps == 1):
        bad = int(np.flatnonzero(steps != 1)[0])
        raise ValueError(
            f"{name}: time axis jumps from {dates[bad]} to {dates[bad + 1]}, expected one day"
        )


def _open_dataset(path: Path) -> xr.Dataset:
    """Open a file whose time units may not be CF-compliant.

    The Dryad FWI files label their day counter ``days_since_Jan11900``, which makes
    xarray's decoder raise before the file even opens. Falling back to an undecoded
    open lets ``find_day_offsets`` interpret it, and costs nothing for correct files.
    """
    try:
        return xr.open_dataset(path, cache=False)
    except ValueError as exc:
        if "decode time units" not in str(exc) and "invalid time units" not in str(exc):
            raise
        return xr.open_dataset(path, cache=False, decode_times=False)


@contextmanager
def open_fwi_year(
    path: Path, year: int | None = None, allow_unnamed: bool = False
) -> Iterator[xr.DataArray]:
    """Yield a lazy (time, lat, lon) float32 array aligned on the canonical grid.

    ``year`` anchors numeric day-of-year time axes; defaults to the year in the file name.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    anchor = year if year is not None else year_from_filename(path)
    with _open_dataset(path) as ds:
        da = to_canonical(ds[find_fwi_variable(ds, allow_unnamed=allow_unnamed)])
        time_dim = next((d for d in TIME_NAMES if d in da.dims), None)
        if time_dim is None:
            raise ValueError(f"{path.name}: FWI variable has no time dimension ({da.dims})")
        offsets = find_day_offsets(ds, time_dim)
        da = da.rename({time_dim: "time"}) if time_dim != "time" else da
        dates = _datetime_axis(da, anchor, path.name, offsets)
        _check_axis(dates, path.name)
        yield da.assign_coords(time=dates).transpose("time", "lat", "lon")


def preferred_block(da: xr.DataArray, minimum: int = 32) -> int:
    """A read size aligned on the file's own time chunking.

    The Dryad files are chunked 73 days deep, so reading 32-day blocks decompresses
    each chunk twice; asking for the file's chunk size halves the read time.
    """
    chunk = int(da.encoding.get("preferred_chunks", {}).get("time", 0) or 0)
    return max(chunk, minimum) if chunk else minimum


def iter_days(
    da: xr.DataArray, block_days: int | None = None
) -> Iterator[tuple[np.datetime64, np.ndarray]]:
    """Iterate (date, float32 slab) over the time axis, a block of days at a time.

    Reading blocks rather than single days avoids decompressing the same NetCDF chunk
    repeatedly. With no size given, the file's own chunking decides.
    """
    block_days = preferred_block(da) if block_days is None else block_days
    if block_days < 1:
        raise ValueError("block_days must be >= 1")
    times = da["time"].values.astype("datetime64[D]")
    for start in range(0, times.size, block_days):
        stop = min(start + block_days, times.size)
        block = np.array(da.isel(time=slice(start, stop)).values, dtype=np.float32, copy=True)
        # FWI is non-negative by construction: negative values are fill values (e.g. the
        # GEFF-ERA5 files code the ocean as -3.4e38 without a decodable _FillValue).
        block[block < 0.0] = np.nan
        for i in range(stop - start):
            yield times[start + i], block[i]
