"""Quick-look maps and series to eyeball pipeline outputs (matplotlib, dev dependency).

Usage: python scripts/plot_diagnostics.py [--source zenodo] [--world observed] [--year 2018]
"""

from __future__ import annotations

import argparse

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import xarray as xr  # noqa: E402

from earthburns import layout  # noqa: E402
from earthburns.build_mask import load_masks  # noqa: E402
from earthburns.config import load_config  # noqa: E402
from earthburns.thresholds import load_thresholds  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="zenodo")
    ap.add_argument("--world", default="observed")
    ap.add_argument("--year", type=int, default=2018)
    ap.add_argument("--month", type=int, default=7, help="1-12, month of the map")
    args = ap.parse_args()
    cfg = load_config()

    thr_files = sorted(cfg.paths.interim.glob(f"thresholds_{args.source}_*.nc"))
    counts_path = layout.monthly_path(cfg, args.source, args.world, args.year)
    extent_file = layout.extent_path(cfg, args.source, args.world, args.year)
    if not thr_files or not counts_path.is_file() or not extent_file.is_file():
        raise SystemExit("run the mask / thresholds / monthly steps first")

    burnable, _regions, _weights, _names = load_masks(layout.masks_path(cfg))
    thr = load_thresholds(thr_files[-1])["p90"]
    with xr.open_dataset(counts_path) as ds:
        counts = ds["days_gt_p90"].isel(time=args.month - 1).values
    table = pd.read_parquet(extent_file)

    fig, ax = plt.subplots(4, 1, figsize=(14, 24))
    ax[0].imshow(burnable, cmap="Greens", aspect="auto")
    ax[0].set_title("burnable mask")
    ax[1].imshow(np.where(burnable, thr, np.nan), cmap="inferno", vmin=0, vmax=60, aspect="auto")
    ax[1].set_title(f"p90 threshold ({thr_files[-1].name})")
    ax[2].imshow(np.where(burnable, counts, np.nan), cmap="magma", vmin=0, vmax=31, aspect="auto")
    ax[2].set_title(f"days > p90, {args.year}-{args.month:02d}, {args.world}")
    for name, sub in table.groupby("threshold"):
        ax[3].plot(sub["date"], 100 * sub["global"], label=f"{name} (total area)")
        ax[3].plot(
            sub["date"], 100 * sub["global"] / sub["coverage"], "--", alpha=0.6,
            label=f"{name} (observed area)",
        )
    p90 = table[table.threshold == "p90"]
    ax[3].plot(p90["date"], 100 * p90["coverage"], color="grey", lw=1, label="data coverage")
    ax[3].set_title(f"{args.year}: % of burnable area above threshold, and coverage")
    ax[3].legend(fontsize=8)
    ax[3].grid(alpha=0.3)
    plt.tight_layout()
    cfg.paths.processed.mkdir(parents=True, exist_ok=True)
    out = cfg.paths.processed / f"diagnostics_{args.source}_{args.world}_{args.year}.png"
    plt.savefig(out, dpi=60)
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
