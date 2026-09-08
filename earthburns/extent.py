"""Daily "how much of the burnable world is in extreme fire weather" statistics.

Two things make this module less obvious than it looks.

*Area weighting* — on a regular lat/lon grid a cell at 60 degrees covers half the
surface of one at the equator, so every fraction is weighted by cos(latitude).

*Coverage* — a cell whose FWI is missing that day cannot exceed anything. Dividing
by the whole burnable area would then make the fraction shrink when data is missing
rather than when the weather calms down. We therefore report both denominators:
``fraction`` over the whole burnable area (the definition used in the literature)
and ``fraction_observed`` over the area that actually had data, plus the
``coverage`` needed to tell the two apart.

All day-invariant quantities live in :class:`ExtentContext`, built once per run.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ExtentStats:
    """One day, one threshold. Fractions are NaN when the denominator is zero."""

    fraction: float
    fraction_observed: float
    coverage: float
    region_fraction: np.ndarray
    region_fraction_observed: np.ndarray
    region_coverage: np.ndarray


class ExtentContext:
    """Burnable cells gathered once, with their areas, regions and denominators.

    Working on the ~185k burnable cells instead of the 1.04M grid cells is what
    keeps the daily loop cheap; the results are identical because every statistic
    is already zero-weighted outside the mask.
    """

    def __init__(
        self,
        burnable: np.ndarray,
        weights: np.ndarray,
        regions: np.ndarray,
        region_ids: Sequence[int],
    ) -> None:
        burn = np.asarray(burnable, dtype=bool)
        reg = np.asarray(regions)
        if reg.shape != burn.shape:
            raise ValueError(f"regions shape {reg.shape} does not match mask {burn.shape}")
        area_grid = np.broadcast_to(np.asarray(weights, dtype=np.float64), burn.shape)

        self.shape = burn.shape
        self.cells = np.flatnonzero(burn.ravel())
        self.area = np.ascontiguousarray(area_grid.ravel()[self.cells])
        self.region = np.ascontiguousarray(reg.ravel()[self.cells].astype(np.int64))
        self.region_ids = tuple(int(r) for r in region_ids)
        if any(r < 0 for r in self.region_ids):
            raise ValueError("region ids must be non-negative")

        self._ids = np.asarray(self.region_ids, dtype=np.int64)
        # minlength must cover the requested ids, not only those present on the grid,
        # otherwise a region absent from the mask would raise IndexError below.
        self._nbins = int(max(self.region.max(initial=-1), self._ids.max(initial=-1))) + 1
        self.total_area = float(self.area.sum())
        self.region_area = self._bincount(self.area)[self._ids]

    def _bincount(self, values: np.ndarray) -> np.ndarray:
        return np.bincount(self.region, weights=values, minlength=self._nbins)

    def gather(self, grid: np.ndarray) -> np.ndarray:
        """Values of ``grid`` at the burnable cells, in cell order."""
        arr = np.asarray(grid)
        if arr.shape != self.shape:
            raise ValueError(f"expected shape {self.shape}, got {arr.shape}")
        return arr.ravel()[self.cells]


def _ratio(num: np.ndarray | float, den: np.ndarray | float) -> np.ndarray | float:
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(np.asarray(den) > 0.0, np.asarray(num) / np.asarray(den), np.nan)


def daily_extent(
    fwi_cells: np.ndarray, threshold_cells: np.ndarray, ctx: ExtentContext
) -> ExtentStats:
    """Statistics for one day and one threshold, from values already gathered.

    ``fwi_cells`` and ``threshold_cells`` hold one value per burnable cell. A cell
    whose FWI is not finite counts neither as exceeding nor as observed.
    """
    x = np.asarray(fwi_cells)
    thr = np.asarray(threshold_cells)
    if x.shape != ctx.area.shape or thr.shape != ctx.area.shape:
        raise ValueError(f"expected {ctx.area.size} values per array")
    observed = np.isfinite(x)
    with np.errstate(invalid="ignore"):
        hit = observed & (x > thr)

    obs_area = ctx.area * observed
    hit_area = ctx.area * hit
    region_obs = ctx._bincount(obs_area)[ctx._ids]
    region_hit = ctx._bincount(hit_area)[ctx._ids]
    total_obs = float(obs_area.sum())
    total_hit = float(hit_area.sum())

    return ExtentStats(
        fraction=float(_ratio(total_hit, ctx.total_area)),
        fraction_observed=float(_ratio(total_hit, total_obs)),
        coverage=float(_ratio(total_obs, ctx.total_area)),
        region_fraction=np.asarray(_ratio(region_hit, ctx.region_area), dtype=np.float64),
        region_fraction_observed=np.asarray(_ratio(region_hit, region_obs), dtype=np.float64),
        region_coverage=np.asarray(_ratio(region_obs, ctx.region_area), dtype=np.float64),
    )
