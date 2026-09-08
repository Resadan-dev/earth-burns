"""The command line: argument wiring, exit codes, and one full run end to end."""

import json
from pathlib import Path

import numpy as np
import pytest

from earthburns.cli import build_parser, main
from earthburns.layout import extent_path, monthly_path, thresholds_path
from tests.conftest import write_fwi_year


def _run(config_file: Path, *argv: str) -> int:
    return main(["--config", str(config_file), *argv])


def test_parser_exposes_every_command():
    parser = build_parser()
    for argv in (
        ["mask"],
        ["thresholds", "--source", "zenodo"],
        ["monthly", "--thresholds", "t.nc"],
        ["pack", "--world", "counterfactual"],
        ["dryad", "status"],
    ):
        assert parser.parse_args(argv).func is not None
    with pytest.raises(SystemExit):
        parser.parse_args(["monthly"])  # --thresholds is required
    with pytest.raises(SystemExit):
        parser.parse_args(["monthly", "--thresholds", "t.nc", "--world", "elsewhere"])


def test_missing_inputs_return_a_nonzero_code(config_file, sandbox_cfg):
    assert _run(config_file, "thresholds", "--source", "zenodo", "--years", "1991",
                "--allow-missing") == 2
    assert _run(config_file, "pack", "--source", "zenodo") == 2


def test_full_zenodo_run_produces_a_consistent_bundle(config_file, sandbox_cfg, sandbox_masks):
    raw = sandbox_cfg.paths.raw_zenodo
    pattern = sandbox_cfg.zenodo.pattern
    write_fwi_year(raw / pattern.format(year=1991), 1991, {})
    write_fwi_year(raw / pattern.format(year=1992), 1992, {i: 50.0 for i in range(200)}, ndays=366)

    assert _run(config_file, "thresholds", "--source", "zenodo", "--years", "1991") == 0
    thr = thresholds_path(sandbox_cfg, "zenodo", 1991, 1991)
    assert thr.is_file()

    assert _run(config_file, "monthly", "--source", "zenodo", "--years", "1992",
                "--thresholds", str(thr)) == 0
    assert monthly_path(sandbox_cfg, "zenodo", "observed", 1992).is_file()
    assert extent_path(sandbox_cfg, "zenodo", "observed", 1992).is_file()

    assert _run(config_file, "pack", "--source", "zenodo") == 0
    web = sandbox_cfg.paths.web / "zenodo"
    manifest = json.loads((web / "manifest.json").read_text())
    entry = manifest["worlds"]["observed"]
    assert manifest["source"] == "zenodo"
    assert entry["years"] == [1992, 1992]
    assert entry["region_names"] == {"1": "North", "2": "South"}
    assert entry["extent"]["shape"] == [366, 3, 6]
    assert entry["extent"]["columns"][:2] == ["global", "coverage"]
    assert sorted(entry["thresholds"]) == ["p90", "p95", "p99"]
    assert (web / entry["thresholds"]["p90"][0]["file"]).is_file()


def test_thresholds_refuses_an_incomplete_reference_unless_allowed(
    config_file, sandbox_cfg, sandbox_masks
):
    raw = sandbox_cfg.paths.raw_zenodo
    write_fwi_year(raw / sandbox_cfg.zenodo.pattern.format(year=1991), 1991, {}, ndays=300)
    with pytest.raises(ValueError, match="incomplete"):
        _run(config_file, "thresholds", "--source", "zenodo", "--years", "1991")
    assert _run(config_file, "thresholds", "--source", "zenodo", "--years", "1991",
                "--allow-incomplete") == 0


def test_monthly_defaults_to_the_years_present_for_the_source(
    config_file, sandbox_cfg, sandbox_masks
):
    raw = sandbox_cfg.paths.raw_zenodo
    write_fwi_year(raw / sandbox_cfg.zenodo.pattern.format(year=1991), 1991, {})
    # pass 1 keeps the reference period as its default; only pass 2 follows the source
    assert _run(config_file, "thresholds", "--source", "zenodo", "--years", "1991") == 0
    thr = thresholds_path(sandbox_cfg, "zenodo", 1991, 1991)
    assert thr.name == "thresholds_zenodo_1991-1991.nc"
    assert _run(config_file, "monthly", "--source", "zenodo", "--thresholds", str(thr)) == 0
    assert monthly_path(sandbox_cfg, "zenodo", "observed", 1991).is_file()


def test_pack_refuses_a_changed_mask_and_accepts_force(config_file, sandbox_cfg, sandbox_masks):
    import xarray as xr

    raw = sandbox_cfg.paths.raw_zenodo
    write_fwi_year(raw / sandbox_cfg.zenodo.pattern.format(year=1991), 1991, {})
    thr = thresholds_path(sandbox_cfg, "zenodo", 1991, 1991)
    assert _run(config_file, "thresholds", "--source", "zenodo", "--years", "1991") == 0
    assert _run(config_file, "monthly", "--source", "zenodo", "--years", "1991",
                "--thresholds", str(thr)) == 0
    assert _run(config_file, "pack", "--source", "zenodo") == 0

    with xr.open_dataset(sandbox_masks) as ds:
        shrunk = ds.load()
    shrunk["burnable"].values[:100, :] = 0
    sandbox_masks.unlink()
    shrunk.to_netcdf(sandbox_masks)
    with pytest.raises(ValueError, match="already packed"):
        _run(config_file, "pack", "--source", "zenodo")
    assert _run(config_file, "pack", "--source", "zenodo", "--force") == 0


def test_mask_command_writes_masks_from_real_inputs(config_file, sandbox_cfg):
    import h5py
    import xarray as xr

    lat = np.arange(-59.875, 90.0, 0.25)
    lon = np.arange(-179.875, 180.0, 0.25)
    veg = np.full((1, lat.size, lon.size), 10.0, np.float32)
    xr.Dataset(
        {"GLDAS_domveg": (("time", "lat", "lon"), veg)},
        coords={"time": [np.datetime64("2000-01-01")], "lat": lat, "lon": lon},
    ).to_netcdf(sandbox_cfg.paths.raw_gldas / sandbox_cfg.mask.domveg_file)

    rlat = np.arange(89.875, -90.0, -0.25)
    with h5py.File(sandbox_cfg.paths.raw_gfed / sandbox_cfg.mask.gfed_regions_file, "w") as f:
        d = f.create_dataset("ancill/basis_regions", data=np.ones((rlat.size, lon.size), np.uint8))
        d.attrs["class_0"] = np.bytes_(b"Ocean")
        d.attrs["class_1"] = np.bytes_(b"BONA (Boreal North America)")
        f.create_dataset("lat", data=np.repeat(rlat[:, None], lon.size, axis=1))
        f.create_dataset("lon", data=np.repeat(lon[None, :], rlat.size, axis=0))

    assert _run(config_file, "mask") == 0
    from earthburns.build_mask import load_masks
    from earthburns.layout import masks_path

    burnable, regions, weights, names = load_masks(masks_path(sandbox_cfg))
    assert burnable.any() and regions.max() == 1
    # HDF5 byte attributes must arrive as text, not as b'...' reprs
    assert names[1] == "BONA (Boreal North America)"
