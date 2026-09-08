"""Resolution of yearly files and year specifications."""

from pathlib import Path

import pytest

from earthburns.config import load_config
from earthburns.sources import parse_years, year_file, year_files, year_from_path


def test_parse_years_accepts_ranges_lists_and_singles():
    assert parse_years("1991-1993") == (1991, 1992, 1993)
    assert parse_years("2018,1991") == (1991, 2018)
    assert parse_years("2001") == (2001,)
    with pytest.raises(ValueError):
        parse_years("2020-1991")


def test_year_file_for_each_source():
    cfg = load_config()
    assert year_file(cfg, "dryad", "counterfactual", 1995).name == "fwi_era5_counter_1995.nc"
    assert year_file(cfg, "zenodo", "observed", 1991).name.endswith("_1991.nc")
    with pytest.raises(ValueError):
        year_file(cfg, "zenodo", "counterfactual", 1991)
    with pytest.raises(ValueError):
        year_file(cfg, "nope", "observed", 1991)


def test_year_files_missing_policy():
    cfg = load_config()
    with pytest.raises(FileNotFoundError):
        year_files(cfg, "dryad", "observed", [1800])
    assert year_files(cfg, "dryad", "observed", [1800], allow_missing=True) == []


def test_year_from_path():
    assert year_from_path(Path("fwi_era5_counter_1995.nc")) == 1995
    with pytest.raises(ValueError):
        year_from_path(Path("nothing.nc"))
