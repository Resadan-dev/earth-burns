"""Command-line entry point: ``earthburns <command> [options]``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from earthburns import build_mask, layout, monthly_run, pack, pack_run, sources, thresholds
from earthburns.cli_dryad import add_dryad_parser
from earthburns.config import WORLDS, PipelineConfig, load_config
from earthburns.extent import ExtentContext

log = logging.getLogger("earthburns")
DEFAULT_REGION_IDS = tuple(range(1, 15))  # the 14 GFED basis regions, ocean (0) excluded


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _load_context(cfg: PipelineConfig):
    """Extent context, region names and the raw burnable mask, from masks.nc."""
    burnable, regions, weights, names = build_mask.load_masks(layout.masks_path(cfg))
    ids = tuple(sorted(i for i in names if i != 0)) or DEFAULT_REGION_IDS
    return ExtentContext(burnable, weights, regions, ids), names, burnable


def cmd_mask(cfg: PipelineConfig, args: argparse.Namespace) -> int:
    ds = build_mask.build_masks(cfg.mask, cfg.paths.raw_gldas, cfg.paths.raw_gfed)
    out = layout.masks_path(cfg)
    build_mask.save_masks(ds, out)
    burn = ds["burnable"].values.astype(bool)
    w = ds["cell_weight"].values
    log.info(
        "burnable nodes: %d (%.1f%% of weighted global area) -> %s",
        int(burn.sum()),
        100.0 * float((w * burn).sum() / w.sum()),
        out,
    )
    return 0


def cmd_thresholds(cfg: PipelineConfig, args: argparse.Namespace) -> int:
    years = sources.parse_years(args.years) if args.years else tuple(cfg.reference.years)
    files = sources.year_files(
        cfg, args.source, "observed", years, allow_missing=args.allow_missing
    )
    if not files:
        log.error("no input files found")
        return 2
    log.info("pass 1 over %d file(s): %s ... %s", len(files), files[0].name, files[-1].name)
    result = thresholds.compute_thresholds(
        files,
        cfg.reference.quantiles,
        cfg.histogram,
        log.info,
        allow_incomplete=args.allow_incomplete,
    )
    out = layout.thresholds_path(cfg, args.source, years[0], years[-1])
    thresholds.save_thresholds(result, out)
    cov = result.coverage
    log.info("streamed %d days, %s to %s", cov.n_days, cov.first_date, cov.last_date)
    if cov.missing_days:
        log.warning("%d day(s) missing from the reference period", len(cov.missing_days))
    log.info("thresholds written to %s", out)
    if result.validation:
        v = result.validation
        for i, q in enumerate(result.quantiles):
            log.info(
                "validation %s on %d cells x %d days: max|err|=%.3f mean=%.4f p99=%.3f",
                thresholds.quantile_name(q),
                v.n_cells,
                v.n_samples,
                v.max_abs_error[i],
                v.mean_abs_error[i],
                v.p99_abs_error[i],
            )
    log.info("cells with overflow samples: %d", int(result.overflow.sum()))
    return 0


def cmd_monthly(cfg: PipelineConfig, args: argparse.Namespace) -> int:
    years = (
        sources.parse_years(args.years)
        if args.years
        else sources.default_years(cfg, args.source)
    )
    files = sources.year_files(
        cfg, args.source, args.world, years, allow_missing=args.allow_missing
    )
    if not files:
        log.error("no input files found")
        return 2
    thr = thresholds.load_thresholds(Path(args.thresholds))
    ctx, _names, _burnable = _load_context(cfg)
    pairs = [(sources.year_from_path(p), p) for p in files]
    done = monthly_run.run_years(
        pairs,
        thr,
        ctx,
        layout.monthly_dir(cfg),
        layout.prefix(args.source, args.world),
        log.info,
        require_complete=not args.allow_incomplete,
    )
    log.info("pass 2 finished for %d year(s): %s ... %s", len(done), done[0], done[-1])
    return 0


def cmd_pack(cfg: PipelineConfig, args: argparse.Namespace) -> int:
    """Turn the per-year outputs of one world into web blobs plus a manifest entry."""
    files = layout.monthly_years(cfg, args.source, args.world)
    if not files:
        log.error("no complete monthly year found for %s/%s", args.source, args.world)
        return 2
    ctx, names, burnable = _load_context(cfg)
    out = layout.web_dir(cfg, args.source)
    cells = pack_run.write_grid(out, burnable, force=args.force)
    thr_names = [thresholds.quantile_name(q) for q in cfg.reference.quantiles]

    entry = pack_run.pack_monthly(
        files, cells, out, args.world, thr_names, args.chunk_years, quality=args.quality
    )
    table = pd.concat(
        [
            pd.read_parquet(layout.extent_path(cfg, args.source, args.world, y))
            for y in sorted(files)
        ],
        ignore_index=True,
    )
    columns = monthly_run.extent_columns(ctx.region_ids)
    entry["extent"] = pack_run.pack_extent(
        table, out, args.world, columns, thr_names, quality=args.quality
    )
    entry["region_names"] = {str(i): names.get(i, "") for i in ctx.region_ids}

    manifest = pack_run.read_manifest(out)
    manifest.setdefault("worlds", {})[args.world] = entry
    manifest["source"] = args.source
    pack_run.write_manifest(out, manifest)
    blobs = list(out.rglob("*.br"))
    log.info(
        "web bundle for %s: %d blob(s), %.1f MB under %s",
        args.world,
        len(blobs),
        sum(p.stat().st_size for p in blobs) / 1e6,
        out,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="earthburns", description="Earth Burns data pipeline")
    p.add_argument("--config", type=Path, default=None, help="path to pipeline.toml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("mask", help="build burnable mask + GFED regions").set_defaults(func=cmd_mask)

    t = sub.add_parser("thresholds", help="pass 1: local percentiles over the reference years")
    t.add_argument("--source", choices=sources.SOURCES, default="dryad")
    t.add_argument("--years", help="e.g. 1991-2020 (default: reference period)")
    t.add_argument("--allow-missing", action="store_true", help="skip absent yearly files")
    t.add_argument("--allow-incomplete", action="store_true", help="accept missing days")
    t.set_defaults(func=cmd_thresholds)

    m = sub.add_parser("monthly", help="pass 2: monthly exceedance counts + daily extent")
    m.add_argument("--source", choices=sources.SOURCES, default="dryad")
    m.add_argument("--world", choices=WORLDS, default="observed")
    m.add_argument("--years", help="e.g. 1979-2024 (default: every year of the source)")
    m.add_argument("--thresholds", required=True, help="thresholds NetCDF from pass 1")
    m.add_argument("--allow-missing", action="store_true")
    m.add_argument("--allow-incomplete", action="store_true", help="accept partial years")
    m.set_defaults(func=cmd_monthly)

    k = sub.add_parser("pack", help="assemble monthly outputs into web-ready brotli blobs")
    k.add_argument("--source", choices=sources.SOURCES, default="dryad")
    k.add_argument("--world", choices=WORLDS, default="observed")
    k.add_argument("--chunk-years", type=int, default=10, help="years per blob (>= 1)")
    k.add_argument(
        "--quality", type=int, default=pack.DEFAULT_QUALITY, help="brotli level, 0 to 11"
    )
    k.add_argument(
        "--force", action="store_true", help="rewrite the cell index even if blobs exist"
    )
    k.set_defaults(func=cmd_pack)

    add_dryad_parser(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    cfg = load_config(args.config)
    return int(args.func(cfg, args))


if __name__ == "__main__":
    sys.exit(main())
