"""Streaming per-cell histograms: estimate local percentiles in a single pass.

Computing an exact 90th percentile per grid cell over 30 years of daily data would
require holding ~11,000 values for each of the ~1 million cells in memory (45 GB) or
re-reading the files many times. Instead we keep, for every cell, a histogram of its
daily FWI values over fixed bin edges. The bin containing the requested rank is found
from the cumulative counts and the value is interpolated linearly inside that bin, so
the estimation error is bounded by the bin width (0.2 FWI units in the fine range).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

MAX_SAMPLES = np.iinfo(np.uint16).max


def make_edges(
    fine_max: float = 80.0,
    fine_step: float = 0.2,
    coarse_max: float = 200.0,
    coarse_step: float = 1.0,
) -> np.ndarray:
    """Bin edges: fine bins on [0, fine_max), coarse bins on [fine_max, coarse_max),
    then a single overflow bin [coarse_max, inf)."""
    if not (fine_step > 0 and coarse_step > 0 and 0 < fine_max < coarse_max):
        raise ValueError("need positive steps and 0 < fine_max < coarse_max")
    n_fine = int(round(fine_max / fine_step))
    n_coarse = int(round((coarse_max - fine_max) / coarse_step))
    fine = np.arange(n_fine) * fine_step
    coarse = fine_max + np.arange(n_coarse) * coarse_step
    return np.concatenate([fine, coarse, [coarse_max, np.inf]]).astype(np.float64)


class StreamingHistogram:
    """Per-cell histogram accumulated one slab at a time.

    Counts are stored as uint16 (max 65,535 samples per cell), which keeps the
    memory footprint at ~1 GB for 521 bins x 1,038,240 cells.
    """

    def __init__(self, edges: np.ndarray, ncells: int) -> None:
        self.edges = np.asarray(edges, dtype=np.float64)
        if self.edges.ndim != 1 or self.edges.size < 3 or np.any(np.diff(self.edges) <= 0):
            raise ValueError("edges must be a strictly increasing 1-D array")
        self.ncells = int(ncells)
        self.nbins = self.edges.size - 1
        self._counts = np.zeros((self.nbins, self.ncells), dtype=np.uint16)
        self._n_updates = 0

    @classmethod
    def from_counts(cls, edges: np.ndarray, counts: np.ndarray) -> StreamingHistogram:
        """Restore an accumulator from a saved count matrix.

        The counts are validated and copied in C order: ``update`` relies on
        ``reshape(-1)`` returning a view, and a Fortran-ordered or transposed input
        would make it a temporary copy, so every later sample would be discarded
        without a word.
        """
        arr = np.asarray(counts)
        h = cls(edges, arr.shape[1] if arr.ndim == 2 else 0)
        if arr.shape != h._counts.shape:
            raise ValueError(f"counts shape {arr.shape} does not match {h._counts.shape}")
        if not np.issubdtype(arr.dtype, np.integer):
            raise ValueError(f"counts must be an integer array, got {arr.dtype}")
        if arr.min(initial=0) < 0 or arr.max(initial=0) > MAX_SAMPLES:
            raise ValueError(f"counts must lie in [0, {MAX_SAMPLES}]")
        totals = arr.sum(axis=0, dtype=np.int64)
        if totals.size and int(totals.max()) > MAX_SAMPLES:
            raise ValueError(f"a cell holds more than {MAX_SAMPLES} samples")
        h._counts = np.ascontiguousarray(arr, dtype=np.uint16)
        h._n_updates = int(totals.max()) if totals.size else 0
        return h

    def update(self, values: np.ndarray) -> None:
        """Add one sample per cell (NaN / inf samples are skipped)."""
        x = np.asarray(values, dtype=np.float32).reshape(-1)
        if x.size != self.ncells:
            raise ValueError(f"expected {self.ncells} values, got {x.size}")
        if self._n_updates >= MAX_SAMPLES:
            raise OverflowError("uint16 histogram counts would overflow")
        finite = np.isfinite(x)
        cells = np.flatnonzero(finite)
        idx = np.searchsorted(self.edges, x[finite], side="right") - 1
        idx = np.clip(idx, 0, self.nbins - 1).astype(np.int64)
        # each cell appears at most once per update, so fancy-index += is exact
        self._counts.reshape(-1)[idx * self.ncells + cells] += 1
        self._n_updates += 1

    @property
    def count(self) -> np.ndarray:
        return self._counts.sum(axis=0, dtype=np.int64)

    def counts_matrix(self) -> np.ndarray:
        return self._counts.copy()

    def overflow_cells(self) -> np.ndarray:
        """Cells with at least one sample in the overflow bin [coarse_max, inf)."""
        return self._counts[-1] > 0

    def quantile(self, q: float) -> np.ndarray:
        return self.quantiles([q])[0]

    def quantiles(self, qs: Sequence[float], chunk: int = 65_536) -> np.ndarray:
        """Estimate several quantiles at once; returns shape (len(qs), ncells)."""
        qs_arr = np.asarray(qs, dtype=np.float64)
        if np.any((qs_arr <= 0) | (qs_arr >= 1)):
            raise ValueError("quantiles must lie strictly in (0, 1)")
        out = np.full((qs_arr.size, self.ncells), np.nan, dtype=np.float32)
        for start in range(0, self.ncells, chunk):
            sl = slice(start, min(start + chunk, self.ncells))
            out[:, sl] = self._quantiles_chunk(qs_arr, self._counts[:, sl])
        return out

    def _quantiles_chunk(self, qs: np.ndarray, counts: np.ndarray) -> np.ndarray:
        n = counts.sum(axis=0, dtype=np.int64)
        cs = np.cumsum(counts, axis=0, dtype=np.int64)
        m = counts.shape[1]
        result = np.full((qs.size, m), np.nan, dtype=np.float64)
        valid = n > 0
        if not valid.any():
            return result.astype(np.float32)
        for qi, q in enumerate(qs):
            # numpy "linear" definition: value between order statistics k and k+1
            r = q * (n - 1)
            k = np.floor(r)
            g = r - k
            lo = self._order_statistic(k, counts, cs)
            hi = self._order_statistic(np.minimum(k + 1, n - 1), counts, cs)
            result[qi] = np.where(valid, lo + g * (hi - lo), np.nan)
        return result.astype(np.float32)

    def _order_statistic(self, k: np.ndarray, counts: np.ndarray, cs: np.ndarray) -> np.ndarray:
        """Approximate the k-th smallest value (0-based) of every cell."""
        m = counts.shape[1]
        cols = np.arange(m)
        k_int = np.clip(k, 0, None).astype(np.int64)
        b = (cs <= k_int[None, :]).sum(axis=0)
        b = np.clip(b, 0, self.nbins - 1)
        before = np.where(b > 0, cs[np.maximum(b - 1, 0), cols], 0)
        in_bin = counts[b, cols].astype(np.float64)
        frac = np.where(in_bin > 0, (k_int - before + 0.5) / np.maximum(in_bin, 1), 0.5)
        widths = np.diff(self.edges)
        widths = np.where(np.isinf(widths), 0.0, widths)
        return self.edges[b] + frac * widths[b]
