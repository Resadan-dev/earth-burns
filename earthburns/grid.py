"""The canonical 0.25 degree ERA5 node grid and helpers to align inputs onto it.

Canonical orientation: latitude descending from +90 to -90 (721 rows), longitude
ascending from -180 to +179.75 (1440 columns). Every array produced by the pipeline
uses this orientation so that masks, thresholds and daily slabs line up cell by cell.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

N_LAT, N_LON = 721, 1440
STEP = 0.25
LAT_NAMES = ("lat", "latitude", "y")
LON_NAMES = ("lon", "longitude", "x")
_TOL = 1e-4


def canonical_grid() -> tuple[np.ndarray, np.ndarray]:
    """Return (lat, lon) 1-D coordinate arrays of the canonical grid."""
    lat = np.round(90.0 - STEP * np.arange(N_LAT), 6)
    lon = np.round(-180.0 + STEP * np.arange(N_LON), 6)
    return lat, lon


def cos_lat_weights(lat: np.ndarray) -> np.ndarray:
    """Relative cell area on a regular lat/lon grid, shape (nlat, 1), in [0, 1].

    On a regular grid the area of a cell is proportional to cos(latitude); this is
    the weight used for every "fraction of area" statistic in the pipeline.
    """
    w = np.cos(np.deg2rad(np.asarray(lat, dtype=np.float64)))
    return np.clip(w, 0.0, None)[:, None]


def _find_dim(da: xr.DataArray, candidates: tuple[str, ...], kind: str) -> str:
    """Case-insensitive lookup of a dimension name among ``candidates``."""
    by_lower = {str(d).lower(): str(d) for d in da.dims}
    for name in candidates:
        if name in by_lower:
            return by_lower[name]
    raise ValueError(f"no {kind} dimension among {da.dims}; expected one of {candidates}")


def to_canonical(da: xr.DataArray) -> xr.DataArray:
    """Rename, re-orient and validate a (…, lat, lon) array onto the canonical grid.

    Works lazily on file-backed arrays: only index permutations are applied.
    Raises ValueError if the input is not a 0.25 degree global node grid.
    """
    lat_dim = _find_dim(da, LAT_NAMES, "latitude")
    lon_dim = _find_dim(da, LON_NAMES, "longitude")
    out = da.rename({lat_dim: "lat", lon_dim: "lon"})

    if out.sizes["lat"] != N_LAT or out.sizes["lon"] != N_LON:
        raise ValueError(
            f"expected a {N_LAT}x{N_LON} grid, got {out.sizes['lat']}x{out.sizes['lon']}"
        )

    lat = out["lat"].values.astype(np.float64)
    if lat[0] < lat[-1]:
        out = out.isel(lat=slice(None, None, -1))

    lon = out["lon"].values.astype(np.float64)
    signed = ((lon + 180.0) % 360.0) - 180.0
    if not np.allclose(signed, lon):
        out = out.assign_coords(lon=np.round(signed, 6))
    if np.any(np.diff(out["lon"].values) < 0):
        out = out.sortby("lon")

    ref_lat, ref_lon = canonical_grid()
    if not np.allclose(out["lat"].values, ref_lat, atol=_TOL):
        raise ValueError("latitude coordinates do not match the canonical 0.25 degree grid")
    if not np.allclose(out["lon"].values, ref_lon, atol=_TOL):
        raise ValueError("longitude coordinates do not match the canonical 0.25 degree grid")

    return out.transpose(..., "lat", "lon")
