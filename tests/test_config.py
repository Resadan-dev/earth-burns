"""Configuration loading and validation."""

from pathlib import Path

import pytest

from earthburns.config import PROJECT_ROOT, PipelineConfig, load_config


def test_default_config_loads_and_resolves_paths():
    cfg = load_config()
    assert isinstance(cfg, PipelineConfig)
    assert cfg.paths.raw_dryad == PROJECT_ROOT / "data" / "raw" / "dryad"
    assert cfg.reference.first_year == 1991 and cfg.reference.last_year == 2020
    assert cfg.reference.quantiles == (0.90, 0.95, 0.99)
    assert 1 in cfg.mask.burnable_classes and 12 not in cfg.mask.burnable_classes


def _mutated(tmp_path: Path, old: str, new: str) -> Path:
    text = (PROJECT_ROOT / "config" / "pipeline.toml").read_text(encoding="utf-8")
    assert old in text
    p = tmp_path / "pipeline.toml"
    p.write_text(text.replace(old, new), encoding="utf-8")
    return p


def test_config_rejects_inverted_year_range(tmp_path: Path):
    with pytest.raises(ValueError):
        load_config(_mutated(tmp_path, "first_year = 1991", "first_year = 2021"))


def test_config_rejects_quantile_out_of_range(tmp_path: Path):
    with pytest.raises(ValueError):
        load_config(_mutated(tmp_path, "quantiles = [0.90, 0.95, 0.99]", "quantiles = [0.9, 1.5]"))


def test_dryad_year_files_are_named_from_patterns():
    cfg = load_config()
    assert cfg.dryad.filename("observed", 1979) == "fwi_era5_1979.nc"
    assert cfg.dryad.filename("counterfactual", 2024) == "fwi_era5_counter_2024.nc"
    with pytest.raises(ValueError):
        cfg.dryad.filename("other", 1979)
