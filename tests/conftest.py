"""Shared fixtures: a config pointing at a temporary tree, and tiny real-shaped inputs."""

import dataclasses
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from earthburns.build_mask import build_masks_from_arrays, save_masks
from earthburns.config import load_config
from earthburns.grid import N_LAT, N_LON, canonical_grid
from earthburns.layout import masks_path


@pytest.fixture
def sandbox_cfg(tmp_path: Path):
    """A PipelineConfig whose every path lives under ``tmp_path``."""
    base = load_config()
    paths = dataclasses.replace(
        base.paths,
        raw_dryad=tmp_path / "raw" / "dryad",
        raw_zenodo=tmp_path / "raw" / "zenodo",
        raw_gldas=tmp_path / "raw" / "gldas",
        raw_gfed=tmp_path / "raw" / "gfed",
        interim=tmp_path / "interim",
        processed=tmp_path / "processed",
        web=tmp_path / "web",
    )
    for p in dataclasses.asdict(paths).values():
        Path(p).mkdir(parents=True, exist_ok=True)
    return dataclasses.replace(base, paths=paths)


@pytest.fixture
def config_file(sandbox_cfg, tmp_path: Path) -> Path:
    """A pipeline.toml equal to the shipped one but rooted in the sandbox."""
    text = (Path(load_config().paths.raw_dryad).parents[2] / "config" / "pipeline.toml").read_text(
        encoding="utf-8"
    )
    for key, value in (
        ("raw_dryad", sandbox_cfg.paths.raw_dryad),
        ("raw_zenodo", sandbox_cfg.paths.raw_zenodo),
        ("raw_gldas", sandbox_cfg.paths.raw_gldas),
        ("raw_gfed", sandbox_cfg.paths.raw_gfed),
        ("interim", sandbox_cfg.paths.interim),
        ("processed", sandbox_cfg.paths.processed),
        ("web", sandbox_cfg.paths.web),
    ):
        old = [ln for ln in text.splitlines() if ln.startswith(f"{key} = ")][0]
        text = text.replace(old, f'{key} = "{Path(value).as_posix()}"')
    path = tmp_path / "pipeline.toml"
    path.write_text(text, encoding="utf-8")
    return path


def write_fwi_year(path: Path, year: int, values: dict[int, float], ndays: int = 365) -> None:
    """A full year on the canonical grid; ``values`` maps day index to a constant FWI."""
    lat, lon = canonical_grid()
    time = np.array([np.datetime64(f"{year}-01-01") + np.timedelta64(i, "D") for i in range(ndays)])
    data = np.zeros((ndays, N_LAT, N_LON), np.float32)
    for i in range(ndays):
        data[i] = values.get(i, 5.0)
    ds = xr.Dataset({"fwi": (("time", "lat", "lon"), data)},
                    coords={"time": time, "lat": lat, "lon": lon})
    ds.to_netcdf(path)


@pytest.fixture
def sandbox_masks(sandbox_cfg) -> Path:
    """Everything burnable, two regions split at the equator."""
    lat, lon = canonical_grid()
    classes = np.full((N_LAT - 1, N_LON), 10, np.int16)
    glat = (lat[:-1] + lat[1:]) / 2
    glon = lon + 0.125
    regions = np.where(glat[:, None] > 0, 1, 2).astype(np.uint8) * np.ones((1, N_LON), np.uint8)
    ds = build_masks_from_arrays(
        classes, glat, glon, regions, glat, glon, sandbox_cfg.mask, {1: "North", 2: "South"}
    )
    path = masks_path(sandbox_cfg)
    save_masks(ds, path)
    return path
