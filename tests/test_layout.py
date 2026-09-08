"""Artefact naming lives in one module, and pairing is checked on disk."""

import dataclasses

from earthburns.config import load_config
from earthburns.layout import (
    extent_path,
    masks_path,
    monthly_path,
    monthly_years,
    prefix,
    thresholds_path,
    web_dir,
)


def test_names_are_stable():
    cfg = load_config()
    assert masks_path(cfg).name == "masks.nc"
    assert thresholds_path(cfg, "dryad", 1991, 2020).name == "thresholds_dryad_1991-2020.nc"
    assert prefix("dryad", "counterfactual") == "dryad_counterfactual"
    assert monthly_path(cfg, "dryad", "observed", 1979).name == "dryad_observed_1979.nc"
    assert extent_path(cfg, "dryad", "observed", 1979).name == "dryad_observed_1979_extent.parquet"
    assert web_dir(cfg, "zenodo").name == "zenodo"


def test_monthly_years_requires_both_artefacts(tmp_path):
    base = load_config()
    cfg = dataclasses.replace(base, paths=dataclasses.replace(base.paths, interim=tmp_path))
    (tmp_path / "monthly").mkdir()
    for year, with_extent in ((2001, True), (2002, False)):
        monthly_path(cfg, "dryad", "observed", year).write_bytes(b"x")
        if with_extent:
            extent_path(cfg, "dryad", "observed", year).write_bytes(b"x")
    # a stray file that is not a year must not be picked up
    (tmp_path / "monthly" / "dryad_observed_notes.nc").write_bytes(b"x")
    assert sorted(monthly_years(cfg, "dryad", "observed")) == [2001]
