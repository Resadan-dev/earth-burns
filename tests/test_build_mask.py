"""Loading the real-shaped source grids, decoding their metadata, and validating them."""

from pathlib import Path

import h5py
import numpy as np
import pytest
import xarray as xr

from earthburns.build_mask import (
    _attr_text,
    check_source_grid,
    load_gfed_regions,
    load_gldas_classes,
)


def test_attr_text_decodes_every_hdf5_flavour():
    assert _attr_text(b"BONA") == "BONA"
    assert _attr_text(np.bytes_(b"TENA")) == "TENA"
    assert _attr_text("EURO") == "EURO"
    assert _attr_text(np.array([b"AUST"])) == "AUST"


def test_load_gldas_classes_turns_missing_into_water(tmp_path: Path):
    lat = np.arange(-59.875, 90.0, 0.25)
    lon = np.arange(-179.875, 180.0, 0.25)
    veg = np.full((1, lat.size, lon.size), 10.0, np.float32)
    veg[0, 0, 0] = np.nan
    p = tmp_path / "veg.nc4"
    xr.Dataset(
        {"GLDAS_domveg": (("time", "lat", "lon"), veg)},
        coords={"time": [np.datetime64("2000-01-01")], "lat": lat, "lon": lon},
    ).to_netcdf(p)
    classes, glat, glon = load_gldas_classes(p)
    assert classes.dtype == np.int16 and classes[0, 0] == 0 and classes[1, 1] == 10
    assert glat[0] == pytest.approx(-59.875) and glon[-1] == pytest.approx(179.875)


def test_load_gfed_regions_decodes_byte_names(tmp_path: Path):
    lat = np.arange(89.875, -90.0, -0.25)
    lon = np.arange(-179.875, 180.0, 0.25)
    p = tmp_path / "gfed.hdf5"
    with h5py.File(p, "w") as f:
        d = f.create_dataset("ancill/basis_regions", data=np.ones((lat.size, lon.size), np.uint8))
        d.attrs["class_0"] = np.bytes_(b"Ocean")
        d.attrs["class_1"] = np.bytes_(b"BONA (Boreal North America)")
        d.attrs["other"] = np.bytes_(b"ignored")
        f.create_dataset("lat", data=np.repeat(lat[:, None], lon.size, axis=1))
        f.create_dataset("lon", data=np.repeat(lon[None, :], lat.size, axis=0))
    regions, rlat, rlon, names = load_gfed_regions(p)
    assert regions.dtype == np.uint8 and regions.shape == (lat.size, lon.size)
    assert names == {0: "Ocean", 1: "BONA (Boreal North America)"}
    assert rlat[0] == pytest.approx(89.875)


def test_check_source_grid_rejects_the_wrong_resolution_and_a_regional_extent():
    lat = np.arange(-59.875, 90.0, 0.25)
    lon = np.arange(-179.875, 180.0, 0.25)
    check_source_grid(lat, lon, "ok")  # does not raise

    coarse_lat = np.arange(-59.5, 90.0, 1.0)
    coarse_lon = np.arange(-179.5, 180.0, 1.0)
    with pytest.raises(ValueError, match="spacing"):
        check_source_grid(coarse_lat, coarse_lon, "1 degree file")

    with pytest.raises(ValueError, match="longitude covers"):
        check_source_grid(lat, np.arange(-19.875, 40.0, 0.25), "europe only")
