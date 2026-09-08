"""One place that decides where every pipeline artefact lives.

Writers and readers previously spelled these names out independently and then
recovered them with globs and regexes; naming them once means a re-run overwrites
exactly what it replaces.
"""

from __future__ import annotations

from pathlib import Path

from earthburns.config import PipelineConfig


def masks_path(cfg: PipelineConfig) -> Path:
    return cfg.paths.interim / "masks.nc"


def thresholds_path(cfg: PipelineConfig, source: str, first_year: int, last_year: int) -> Path:
    return cfg.paths.interim / f"thresholds_{source}_{first_year}-{last_year}.nc"


def monthly_dir(cfg: PipelineConfig) -> Path:
    return cfg.paths.interim / "monthly"


def prefix(source: str, world: str) -> str:
    return f"{source}_{world}"


def monthly_path(cfg: PipelineConfig, source: str, world: str, year: int) -> Path:
    return monthly_dir(cfg) / f"{prefix(source, world)}_{year}.nc"


def extent_path(cfg: PipelineConfig, source: str, world: str, year: int) -> Path:
    return monthly_dir(cfg) / f"{prefix(source, world)}_{year}_extent.parquet"


def monthly_years(cfg: PipelineConfig, source: str, world: str) -> dict[int, Path]:
    """Years for which BOTH the counts and the extent rows exist, keyed by year."""
    pre = prefix(source, world)
    found: dict[int, Path] = {}
    for p in sorted(monthly_dir(cfg).glob(f"{pre}_*.nc")):
        stem = p.stem[len(pre) + 1 :]
        if not stem.isdigit():
            continue
        year = int(stem)
        if extent_path(cfg, source, world, year).is_file():
            found[year] = p
    return found


def web_dir(cfg: PipelineConfig, source: str) -> Path:
    return cfg.paths.web / source
