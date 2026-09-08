"""Pass 2: count, for every month and cell, the days whose FWI exceeds local thresholds.

The accumulator mutates its internal counters on purpose: it is the one place in the
pipeline where an in-place update is required to stay within memory (one uint8 per
cell, month and threshold instead of one float per cell and day).
"""

from __future__ import annotations

import calendar

import numpy as np


def days_in_months(year: int) -> np.ndarray:
    return np.array([calendar.monthrange(year, m)[1] for m in range(1, 13)], dtype=np.int64)


class MonthlyExceedance:
    def __init__(self, year: int, thresholds: dict[str, np.ndarray], shape: tuple[int, int]):
        self.year = int(year)
        self.shape = tuple(int(s) for s in shape)
        if not thresholds:
            raise ValueError("at least one threshold is required")
        # NaN thresholds become +inf so that "fwi > threshold" is never true there
        self._thresholds = {}
        for name, thr in thresholds.items():
            arr = np.asarray(thr, dtype=np.float32)
            if arr.shape != self.shape:
                raise ValueError(f"threshold {name!r} has shape {arr.shape}, expected {self.shape}")
            self._thresholds[name] = np.where(np.isnan(arr), np.inf, arr).astype(np.float32)
        self._counts = {name: np.zeros((12, *self.shape), dtype=np.uint8) for name in thresholds}
        self._expected = days_in_months(self.year)
        self._seen = np.zeros(int(self._expected.sum()), dtype=bool)
        self.days_seen = np.zeros(12, dtype=np.int64)
        self._jan1 = np.datetime64(f"{self.year}-01-01", "D")

    def add_day(self, date: np.datetime64, slab: np.ndarray) -> None:
        d = np.datetime64(date, "D")
        doy = int((d - self._jan1).astype(np.int64))
        if doy < 0 or doy >= self._seen.size:
            raise ValueError(f"{d} does not belong to year {self.year}")
        if self._seen[doy]:
            raise ValueError(f"{d} was already added")
        x = np.asarray(slab, dtype=np.float32)
        if x.shape != self.shape:
            raise ValueError(f"slab has shape {x.shape}, expected {self.shape}")
        month = int(d.astype("datetime64[M]").astype(np.int64) % 12)
        with np.errstate(invalid="ignore"):
            for name, thr in self._thresholds.items():
                self._counts[name][month] += (x > thr).astype(np.uint8)
        self._seen[doy] = True
        self.days_seen[month] += 1

    def is_complete(self) -> bool:
        return bool(self._seen.all())

    def missing_days(self) -> list[str]:
        """Calendar days of the year that were never added, as ISO strings."""
        idx = np.flatnonzero(~self._seen)
        return [str(self._jan1 + int(i)) for i in idx]

    def _first_gap(self) -> int | None:
        """Index of the first day missing *between* two days that were added.

        A run that stops early is a known dataset shape: the Dryad FWI files carry 365
        steps every year, so a leap year legitimately ends on 30 December. A hole
        between two observed days is different, and always means a damaged input.
        """
        seen = np.flatnonzero(self._seen)
        if seen.size < 2:
            return None
        inside = np.arange(seen[0], seen[-1] + 1)
        missing = inside[~self._seen[inside]]
        return int(missing[0]) if missing.size else None

    def result(self, require_complete: bool = False) -> dict[str, np.ndarray]:
        gap = self._first_gap()
        if gap is not None:
            raise ValueError(
                f"year {self.year} has a hole at {self._jan1 + gap} inside its data; "
                "the file is damaged or was read out of order"
            )
        if require_complete and not self.is_complete():
            missing = self.missing_days()
            raise ValueError(
                f"year {self.year} stops early: {len(missing)} day(s) missing, "
                f"first {missing[0]} (pass allow_incomplete=True if the source ships "
                "fewer steps than the calendar has days)"
            )
        return {name: counts.copy() for name, counts in self._counts.items()}
