"""Burnable-wildland mask (GLDAS classes) and regridding of cell grids onto ERA5 nodes.

GLDAS and GFED grids are *cell-centred* (centres at ±0.125, ±0.375, …) while the ERA5
FWI grid is *node-centred* (nodes at multiples of 0.25). Every ERA5 node therefore sits
exactly at the corner of four source cells. For a boolean mask we take a vote of those
four cells; for categorical ids we take the north-west cell (deterministic).
"""

from __future__ import annotations

import numpy as np

GLDAS_CLASS_NAMES: dict[int, str] = {
    0: "Missing value / water",
    1: "Evergreen Needleleaf Forest",
    2: "Evergreen Broadleaf Forest",
    3: "Deciduous Needleleaf Forest",
    4: "Deciduous Broadleaf Forest",
    5: "Mixed Forest",
    6: "Closed Shrublands",
    7: "Open Shrublands",
    8: "Woody Savannas",
    9: "Savannas",
    10: "Grassland",
    11: "Permanent Wetland",
    12: "Cropland",
    13: "Urban and Built-Up",
    14: "Cropland/Natural Vegetation Mosaic",
    15: "Snow and Ice",
    16: "Barren or Sparsely Vegetated",
    17: "Ocean",
    18: "Wooded Tundra",
    19: "Mixed Tundra",
    20: "Bare Ground Tundra",
}
BURNABLE_CLASSES_DEFAULT = frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14, 18, 19})
_EPS = 1e-6


def burnable_from_classes(classes: np.ndarray, burnable: frozenset[int]) -> np.ndarray:
    """Boolean mask: True where the class code belongs to the burnable set."""
    return np.isin(np.asarray(classes), np.fromiter(burnable, dtype=np.int64))


def _axis_neighbours(
    src: np.ndarray, target: np.ndarray, periodic: bool
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each target coordinate, the two nearest source cells along one axis.

    Returns (idx, in_window, in_extent), each of shape (2, ntarget). ``src`` must be
    ascending and regularly spaced. A candidate is "in window" when it lies within half
    a step of the target, and "in extent" when its index exists in the source array.
    """
    src = np.asarray(src, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    step = float(np.median(np.diff(src)))
    if step <= 0:
        raise ValueError("source coordinates must be ascending")
    pos = (target - src[0]) / step
    j_lo = np.floor(pos - 0.5 + _EPS).astype(np.int64)
    idx = np.stack([j_lo, j_lo + 1])
    n = src.size
    if periodic:
        in_extent = np.ones_like(idx, dtype=bool)
        centres = src[0] + idx * step
        dist = np.abs(((centres - target[None, :]) + 180.0) % 360.0 - 180.0)
        idx = idx % n
    else:
        in_extent = (idx >= 0) & (idx < n)
        centres = src[0] + idx * step
        dist = np.abs(centres - target[None, :])
        idx = np.clip(idx, 0, n - 1)
    in_window = dist <= step / 2 + _EPS
    return idx, in_window, in_extent


def _prepare(src: np.ndarray, src_lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Flip rows so that source latitudes are ascending (required by _axis_neighbours)."""
    src_lat = np.asarray(src_lat, dtype=np.float64)
    if src_lat[0] > src_lat[-1]:
        return np.asarray(src)[::-1], src_lat[::-1]
    return np.asarray(src), src_lat


def _neighbour_fraction(
    src: np.ndarray, src_lat, src_lon, tgt_lat, tgt_lon
) -> tuple[np.ndarray, np.ndarray]:
    src, src_lat = _prepare(src, src_lat)
    li, lw, le = _axis_neighbours(src_lat, tgt_lat, periodic=False)
    oi, ow, oe = _axis_neighbours(np.asarray(src_lon, dtype=np.float64), tgt_lon, periodic=True)
    num = np.zeros((len(tgt_lat), len(tgt_lon)), dtype=np.float64)
    den = np.zeros_like(num)
    for a in range(2):
        for b in range(2):
            window = lw[a][:, None] & ow[b][None, :]
            usable = window & le[a][:, None] & oe[b][None, :]
            vals = src[li[a][:, None], oi[b][None, :]].astype(np.float64)
            num += np.where(usable, vals, 0.0)
            den += window
    return num, den


def vote_regrid_to_nodes(
    src: np.ndarray, src_lat, src_lon, tgt_lat, tgt_lon, threshold: float = 0.5
) -> np.ndarray:
    """Boolean regrid: node is True when >= ``threshold`` of its neighbouring cells are True.

    Cells outside the source extent count as False, so the result is conservative.
    """
    num, den = _neighbour_fraction(np.asarray(src, dtype=bool), src_lat, src_lon, tgt_lat, tgt_lon)
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(den > 0, num / np.maximum(den, 1), 0.0)
    return frac >= threshold


def nearest_nw_regrid_to_nodes(
    src: np.ndarray, src_lat, src_lon, tgt_lat, tgt_lon, fill: int = 0
) -> np.ndarray:
    """Categorical regrid: take the north-west neighbouring cell of each node."""
    src, src_lat = _prepare(src, src_lat)
    li, lw, le = _axis_neighbours(src_lat, tgt_lat, periodic=False)
    oi, ow, oe = _axis_neighbours(np.asarray(src_lon, dtype=np.float64), tgt_lon, periodic=True)
    north = 1  # ascending latitude -> index 1 is the northern candidate
    west = 0
    ok = (lw[north] & le[north])[:, None] & (ow[west] & oe[west])[None, :]
    vals = src[li[north][:, None], oi[west][None, :]]
    return np.where(ok, vals, np.asarray(fill, dtype=vals.dtype))
