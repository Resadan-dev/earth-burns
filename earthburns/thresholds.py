"""Pass 1: local percentile thresholds of daily FWI over the reference period.

One streaming pass feeds every daily slab into a per-cell histogram. A random sample
of cells additionally keeps its full daily series so that the histogram estimate can be
checked against the exact percentile (see ``ValidationReport``).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import xarray as xr

from earthburns.config import HistogramConfig
from earthburns.fwi_io import iter_days, open_fwi_year
from earthburns.grid import N_LAT, N_LON, canonical_grid
from earthburns.histogram import StreamingHistogram, make_edges

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationReport:
    n_cells: int
    n_samples: int
    max_abs_error: tuple[float, ...]
    mean_abs_error: tuple[float, ...]
    p99_abs_error: tuple[float, ...]


@dataclass(frozen=True)
class Coverage:
    """What pass 1 actually streamed, so a short or mis-dated file cannot pass unseen."""

    n_days: int
    first_date: str
    last_date: str
    years: tuple[int, ...]
    missing_days: tuple[str, ...]


@dataclass(frozen=True)
class ThresholdResult:
    quantiles: tuple[float, ...]
    values: np.ndarray  # (nq, N_LAT, N_LON) float32
    count: np.ndarray  # (N_LAT, N_LON) int32 – finite samples per cell
    overflow: np.ndarray  # (N_LAT, N_LON) bool – saw values >= coarse_max
    files: tuple[str, ...]
    coverage: Coverage
    validation: ValidationReport | None


def quantile_name(q: float) -> str:
    return f"p{int(round(q * 100))}"


def _pick_validation_cells(first_slab: np.ndarray, n: int, seed: int) -> np.ndarray:
    finite = np.flatnonzero(np.isfinite(first_slab))
    if n <= 0 or finite.size == 0:
        return np.zeros(0, dtype=np.int64)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(finite, size=min(n, finite.size), replace=False))


def _validate(
    samples: np.ndarray, cells: np.ndarray, estimate: np.ndarray, quantiles: Sequence[float]
) -> ValidationReport:
    exact = np.nanpercentile(samples, [100.0 * q for q in quantiles], axis=0)
    err = np.abs(estimate[:, cells] - exact)
    ok = np.isfinite(err)
    stats = lambda f: tuple(float(f(err[i][ok[i]])) if ok[i].any() else float("nan")  # noqa: E731
                            for i in range(len(quantiles)))
    return ValidationReport(
        n_cells=int(cells.size),
        n_samples=int(samples.shape[0]),
        max_abs_error=stats(np.max),
        mean_abs_error=stats(np.mean),
        p99_abs_error=stats(lambda e: np.percentile(e, 99)),
    )


def _check_dates(seen: set[np.datetime64], allow_incomplete: bool) -> Coverage:
    """Validate the days streamed, year by year.

    Within a year the days must run without a break from 1 January. A year that stops
    early is tolerated and reported: the Dryad files carry 365 steps every year, so
    every leap year legitimately ends on 30 December. A break between two days that
    were both read means a damaged input and always raises.
    """
    days = np.array(sorted(seen), dtype="datetime64[D]")
    years = tuple(sorted({int(str(d)[:4]) for d in days}))
    missing: list[str] = []
    for y in years:
        start = np.datetime64(f"{y}-01-01", "D")
        calendar = np.arange(start, np.datetime64(f"{y + 1}-01-01", "D"))
        present = np.isin(calendar, days)
        absent = np.flatnonzero(~present)
        if absent.size == 0:
            continue
        last_present = int(np.flatnonzero(present)[-1]) if present.any() else -1
        interior = absent[absent < last_present]
        if interior.size:
            raise ValueError(
                f"{calendar[interior[0]]} is missing although later days of {y} were read; "
                "the input is damaged"
            )
        missing.extend(str(calendar[i]) for i in absent)

    cov = Coverage(
        n_days=int(days.size),
        first_date=str(days[0]),
        last_date=str(days[-1]),
        years=years,
        missing_days=tuple(missing),
    )
    if missing and not allow_incomplete:
        raise ValueError(
            f"the reference period stops short by {len(missing)} day(s), first {missing[0]} "
            "(pass allow_incomplete=True if the source ships fewer steps than the calendar)"
        )
    return cov


def compute_thresholds(
    files: Sequence[Path],
    quantiles: Sequence[float],
    hist_cfg: HistogramConfig,
    progress: Callable[[str], None] = log.info,
    allow_incomplete: bool = False,
) -> ThresholdResult:
    edges = make_edges(
        hist_cfg.fine_max, hist_cfg.fine_step, hist_cfg.coarse_max, hist_cfg.coarse_step
    )
    hist = StreamingHistogram(edges, N_LAT * N_LON)
    cells: np.ndarray | None = None
    samples: list[np.ndarray] = []
    seen: set[np.datetime64] = set()
    n_days = 0
    for path in files:
        with open_fwi_year(path) as da:
            for date, slab in iter_days(da):
                day = np.datetime64(date, "D")
                if day in seen:
                    raise ValueError(f"{Path(path).name}: {day} was already streamed")
                seen.add(day)
                flat = slab.ravel()
                if cells is None:
                    cells = _pick_validation_cells(flat, hist_cfg.validation_cells, hist_cfg.seed)
                if cells.size:
                    samples.append(flat[cells])
                hist.update(flat)
                n_days += 1
        progress(f"{Path(path).name}: streamed ({n_days} days so far)")
    if n_days == 0:
        raise ValueError("no daily data found in the given files")
    coverage = _check_dates(seen, allow_incomplete)
    estimate = hist.quantiles(list(quantiles))
    validation = _validate(np.array(samples), cells, estimate, quantiles) if samples else None
    return ThresholdResult(
        quantiles=tuple(float(q) for q in quantiles),
        values=estimate.reshape(len(quantiles), N_LAT, N_LON),
        count=hist.count.reshape(N_LAT, N_LON).astype(np.int32),
        overflow=hist.overflow_cells().reshape(N_LAT, N_LON),
        files=tuple(Path(p).name for p in files),
        coverage=coverage,
        validation=validation,
    )


def save_thresholds(result: ThresholdResult, path: Path) -> None:
    lat, lon = canonical_grid()
    ds = xr.Dataset(
        {
            "threshold": (("quantile", "lat", "lon"), result.values),
            "count": (("lat", "lon"), result.count),
            "overflow": (("lat", "lon"), result.overflow.astype(np.uint8)),
        },
        coords={"quantile": list(result.quantiles), "lat": lat, "lon": lon},
        attrs={
            "files": json.dumps(list(result.files)),
            "coverage": json.dumps(asdict(result.coverage)),
            "validation": json.dumps(asdict(result.validation)) if result.validation else "",
            "description": "Local FWI percentiles over the reference period (histogram estimate)",
        },
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    enc = {v: {"zlib": True, "complevel": 4} for v in ds.data_vars}
    ds.to_netcdf(path, encoding=enc)


def load_thresholds(path: Path) -> dict[str, np.ndarray]:
    """Thresholds keyed by name ('p90', 'p95', …), each (N_LAT, N_LON) float32."""
    with xr.open_dataset(path) as ds:
        qs = [float(q) for q in ds["quantile"].values]
        values = ds["threshold"].values.astype(np.float32)
    return {quantile_name(q): values[i] for i, q in enumerate(qs)}
