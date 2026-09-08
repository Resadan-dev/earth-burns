"""Resolve which yearly FWI file belongs to a (source, world, year) triple."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from earthburns.config import WORLDS, PipelineConfig

SOURCES = ("dryad", "zenodo")


def year_file(cfg: PipelineConfig, source: str, world: str, year: int) -> Path:
    if world not in WORLDS:
        raise ValueError(f"unknown world {world!r}; expected one of {WORLDS}")
    if source == "dryad":
        return cfg.paths.raw_dryad / cfg.dryad.filename(world, year)
    if source == "zenodo":
        if world != "observed":
            raise ValueError("the Zenodo GEFF-ERA5 source only provides the observed world")
        return cfg.paths.raw_zenodo / cfg.zenodo.pattern.format(year=year)
    raise ValueError(f"unknown source {source!r}; expected one of {SOURCES}")


def year_files(
    cfg: PipelineConfig, source: str, world: str, years: Iterable[int], allow_missing: bool = False
) -> list[Path]:
    """Existing files for the requested years; missing files raise unless allowed."""
    found, missing = [], []
    for y in years:
        p = year_file(cfg, source, world, y)
        (found if p.is_file() else missing).append(p)
    if missing and not allow_missing:
        names = ", ".join(m.name for m in missing[:5])
        raise FileNotFoundError(f"{len(missing)} missing file(s) for {source}/{world}: {names} ...")
    return found


def year_from_path(path: Path) -> int:
    """Year embedded in a yearly file name (e.g. fwi_era5_counter_1995.nc -> 1995)."""
    m = re.search(r"(19|20)\d{2}", Path(path).name)
    if not m:
        raise ValueError(f"no year in file name {Path(path).name!r}")
    return int(m.group(0))


def default_years(cfg: PipelineConfig, source: str) -> tuple[int, ...]:
    """Years to process when the user gives none: those actually present on disk.

    Defaulting to the Dryad range regardless of source made `monthly --source
    zenodo` fail on 44 files that were never expected to exist.
    """
    if source == "dryad":
        return tuple(cfg.dryad.years)
    if source == "zenodo":
        found = sorted(
            year_from_path(p) for p in cfg.paths.raw_zenodo.glob("*.nc") if p.is_file()
        )
        if not found:
            raise FileNotFoundError(f"no yearly file in {cfg.paths.raw_zenodo}")
        return tuple(found)
    raise ValueError(f"unknown source {source!r}; expected one of {SOURCES}")


def parse_years(spec: str) -> tuple[int, ...]:
    """'1991-2020' -> range, '1991,1995' -> list, '2018' -> single year."""
    years: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
            if a > b:
                raise ValueError(f"inverted year range {part!r}")
            years.extend(range(a, b + 1))
        elif part:
            years.append(int(part))
    if not years:
        raise ValueError(f"no years in {spec!r}")
    return tuple(sorted(set(years)))
