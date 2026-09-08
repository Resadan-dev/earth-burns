"""Web packing: shared cell index, gap-free layouts, configured thresholds."""

import json
from pathlib import Path

import brotli
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from earthburns.grid import N_LAT, N_LON, canonical_grid
from earthburns.pack import unpack_frames
from earthburns.pack_run import pack_extent, pack_monthly, write_grid, write_manifest

THR = ("p90", "p95", "p99")


def _monthly_file(path: Path, year: int, value: int) -> None:
    lat, lon = canonical_grid()
    months = np.array([np.datetime64(f"{year}-{m:02d}-01", "D") for m in range(1, 13)])
    data = {
        f"days_gt_{t}": (("time", "lat", "lon"), np.full((12, N_LAT, N_LON), value, np.uint8))
        for t in THR
    }
    xr.Dataset(data, coords={"time": months, "lat": lat, "lon": lon}).to_netcdf(path)


def _mask():
    burnable = np.zeros((N_LAT, N_LON), bool)
    burnable[100:110, 200:260] = True
    return burnable


def _years(tmp_path: Path, years):
    files = {}
    for i, y in enumerate(years):
        files[y] = tmp_path / f"m_{y}.nc"
        _monthly_file(files[y], y, i + 1)
    return files


def test_pack_monthly_writes_chunk_blobs_that_roundtrip(tmp_path: Path):
    cells = write_grid(tmp_path / "web", _mask())
    assert json.loads((tmp_path / "web" / "grid.json").read_text())["n_cells"] == 600
    files = _years(tmp_path, (2001, 2002, 2003))
    manifest = pack_monthly(files, cells, tmp_path / "web", "observed", THR, chunk_years=2)
    blobs = manifest["thresholds"]["p90"]
    assert [(b["first_year"], b["n_months"]) for b in blobs] == [(2001, 24), (2003, 12)]
    assert manifest["n_cells"] == 600
    blob = (tmp_path / "web" / blobs[0]["file"]).read_bytes()
    frames = unpack_frames(blob, 24, cells, (N_LAT, N_LON))
    assert frames[0, 105, 230] == 1 and frames[23, 105, 230] == 2 and frames[0, 0, 0] == 0


def test_pack_monthly_rejects_gaps_and_bad_chunk_size(tmp_path: Path):
    cells = write_grid(tmp_path / "web", _mask())
    files = _years(tmp_path, (2001, 2002, 2004))
    with pytest.raises(ValueError, match="missing between"):
        pack_monthly(files, cells, tmp_path / "web", "observed", THR, chunk_years=2)
    ok = _years(tmp_path, (2001, 2002))
    for bad in (0, -1):
        with pytest.raises(ValueError, match="chunk_years"):
            pack_monthly(ok, cells, tmp_path / "web", "observed", THR, chunk_years=bad)


def test_pack_monthly_reports_a_missing_threshold_variable(tmp_path: Path):
    cells = write_grid(tmp_path / "web", _mask())
    files = _years(tmp_path, (2001,))
    with pytest.raises(ValueError, match="days_gt_p50"):
        pack_monthly(files, cells, tmp_path / "web", "observed", ("p50",))


def test_write_grid_refuses_to_invalidate_existing_blobs(tmp_path: Path):
    web = tmp_path / "web"
    cells = write_grid(web, _mask())
    files = _years(tmp_path, (2001,))
    entry = pack_monthly(files, cells, web, "observed", THR)
    write_manifest(web, {"worlds": {"observed": entry}})

    bigger = _mask()
    bigger[120:130, 200:260] = True
    with pytest.raises(ValueError, match="already packed"):
        write_grid(web, bigger)
    assert write_grid(web, bigger, force=True).size == 1200


def _rows(dates, thresholds=THR, cols=("global", "coverage", "region_1", "region_1_cov")):
    rows = []
    for t in thresholds:
        for i, d in enumerate(dates):
            rows.append({"date": pd.Timestamp(d), "threshold": t,
                         **{c: 0.1 + 0.001 * i for c in cols}})
    return pd.DataFrame(rows)


def test_pack_extent_scales_to_uint16(tmp_path: Path):
    cols = ["global", "coverage", "region_1", "region_1_cov"]
    table = _rows(["2001-01-01", "2001-01-02"])
    meta = pack_extent(table, tmp_path / "web", "observed", cols, THR)
    raw = brotli.decompress((tmp_path / "web" / meta["file"]).read_bytes())
    cube = np.frombuffer(raw, dtype=np.uint16).reshape(meta["shape"])
    assert cube.shape == (2, 3, 4)
    assert cube[0, 0, 0] == 1000 and cube[1, 0, 0] == 1010
    assert meta["first_date"] == "2001-01-01" and meta["columns"] == cols


def test_pack_extent_ships_the_date_axis_so_a_gap_stays_readable(tmp_path: Path):
    """Leap years in the Dryad files have no 31 December; the offsets say so."""
    cols = ["global", "coverage", "region_1", "region_1_cov"]
    gapped = _rows(["2001-01-01", "2001-01-02", "2001-01-04"])
    meta = pack_extent(gapped, tmp_path / "web", "observed", cols, THR)
    assert meta["n_days"] == 3 and meta["gaps"] == 1
    raw = brotli.decompress((tmp_path / "web" / meta["days_file"]).read_bytes())
    assert np.frombuffer(raw, dtype=np.int32).tolist() == [0, 1, 3]


def test_pack_extent_rejects_a_threshold_missing_days(tmp_path: Path):
    cols = ["global", "coverage", "region_1", "region_1_cov"]
    table = _rows(["2001-01-01", "2001-01-02"])
    short = table.drop(table[(table.threshold == "p95") & (table.date == "2001-01-02")].index)
    with pytest.raises(ValueError, match="rows for"):
        pack_extent(short, tmp_path / "web", "observed", cols, THR)
