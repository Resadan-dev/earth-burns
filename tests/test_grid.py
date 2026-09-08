"""Canonical grid, latitude weights and re-orientation of input arrays."""

import numpy as np
import pytest
import xarray as xr

from earthburns.grid import canonical_grid, cos_lat_weights, to_canonical


def _synthetic(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Value encodes position so that any misalignment is detectable."""
    return lat[:, None] * 1000.0 + lon[None, :]


def test_canonical_grid_shape_and_orientation():
    lat, lon = canonical_grid()
    assert lat.shape == (721,) and lon.shape == (1440,)
    assert lat[0] == 90.0 and lat[-1] == -90.0
    assert np.all(np.diff(lat) < 0)
    assert lon[0] == -180.0 and lon[-1] == 179.75
    assert np.allclose(np.diff(lon), 0.25)


def test_cos_lat_weights_zero_at_poles_and_one_at_equator():
    lat, _ = canonical_grid()
    w = cos_lat_weights(lat)
    assert w.shape == (721, 1)
    assert w[0, 0] == pytest.approx(0.0, abs=1e-12)
    assert w[360, 0] == pytest.approx(1.0)
    assert np.all(w >= 0)


def test_to_canonical_reorders_ascending_lat_and_0_360_lon():
    lat_src = np.arange(-90, 90.01, 0.25)
    lon_src = np.arange(0, 360, 0.25)
    lon_signed = np.where(lon_src >= 180, lon_src - 360, lon_src)
    da = xr.DataArray(
        _synthetic(lat_src, lon_signed),
        dims=("lat", "lon"),
        coords={"lat": lat_src, "lon": lon_src},
    )
    out = to_canonical(da)
    lat, lon = canonical_grid()
    assert np.allclose(out["lat"].values, lat)
    assert np.allclose(out["lon"].values, lon)
    assert np.allclose(out.values, _synthetic(lat, lon))


def test_to_canonical_accepts_alternative_dim_names_and_keeps_time_first():
    lat_src = np.arange(90, -90.01, -0.25)
    lon_src = np.arange(-180, 180, 0.25)
    base = _synthetic(lat_src, lon_src)
    da = xr.DataArray(
        np.stack([base, base + 1.0]),
        dims=("time", "latitude", "longitude"),
        coords={"time": [0, 1], "latitude": lat_src, "longitude": lon_src},
    )
    out = to_canonical(da)
    assert out.dims == ("time", "lat", "lon")
    assert np.allclose(out.values[1], _synthetic(*canonical_grid()) + 1.0)


def test_to_canonical_rejects_unexpected_grid():
    da = xr.DataArray(
        np.zeros((10, 20)),
        dims=("lat", "lon"),
        coords={"lat": np.linspace(-90, 90, 10), "lon": np.linspace(0, 359, 20)},
    )
    with pytest.raises(ValueError):
        to_canonical(da)
