"""Build the burnable-wildland mask and the GFED region grid on the canonical grid."""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import xarray as xr

from earthburns.config import MaskConfig
from earthburns.grid import canonical_grid, cos_lat_weights
from earthburns.mask import (
    GLDAS_CLASS_NAMES,
    burnable_from_classes,
    nearest_nw_regrid_to_nodes,
    vote_regrid_to_nodes,
)


def load_gldas_classes(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Dominant vegetation class (int16, water = 0) with its cell-centre lat/lon."""
    with xr.open_dataset(path) as ds:
        da = ds["GLDAS_domveg"].isel(time=0)
        classes = np.nan_to_num(da.values, nan=0.0).astype(np.int16)
        return classes, da["lat"].values.astype(np.float64), da["lon"].values.astype(np.float64)


def _attr_text(value: object) -> str:
    """HDF5 attributes come back as bytes, numpy bytes or str depending on how the
    file was written; ``str()`` on the first two yields b'BONA' rather than BONA."""
    if isinstance(value, bytes | np.bytes_):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray) and value.size == 1:
        return _attr_text(value.item())
    return str(value)


def load_gfed_regions(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[int, str]]:
    """GFED basis regions (uint8, ocean = 0) from a GFED4.1s yearly HDF5 file."""
    with h5py.File(path, "r") as f:
        regions = f["ancill/basis_regions"][...].astype(np.uint8)
        lat = f["lat"][:, 0].astype(np.float64)
        lon = f["lon"][0, :].astype(np.float64)
        names = {
            int(k.split("_")[1]): _attr_text(v)
            for k, v in f["ancill/basis_regions"].attrs.items()
            if k.startswith("class_")
        }
    return regions, lat, lon, names


def check_source_grid(lat: np.ndarray, lon: np.ndarray, name: str, step: float = 0.25) -> None:
    """A source grid must be global in longitude and regularly spaced at ``step``.

    NASA ships a 1 degree vegetation file under a name one character away from the
    0.25 degree one; without this check it regrids without complaint and moves a
    quarter of the burnable cells.
    """
    for axis, values in (("lat", np.asarray(lat, float)), ("lon", np.asarray(lon, float))):
        diffs = np.abs(np.diff(values))
        if values.size < 2 or not np.allclose(diffs, step, atol=1e-6):
            got = float(np.median(diffs)) if values.size > 1 else float("nan")
            raise ValueError(f"{name}: {axis} spacing is {got}, expected {step}")
    span = float(np.asarray(lon, float).size) * step
    if not np.isclose(span, 360.0, atol=1e-6):
        raise ValueError(f"{name}: longitude covers {span} degrees, expected a global 360")


def build_masks_from_arrays(
    classes: np.ndarray, glat: np.ndarray, glon: np.ndarray,
    regions: np.ndarray, rlat: np.ndarray, rlon: np.ndarray,
    cfg: MaskConfig, region_names: dict[int, str] | None = None,
) -> xr.Dataset:
    check_source_grid(glat, glon, "vegetation grid")
    check_source_grid(rlat, rlon, "region grid")
    lat, lon = canonical_grid()
    burnable_cells = burnable_from_classes(classes, cfg.burnable_classes)
    burnable = vote_regrid_to_nodes(burnable_cells, glat, glon, lat, lon, cfg.vote_threshold)
    region_nodes = nearest_nw_regrid_to_nodes(regions, rlat, rlon, lat, lon, fill=0)
    weights = np.broadcast_to(cos_lat_weights(lat), burnable.shape).astype(np.float32)
    ds = xr.Dataset(
        {
            "burnable": (("lat", "lon"), burnable.astype(np.uint8)),
            "gfed_region": (("lat", "lon"), region_nodes.astype(np.uint8)),
            "cell_weight": (("lat", "lon"), weights),
        },
        coords={"lat": lat, "lon": lon},
        attrs={
            "burnable_classes": json.dumps(sorted(cfg.burnable_classes)),
            "burnable_class_names": json.dumps(
                {c: GLDAS_CLASS_NAMES.get(c, "?") for c in sorted(cfg.burnable_classes)}
            ),
            "vote_threshold": cfg.vote_threshold,
            "region_names": json.dumps(region_names or {}),
        },
    )
    return ds


def build_masks(cfg: MaskConfig, gldas_dir: Path, gfed_dir: Path) -> xr.Dataset:
    classes, glat, glon = load_gldas_classes(gldas_dir / cfg.domveg_file)
    regions, rlat, rlon, names = load_gfed_regions(gfed_dir / cfg.gfed_regions_file)
    return build_masks_from_arrays(classes, glat, glon, regions, rlat, rlon, cfg, names)


def save_masks(ds: xr.Dataset, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path, encoding={v: {"zlib": True, "complevel": 4} for v in ds.data_vars})


def load_masks(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[int, str]]:
    """Return (burnable bool, gfed_region uint8, cell_weight float32, region names)."""
    with xr.open_dataset(path) as ds:
        names = {int(k): v for k, v in json.loads(ds.attrs.get("region_names", "{}")).items()}
        return (
            ds["burnable"].values.astype(bool),
            ds["gfed_region"].values.astype(np.uint8),
            ds["cell_weight"].values.astype(np.float32),
            names,
        )
