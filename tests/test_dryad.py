"""Dryad manifest parsing, download ordering and local verification (no network)."""

import hashlib
from pathlib import Path

import pytest

from earthburns.dryad import (
    FileEntry,
    LocalStatus,
    download_order,
    local_status,
    parse_manifest,
    sha256_of_file,
)


def _payload():
    def rec(path, size, digest, fid):
        return {
            "path": path,
            "size": size,
            "digestType": "sha-256",
            "digest": digest,
            "_links": {"stash:download": {"href": f"/api/v2/files/{fid}/download"}},
        }

    return {
        "_embedded": {
            "stash:files": [
                rec("fwi_era5_1979.nc", 10, "ab", 1),
                rec("fwi_era5_counter_1979.nc", 10, "cd", 2),
                rec("README.md", 5, "ef", 3),
            ]
        }
    }


def test_parse_manifest_extracts_entries_with_world_and_year():
    entries = parse_manifest(_payload())
    assert [e.path for e in entries] == [
        "fwi_era5_1979.nc",
        "fwi_era5_counter_1979.nc",
        "README.md",
    ]
    assert entries[0].world == "observed" and entries[0].year == 1979
    assert entries[1].world == "counterfactual" and entries[1].year == 1979
    assert entries[2].world is None and entries[2].year is None
    assert entries[0].download_url == "https://datadryad.org/api/v2/files/1/download"
    assert entries[0].sha256 == "ab"


def test_parse_manifest_rejects_unknown_digest_type():
    payload = _payload()
    payload["_embedded"]["stash:files"][0]["digestType"] = "md5"
    with pytest.raises(ValueError):
        parse_manifest(payload)


def _entry(path, world, year):
    return FileEntry(path=path, size=1, sha256="x", download_url="u", world=world, year=year)


def test_download_order_small_files_then_reference_years_then_rest():
    entries = [
        _entry("fwi_era5_2024.nc", "observed", 2024),
        _entry("fwi_era5_counter_1995.nc", "counterfactual", 1995),
        _entry("fwi_era5_1979.nc", "observed", 1979),
        _entry("fwi_era5_1995.nc", "observed", 1995),
        _entry("fwi_era5_counter_2024.nc", "counterfactual", 2024),
        _entry("README.md", None, None),
    ]
    ordered = [e.path for e in download_order(entries, reference_years=(1991, 2020))]
    assert ordered == [
        "README.md",
        "fwi_era5_1995.nc",
        "fwi_era5_counter_1995.nc",
        "fwi_era5_1979.nc",
        "fwi_era5_2024.nc",
        "fwi_era5_counter_2024.nc",
    ]


def test_sha256_of_file_and_local_status(tmp_path: Path):
    p = tmp_path / "fwi_era5_1979.nc"
    p.write_bytes(b"hello world")
    digest = hashlib.sha256(b"hello world").hexdigest()
    assert sha256_of_file(p) == digest

    ok = FileEntry("fwi_era5_1979.nc", 11, digest, "u", "observed", 1979)
    assert local_status(ok, tmp_path, verify=True) is LocalStatus.VERIFIED
    assert local_status(ok, tmp_path, verify=False) is LocalStatus.COMPLETE_UNVERIFIED

    bad = FileEntry("fwi_era5_1979.nc", 11, "0" * 64, "u", "observed", 1979)
    assert local_status(bad, tmp_path, verify=True) is LocalStatus.CORRUPT

    partial = FileEntry("fwi_era5_1979.nc", 20, digest, "u", "observed", 1979)
    assert local_status(partial, tmp_path, verify=True) is LocalStatus.PARTIAL

    missing = FileEntry("nope.nc", 1, digest, "u", "observed", 1979)
    assert local_status(missing, tmp_path, verify=True) is LocalStatus.MISSING
