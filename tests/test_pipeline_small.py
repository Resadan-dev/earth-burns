"""End-to-end wiring on tiny synthetic files placed on the real canonical grid."""

import dataclasses
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from earthburns.build_mask import build_masks_from_arrays, load_masks, save_masks
from earthburns.config import load_config
from earthburns.extent import ExtentContext
from earthburns.grid import N_LAT, N_LON, canonical_grid
from earthburns.monthly_run import extent_columns, run_year, save_year
from earthburns.thresholds import compute_thresholds, load_thresholds, save_thresholds


def _write_year(path: Path, year: int, ndays: int, value: float) -> None:
    lat, lon = canonical_grid()
    time = np.array([np.datetime64(f"{year}-01-01") + np.timedelta64(i, "D") for i in range(ndays)])
    data = np.full((ndays, N_LAT, N_LON), value, np.float32)
    data[:, :, 0] = np.nan  # a "missing" column
    ds = xr.Dataset(
        {"fwi": (("time", "lat", "lon"), data)},
        coords={"time": time, "lat": lat, "lon": lon},
    )
    ds.to_netcdf(path)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def _masks(tmp_path: Path, cfg) -> Path:
    """Everything burnable, two regions split at the equator."""
    lat, lon = canonical_grid()
    classes = np.full((N_LAT - 1, N_LON), 10, np.int16)
    glat = (lat[:-1] + lat[1:]) / 2
    glon = lon + 0.125
    regions = np.where(glat[:, None] > 0, 1, 2).astype(np.uint8) * np.ones((1, N_LON), np.uint8)
    masks = build_masks_from_arrays(
        classes, glat, glon, regions, glat, glon, cfg.mask, {1: "N", 2: "S"}
    )
    path = tmp_path / "masks.nc"
    save_masks(masks, path)
    return path


def test_thresholds_then_monthly_on_synthetic_files(tmp_path: Path, cfg):
    f1, f2 = tmp_path / "fwi_era5_2001.nc", tmp_path / "fwi_era5_2002.nc"
    _write_year(f1, 2001, 4, 10.0)
    _write_year(f2, 2002, 4, 30.0)

    hist_cfg = dataclasses.replace(cfg.histogram, validation_cells=50)
    with pytest.raises(ValueError, match="incomplete"):
        compute_thresholds([f1, f2], (0.5, 0.9), hist_cfg, progress=lambda s: None)
    with pytest.raises(ValueError, match="already streamed"):
        compute_thresholds([f1, f1], (0.5,), hist_cfg, lambda s: None, allow_incomplete=True)

    res = compute_thresholds(
        [f1, f2], (0.5, 0.9), hist_cfg, progress=lambda s: None, allow_incomplete=True
    )
    assert res.values.shape == (2, N_LAT, N_LON)
    assert res.count[0, 5] == 8 and res.count[0, 0] == 0
    assert 10.0 <= res.values[0, 0, 5] <= 30.0 and np.isnan(res.values[0, 0, 0])
    assert res.coverage.n_days == 8 and res.coverage.years == (2001, 2002)
    assert len(res.coverage.missing_days) == 722
    assert res.validation is not None and max(res.validation.max_abs_error) <= 1.0 + 1e-6

    thr_path = tmp_path / "thr.nc"
    save_thresholds(res, thr_path)
    thr = load_thresholds(thr_path)
    assert set(thr) == {"p50", "p90"} and thr["p90"].shape == (N_LAT, N_LON)

    burnable, reg, weights, names = load_masks(_masks(tmp_path, cfg))
    assert names == {1: "N", 2: "S"} and burnable[100, 100] and reg[100, 100] == 1
    ctx = ExtentContext(burnable, weights, reg, (1, 2))

    # The p90 estimate lies inside the histogram bin [30.0, 30.2): a value of exactly 30
    # is therefore not counted as exceeding it, while 40 clearly is.
    f3 = tmp_path / "fwi_era5_2003.nc"
    _write_year(f3, 2003, 4, 40.0)
    counts, extent, days_seen = run_year(f3, 2003, thr, ctx, require_complete=False)
    assert days_seen.sum() == 4 and days_seen[0] == 4
    assert counts["p90"].shape == (12, N_LAT, N_LON)
    assert counts["p90"][0, 0, 5] == 4 and counts["p50"][0, 0, 5] == 4
    same, _, _ = run_year(f2, 2002, thr, ctx, require_complete=False)
    assert same["p90"][0, 0, 5] == 0 and same["p50"][0, 0, 5] == 4

    assert list(extent.columns) == ["date", "threshold", *extent_columns((1, 2))]
    assert len(extent) == 4 * 2
    p90 = extent[extent.threshold == "p90"]
    assert p90["global"].max() <= 1.0
    # one grid column is NaN everywhere, so coverage is just under 1
    assert 0.99 < p90["coverage"].min() < 1.0
    assert p90["global"].iloc[0] == pytest.approx(p90["coverage"].iloc[0])

    counts_path, extent_path = save_year(
        counts, extent, days_seen, 2003, tmp_path / "out", "test_observed"
    )
    with xr.open_dataset(counts_path) as ds:
        assert ds["days_gt_p90"].shape == (12, N_LAT, N_LON)
        assert ds["days_observed"].values[0] == 4
    assert extent_path.name == "test_observed_2003_extent.parquet"
