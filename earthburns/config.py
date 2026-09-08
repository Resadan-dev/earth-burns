"""Typed, validated pipeline configuration loaded from ``config/pipeline.toml``."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "pipeline.toml"
WORLDS = ("observed", "counterfactual")


@dataclass(frozen=True)
class Paths:
    raw_dryad: Path
    raw_zenodo: Path
    raw_gldas: Path
    raw_gfed: Path
    interim: Path
    processed: Path
    web: Path


@dataclass(frozen=True)
class DryadConfig:
    doi: str
    version_id: int
    observed_pattern: str
    counterfactual_pattern: str
    first_year: int
    last_year: int

    def filename(self, world: str, year: int) -> str:
        if world == "observed":
            return self.observed_pattern.format(year=year)
        if world == "counterfactual":
            return self.counterfactual_pattern.format(year=year)
        raise ValueError(f"unknown world {world!r}; expected one of {WORLDS}")

    @property
    def years(self) -> range:
        return range(self.first_year, self.last_year + 1)


@dataclass(frozen=True)
class ZenodoConfig:
    record_id: int
    pattern: str


@dataclass(frozen=True)
class ReferenceConfig:
    first_year: int
    last_year: int
    quantiles: tuple[float, ...]

    @property
    def years(self) -> range:
        return range(self.first_year, self.last_year + 1)


@dataclass(frozen=True)
class HistogramConfig:
    fine_max: float
    fine_step: float
    coarse_max: float
    coarse_step: float
    validation_cells: int
    seed: int


@dataclass(frozen=True)
class MaskConfig:
    burnable_classes: frozenset[int]
    vote_threshold: float
    domveg_file: str
    gfed_regions_file: str


@dataclass(frozen=True)
class PipelineConfig:
    paths: Paths
    dryad: DryadConfig
    zenodo: ZenodoConfig
    reference: ReferenceConfig
    histogram: HistogramConfig
    mask: MaskConfig


def _resolve(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else root / p


def _year_range(section: dict, name: str) -> tuple[int, int]:
    first, last = int(section["first_year"]), int(section["last_year"])
    if first > last:
        raise ValueError(f"[{name}] first_year {first} is after last_year {last}")
    return first, last


def _build(raw: dict, root: Path) -> PipelineConfig:
    p = raw["paths"]
    paths = Paths(**{k: _resolve(root, p[k]) for k in Paths.__dataclass_fields__})

    d = raw["dryad"]
    d_first, d_last = _year_range(d, "dryad")
    dryad = DryadConfig(
        doi=str(d["doi"]),
        version_id=int(d["version_id"]),
        observed_pattern=str(d["observed_pattern"]),
        counterfactual_pattern=str(d["counterfactual_pattern"]),
        first_year=d_first,
        last_year=d_last,
    )

    z = raw["zenodo"]
    zenodo = ZenodoConfig(record_id=int(z["record_id"]), pattern=str(z["pattern"]))

    r = raw["reference"]
    r_first, r_last = _year_range(r, "reference")
    quantiles = tuple(float(q) for q in r["quantiles"])
    if not quantiles or any(not (0.0 < q < 1.0) for q in quantiles):
        raise ValueError(f"[reference] quantiles must lie strictly in (0, 1): {quantiles}")
    # Thresholds are keyed by their rounded name everywhere downstream, so two
    # quantiles rounding to the same percent would silently overwrite each other.
    names = [f"p{int(round(q * 100))}" for q in quantiles]
    if len(set(names)) != len(names):
        pairs = list(zip(quantiles, names, strict=True))
        raise ValueError(f"[reference] quantiles collide once named: {pairs}")
    reference = ReferenceConfig(first_year=r_first, last_year=r_last, quantiles=quantiles)

    h = raw["histogram"]
    histogram = HistogramConfig(
        fine_max=float(h["fine_max"]),
        fine_step=float(h["fine_step"]),
        coarse_max=float(h["coarse_max"]),
        coarse_step=float(h["coarse_step"]),
        validation_cells=int(h["validation_cells"]),
        seed=int(h["seed"]),
    )
    if not (0 < histogram.fine_step and 0 < histogram.coarse_step):
        raise ValueError("[histogram] steps must be positive")
    if not (0 < histogram.fine_max < histogram.coarse_max):
        raise ValueError("[histogram] need 0 < fine_max < coarse_max")
    if histogram.validation_cells < 0:
        raise ValueError("[histogram] validation_cells must be >= 0")

    m = raw["mask"]
    vote = float(m["vote_threshold"])
    if not (0.0 <= vote <= 1.0):
        raise ValueError("[mask] vote_threshold must lie in [0, 1]")
    mask = MaskConfig(
        burnable_classes=frozenset(int(c) for c in m["burnable_classes"]),
        vote_threshold=vote,
        domveg_file=str(m["domveg_file"]),
        gfed_regions_file=str(m["gfed_regions_file"]),
    )
    return PipelineConfig(paths, dryad, zenodo, reference, histogram, mask)


def load_config(path: Path | None = None) -> PipelineConfig:
    """Load and validate the TOML configuration (defaults to ``config/pipeline.toml``)."""
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with open(cfg_path, "rb") as fh:
        raw = tomllib.load(fh)
    try:
        return _build(raw, PROJECT_ROOT)
    except KeyError as exc:
        raise ValueError(f"missing configuration key {exc} in {cfg_path}") from exc
