"""Pass 2: monthly exceedance counts and daily extent series for one world.

Both products come from a single read of each yearly file. Each year is written
to disk as soon as it is finished, counts and extent together, so that a failure
part-way through a 46-year run never leaves the two halves out of step.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from earthburns.extent import ExtentContext, daily_extent
from earthburns.fwi_io import iter_days, open_fwi_year
from earthburns.grid import canonical_grid
from earthburns.monthly import MonthlyExceedance

log = logging.getLogger(__name__)


def extent_columns(region_ids: Sequence[int]) -> list[str]:
    """Column order of the daily extent table.

    ``global`` and ``region_k`` are fractions of the whole burnable area;
    ``coverage`` and ``region_k_cov`` are the fractions of that area which had
    data. The fraction of *observed* area exceeding is the ratio of the two.
    """
    cols = ["global", "coverage"]
    for r in region_ids:
        cols += [f"region_{r}", f"region_{r}_cov"]
    return cols


def run_year(
    path: Path,
    year: int,
    thresholds: dict[str, np.ndarray],
    ctx: ExtentContext,
    require_complete: bool = True,
) -> tuple[dict[str, np.ndarray], pd.DataFrame, np.ndarray]:
    """Stream one yearly file.

    Returns the monthly counts per threshold, the daily extent rows, and how many days
    each month actually contributed, so a count is always readable against its own
    denominator rather than against an assumed 28 to 31.
    """
    acc = MonthlyExceedance(year=year, thresholds=thresholds, shape=ctx.shape)
    gathered = {name: ctx.gather(thr) for name, thr in thresholds.items()}
    cols = extent_columns(ctx.region_ids)
    rows: list[dict] = []
    with open_fwi_year(path, year=year) as da:
        for date, slab in iter_days(da):
            acc.add_day(date, slab)
            cells = ctx.gather(slab)
            stamp = pd.Timestamp(date)
            for name, thr_cells in gathered.items():
                s = daily_extent(cells, thr_cells, ctx)
                values = [s.fraction, s.coverage]
                for i in range(len(ctx.region_ids)):
                    values += [float(s.region_fraction[i]), float(s.region_coverage[i])]
                row = dict(zip(cols, values, strict=True))
                rows.append({"date": stamp, "threshold": name, **row})
    table = pd.DataFrame(rows, columns=["date", "threshold", *cols])
    return acc.result(require_complete=require_complete), table, acc.days_seen.copy()


def save_year(
    counts: dict[str, np.ndarray],
    extent: pd.DataFrame,
    days_seen: np.ndarray,
    year: int,
    out_dir: Path,
    prefix: str,
) -> tuple[Path, Path]:
    """Write one year's counts (NetCDF) and extent rows (Parquet) side by side."""
    lat, lon = canonical_grid()
    months = np.array([np.datetime64(f"{year}-{m:02d}-01", "D") for m in range(1, 13)])
    data = {f"days_gt_{name}": (("time", "lat", "lon"), arr) for name, arr in counts.items()}
    data["days_observed"] = (("time",), np.asarray(days_seen, dtype=np.int16))
    ds = xr.Dataset(
        data,
        coords={"time": months, "lat": lat, "lon": lon},
        attrs={"description": "Days per month with FWI above the local reference percentile"},
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    counts_path = out_dir / f"{prefix}_{year}.nc"
    extent_path = out_dir / f"{prefix}_{year}_extent.parquet"
    ds.to_netcdf(counts_path, encoding={v: {"zlib": True, "complevel": 4} for v in ds.data_vars})
    extent.to_parquet(extent_path, index=False)
    return counts_path, extent_path


def run_years(
    files: Sequence[tuple[int, Path]],
    thresholds: dict[str, np.ndarray],
    ctx: ExtentContext,
    out_dir: Path,
    prefix: str,
    progress: Callable[[str], None] = log.info,
    require_complete: bool = True,
) -> list[int]:
    """Process several years, writing each one as it completes; returns the years done."""
    done: list[int] = []
    for year, path in files:
        counts, extent, days_seen = run_year(
            path, year, thresholds, ctx, require_complete=require_complete
        )
        save_year(counts, extent, days_seen, year, out_dir, prefix)
        done.append(year)
        cov = float(extent["coverage"].mean()) if len(extent) else float("nan")
        n_days = int(days_seen.sum())
        progress(f"{prefix} {year}: {n_days} days, mean coverage {cov:.3f}")
    return done
