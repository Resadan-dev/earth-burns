"""Assemble the per-year outputs of one world into web-ready blobs.

Outputs (under ``data/web``):

- ``grid.json``            grid description and burnable cell count
- ``cells.bin.br``         int32 row-major indices of the burnable cells (brotli)
- ``<world>/<thr>/<y0>-<y1>.bin.br``  uint8 frames (n_months, n_cells), one blob per chunk
- ``extent/<world>.bin.br`` uint16 daily values x 10000
- ``manifest.json``        everything the client needs to locate and decode the blobs

Two rules are enforced rather than papered over: the cell index is shared by every
blob, so it may not change while blobs from an earlier index are still listed; and
the frame and extent series must be gap-free, because their layout is positional.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from itertools import batched
from pathlib import Path

import brotli
import numpy as np
import pandas as pd
import xarray as xr

from earthburns.grid import N_LAT, N_LON, STEP, canonical_grid
from earthburns.pack import DEFAULT_QUALITY, build_cell_index, compress_cell_frames

EXTENT_SCALE = 10_000


def write_grid(out_dir: Path, burnable: np.ndarray, force: bool = False) -> np.ndarray:
    """Write the shared cell index, refusing to invalidate blobs already packed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = build_cell_index(burnable)
    grid_path = out_dir / "grid.json"
    if grid_path.is_file() and not force:
        previous = json.loads(grid_path.read_text(encoding="utf-8"))
        listed = read_manifest(out_dir).get("worlds", {})
        if listed and int(previous.get("n_cells", -1)) != int(cells.size):
            raise ValueError(
                f"the burnable mask changed ({previous.get('n_cells')} -> {cells.size} cells) "
                f"but {sorted(listed)} already packed against the old index; "
                "repack every world (or delete data/web) so the bundle stays consistent"
            )
    lat, lon = canonical_grid()
    (out_dir / "cells.bin.br").write_bytes(brotli.compress(cells.tobytes(), quality=11))
    grid_path.write_text(
        json.dumps(
            {
                "nlat": N_LAT,
                "nlon": N_LON,
                "lat0": float(lat[0]),
                "lon0": float(lon[0]),
                "step": STEP,
                "n_cells": int(cells.size),
                "cells_dtype": "int32",
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return cells


def _require_contiguous(years: Sequence[int]) -> list[int]:
    ys = sorted(years)
    gaps = [y for y in range(ys[0], ys[-1] + 1) if y not in set(ys)]
    if gaps:
        raise ValueError(
            f"years {gaps[:5]} are missing between {ys[0]} and {ys[-1]}; the web layout is "
            "positional, so run the monthly pass for them before packing"
        )
    return ys


def pack_monthly(
    files_by_year: dict[int, Path],
    cells: np.ndarray,
    out_dir: Path,
    world: str,
    thresholds: Sequence[str],
    chunk_years: int = 10,
    quality: int = DEFAULT_QUALITY,
) -> dict:
    """One brotli blob per (threshold, chunk of years); returns the manifest fragment."""
    if chunk_years < 1:
        raise ValueError(f"chunk_years must be >= 1, got {chunk_years}")
    if not thresholds:
        raise ValueError("no thresholds to pack")
    years = _require_contiguous(files_by_year)
    manifest: dict = {
        "years": [years[0], years[-1]],
        "n_cells": int(len(cells)),
        "days_observed": _days_observed(files_by_year, years),
        "thresholds": {},
    }
    for thr in thresholds:
        blobs = []
        for chunk in batched(years, chunk_years):
            arr = np.concatenate([_year_frames(files_by_year[y], thr, cells) for y in chunk])
            rel = Path(world) / thr / f"{chunk[0]}-{chunk[-1]}.bin.br"
            (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (out_dir / rel).write_bytes(compress_cell_frames(arr, quality=quality))
            blobs.append(
                {"file": rel.as_posix(), "first_year": chunk[0], "n_months": int(arr.shape[0])}
            )
        manifest["thresholds"][thr] = blobs
    return manifest


def _days_observed(files_by_year: dict[int, Path], years: Sequence[int]) -> list[int]:
    """Days behind each monthly frame, so a count is read against its own denominator."""
    out: list[int] = []
    for y in years:
        with xr.open_dataset(files_by_year[y]) as ds:
            if "days_observed" in ds.data_vars:
                out.extend(int(v) for v in ds["days_observed"].values)
            else:
                out.extend([0] * 12)
    return out


def _year_frames(path: Path, threshold: str, cells: np.ndarray) -> np.ndarray:
    """The 12 monthly frames of one year, already reduced to the burnable cells."""
    var = f"days_gt_{threshold}"
    with xr.open_dataset(path) as ds:
        if var not in ds.data_vars:
            raise ValueError(f"{path.name}: no variable {var!r} (has {list(ds.data_vars)})")
        arr = ds[var].values
        if arr.shape != (12, N_LAT, N_LON):
            raise ValueError(
                f"{path.name}: {var} has shape {arr.shape}, expected (12, {N_LAT}, {N_LON})"
            )
        return arr.reshape(12, -1)[:, cells].astype(np.uint8)


def pack_extent(
    table: pd.DataFrame,
    out_dir: Path,
    world: str,
    columns: Sequence[str],
    thresholds: Sequence[str],
    quality: int = DEFAULT_QUALITY,
) -> dict:
    """Daily values as uint16 x 10000, with an explicit date axis.

    The day offsets are shipped rather than assumed: the Dryad files carry 365 steps
    every year, so leap years have no 31 December and a purely positional layout would
    silently slide every later day by one.
    """
    dates = pd.DatetimeIndex(np.sort(table["date"].unique()))
    if dates.empty:
        raise ValueError("the extent table is empty")
    offsets = ((dates - dates[0]).days).to_numpy(dtype=np.int32)
    cube = np.zeros((len(dates), len(thresholds), len(columns)), dtype=np.uint16)
    for ti, thr in enumerate(thresholds):
        sub = table[table["threshold"] == thr]
        if len(sub) != len(dates):
            raise ValueError(
                f"threshold {thr!r} has {len(sub)} rows for {len(dates)} days; "
                "every threshold must cover exactly the same days"
            )
        vals = sub.set_index("date").reindex(dates)[list(columns)].to_numpy(dtype=np.float64)
        # NaN means "no burnable area in this region", the one documented empty case.
        cube[:, ti, :] = np.rint(np.clip(np.nan_to_num(vals, nan=0.0), 0.0, 1.0) * EXTENT_SCALE)

    rel = Path("extent") / f"{world}.bin.br"
    rel_days = Path("extent") / f"{world}_days.bin.br"
    (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    (out_dir / rel).write_bytes(brotli.compress(cube.tobytes(), quality=quality))
    (out_dir / rel_days).write_bytes(brotli.compress(offsets.tobytes(), quality=quality))
    gaps = int((np.diff(offsets) != 1).sum()) if offsets.size > 1 else 0
    return {
        "file": rel.as_posix(),
        "days_file": rel_days.as_posix(),
        "days_dtype": "int32",
        "dtype": "uint16",
        "scale": EXTENT_SCALE,
        "shape": list(cube.shape),
        "thresholds": list(thresholds),
        "columns": list(columns),
        "first_date": str(dates[0].date()),
        "last_date": str(dates[-1].date()),
        "n_days": int(len(dates)),
        "gaps": gaps,
    }


def write_manifest(out_dir: Path, manifest: dict) -> None:
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def read_manifest(out_dir: Path) -> dict:
    p = out_dir / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"worlds": {}}
