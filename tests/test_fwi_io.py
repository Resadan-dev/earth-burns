"""Opening a yearly FWI NetCDF file and normalising it onto the canonical grid."""

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from earthburns.fwi_io import find_fwi_variable, iter_days, open_fwi_year


def _write_synthetic(path: Path, var: str = "fwi", ndays: int = 3) -> None:
    lat = np.arange(-90, 90.01, 0.25)
    lon = np.arange(0, 360, 0.25)
    time = np.array([np.datetime64("2001-01-01") + np.timedelta64(i, "D") for i in range(ndays)])
    lon_signed = np.where(lon >= 180, lon - 360, lon)
    base = lat[:, None] * 1000.0 + lon_signed[None, :]
    data = np.stack([base + i for i in range(ndays)]).astype(np.float32)
    ds = xr.Dataset(
        {var: (("time", "lat", "lon"), data), "aux": (("lat",), np.zeros(lat.size))},
        coords={"time": time, "lat": lat, "lon": lon},
    )
    ds.to_netcdf(path)


def _multi_var(path: Path) -> None:
    """A GEFF-like file: FWI next to the other Canadian fire weather codes."""
    lat = np.arange(90, -90.01, -0.25)
    lon = np.arange(-180, 180, 0.25)
    shape = (2, lat.size, lon.size)
    ds = xr.Dataset(
        {name: (("time", "lat", "lon"), np.full(shape, i, np.float32))
         for i, name in enumerate(("ffmc", "dmc", "dc", "isi", "bui", "fwi"))},
        coords={"time": [0, 1], "lat": lat, "lon": lon},
    )
    ds.to_netcdf(path)


def test_find_fwi_variable_picks_fwi_among_several_3d_variables(tmp_path: Path):
    p = tmp_path / "multi.nc"
    _multi_var(p)
    with xr.open_dataset(p) as ds:
        assert find_fwi_variable(ds) == "fwi"


def test_find_fwi_variable_refuses_an_unnamed_variable_unless_asked(tmp_path: Path):
    p = tmp_path / "b.nc"
    _write_synthetic(p, var="ffmc")  # a real field, but not the Fire Weather Index
    with xr.open_dataset(p) as ds:
        with pytest.raises(ValueError, match="no FWI variable"):
            find_fwi_variable(ds)
        assert find_fwi_variable(ds, allow_unnamed=True) == "ffmc"


def test_find_fwi_variable_accepts_a_known_name(tmp_path: Path):
    p = tmp_path / "a.nc"
    _write_synthetic(p, var="fwi")
    with xr.open_dataset(p) as ds:
        assert find_fwi_variable(ds) == "fwi"


def test_open_fwi_year_returns_canonical_lazy_array(tmp_path: Path):
    p = tmp_path / "fwi_era5_2001.nc"
    _write_synthetic(p)
    with open_fwi_year(p) as da:
        assert da.dims == ("time", "lat", "lon")
        assert da.shape == (3, 721, 1440)
        assert da["lat"].values[0] == 90.0 and da["lon"].values[0] == -180.0
        days = list(iter_days(da))
        assert len(days) == 3
        date, slab = days[1]
        assert date == np.datetime64("2001-01-02")
        assert slab.dtype == np.float32 and slab.shape == (721, 1440)
        assert slab[0, 0] == pytest.approx(90 * 1000.0 - 180.0 + 1)


def test_open_fwi_year_rejects_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        with open_fwi_year(tmp_path / "missing.nc"):
            pass


def test_open_fwi_year_reconstructs_dates_from_day_index_and_filename(tmp_path: Path):
    # GEFF-ERA5 style: dims Time/Latitude/Longitude, time = 1..N day numbers, lon 0..360
    lat = np.arange(90, -90.01, -0.25)
    lon = np.arange(0, 360, 0.25)
    data = np.zeros((3, lat.size, lon.size), np.float32)
    ds = xr.Dataset(
        {"FWI": (("Time", "Latitude", "Longitude"), data), "crs": ((), np.int32(0))},
        coords={"Time": [1.0, 2.0, 3.0], "Latitude": lat, "Longitude": lon},
    )
    p = tmp_path / "no_overwintering_fire_weather_index_1991.nc"
    ds.to_netcdf(p)
    with open_fwi_year(p) as da:
        assert da.dims == ("time", "lat", "lon")
        assert da["time"].values[0] == np.datetime64("1991-01-01")
        assert da["time"].values[-1] == np.datetime64("1991-01-03")


def test_open_fwi_year_numeric_time_without_year_is_an_error(tmp_path: Path):
    lat = np.arange(90, -90.01, -0.25)
    lon = np.arange(-180, 180, 0.25)
    ds = xr.Dataset(
        {"fwi": (("time", "lat", "lon"), np.zeros((2, lat.size, lon.size), np.float32))},
        coords={"time": [1.0, 2.0], "lat": lat, "lon": lon},
    )
    p = tmp_path / "noyear.nc"
    ds.to_netcdf(p)
    with pytest.raises(ValueError):
        with open_fwi_year(p):
            pass


def test_iter_days_turns_negative_fill_values_into_nan():
    lat = np.arange(90, -90.01, -0.25)
    lon = np.arange(-180, 180, 0.25)
    data = np.full((2, lat.size, lon.size), 5.0, np.float32)
    data[0, 0, 0] = -3.4e38
    da = xr.DataArray(data, dims=("time", "lat", "lon"),
                      coords={"time": np.array(["2001-01-01", "2001-01-02"], "datetime64[D]"),
                              "lat": lat, "lon": lon})
    days = list(iter_days(da, block_days=1))
    assert np.isnan(days[0][1][0, 0]) and days[1][1][0, 0] == 5.0
