"""Compare the two worlds: annual series, growing gap, and where the gap sits.

Usage: python scripts/plot_two_worlds.py [--source dryad] [--threshold p90]
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


def annual(cfg, source: str, world: str, threshold: str) -> pd.Series:
    files = sorted(layout.monthly_dir(cfg).glob(f"{layout.prefix(source, world)}_*_extent.parquet"))
    if not files:
        raise SystemExit(f"no extent table for {source}/{world}; run the monthly pass first")
    table = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    sub = table[table["threshold"] == threshold].set_index("date").sort_index()
    return sub.groupby(sub.index.year)["global"].mean() * 100


def decade_mean_days(cfg, source: str, world: str, threshold: str, years: range) -> np.ndarray:
    """Mean days per year above the threshold, averaged over ``years``."""
    total = None
    for y in years:
        path = layout.monthly_path(cfg, source, world, y)
        if not path.is_file():
            continue
        with xr.open_dataset(path) as ds:
            year_total = ds[f"days_gt_{threshold}"].values.sum(axis=0).astype(np.float32)
        total = year_total if total is None else total + year_total
    return total / len(years)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="dryad")
    ap.add_argument("--threshold", default="p90")
    args = ap.parse_args()
    cfg = load_config()

    obs = annual(cfg, args.source, "observed", args.threshold)
    cfa = annual(cfg, args.source, "counterfactual", args.threshold)
    burnable, _regions, _weights, _names = load_masks(layout.masks_path(cfg))

    recent = range(max(obs.index) - 9, max(obs.index) + 1)
    d_obs = decade_mean_days(cfg, args.source, "observed", args.threshold, recent)
    d_cf = decade_mean_days(cfg, args.source, "counterfactual", args.threshold, recent)
    diff = np.where(burnable, d_obs - d_cf, np.nan)

    fig = plt.figure(figsize=(15, 13))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.1, 0.7, 1.6], hspace=0.28)

    ax = fig.add_subplot(gs[0])
    ax.plot(obs.index, obs.values, color="#c1272d", lw=2, label="our world")
    ax.plot(cfa.index, cfa.values, color="#3b6ea5", lw=2, label="without human-caused warming")
    ax.fill_between(obs.index, cfa.values, obs.values, color="#c1272d", alpha=0.18)
    ax.set_ylabel(f"% of burnable area above local {args.threshold}")
    ax.set_title(
        f"Extreme fire weather, {min(obs.index)}-{max(obs.index)} "
        f"({args.source}, reference {cfg.reference.first_year}-{cfg.reference.last_year})"
    )
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)

    ax = fig.add_subplot(gs[1])
    gap = obs - cfa
    ax.bar(gap.index, gap.values, color="#c1272d", width=0.85)
    ax.set_ylabel("gap, points")
    ax.set_title("How much of it is attributable to warming")
    ax.grid(alpha=0.3, axis="y")

    ax = fig.add_subplot(gs[2])
    lim = float(np.nanpercentile(np.abs(diff), 99))
    im = ax.imshow(diff, cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_title(
        f"Extra days per year above {args.threshold}, {recent.start}-{recent.stop - 1}: "
        "our world minus the world without warming"
    )
    ax.set_xticks([]), ax.set_yticks([])
    fig.colorbar(im, ax=ax, shrink=0.8, label="days per year")

    out = cfg.paths.processed / f"two_worlds_{args.source}_{args.threshold}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=70, bbox_inches="tight")
    print(f"written {out}")
    print(f"  {min(obs.index)}: observed {obs.iloc[0]:.2f}%  counterfactual {cfa.iloc[0]:.2f}%")
    print(f"  {max(obs.index)}: observed {obs.iloc[-1]:.2f}%  counterfactual {cfa.iloc[-1]:.2f}%")
    print(f"  mean extra days per year in the last decade: {np.nanmean(diff):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
