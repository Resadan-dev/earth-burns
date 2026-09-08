"""``earthburns dryad status|download`` sub-command."""

from __future__ import annotations

import argparse
import logging
import os

import requests

from earthburns import dryad, sources
from earthburns.config import PipelineConfig

log = logging.getLogger("earthburns.dryad")


def token_from_env() -> str | None:
    """DRYAD_TOKEN, or a fresh token from DRYAD_CLIENT_ID + DRYAD_CLIENT_SECRET."""
    token = os.environ.get("DRYAD_TOKEN")
    if token:
        return token
    cid, secret = os.environ.get("DRYAD_CLIENT_ID"), os.environ.get("DRYAD_CLIENT_SECRET")
    if cid and secret:
        return dryad.fetch_token(cid, secret)
    return None


def cmd_dryad(cfg: PipelineConfig, args: argparse.Namespace) -> int:
    entries = dryad.download_order(
        dryad.fetch_manifest(cfg.dryad.version_id),
        (cfg.reference.first_year, cfg.reference.last_year),
    )
    if args.years:
        keep = set(sources.parse_years(args.years))
        entries = [e for e in entries if e.year is None or e.year in keep]
    dest = cfg.paths.raw_dryad

    if args.action == "status":
        counts: dict[str, int] = {}
        for e in entries:
            st = dryad.local_status(e, dest, verify=args.verify).value
            counts[st] = counts.get(st, 0) + 1
            log.info("%-28s %s", e.path, st)
        log.info("summary: %s", counts)
        return 0

    token = token_from_env()
    if not token:
        log.error("no Dryad token: set DRYAD_TOKEN or DRYAD_CLIENT_ID + DRYAD_CLIENT_SECRET "
                  "(see docs/01-data-sources.md)")
        return 2
    session = requests.Session()
    done = (dryad.LocalStatus.COMPLETE_UNVERIFIED, dryad.LocalStatus.VERIFIED)
    for e in entries:
        # --verify makes an already-present file prove its SHA-256 before it is
        # trusted; without it only the size is checked, as documented.
        status = dryad.local_status(e, dest, verify=args.verify)
        if status in done:
            log.info("%s already present (%s)", e.path, status.value)
            continue
        if status is dryad.LocalStatus.CORRUPT:
            log.warning("%s fails its checksum, downloading again", e.path)
            (dest / e.path).unlink()
        log.info("downloading %s (%.1f MB)", e.path, e.size / 1e6)
        st = dryad.download_entry(session, e, dest, token)
        log.info("%s -> %s", e.path, st.value)
        if st is dryad.LocalStatus.CORRUPT:
            log.error("checksum mismatch for %s; aborting", e.path)
            return 3
    return 0


def add_dryad_parser(sub: argparse._SubParsersAction) -> None:
    d = sub.add_parser("dryad", help="status / download of the Dryad dataset")
    d.add_argument("action", choices=("status", "download"))
    d.add_argument("--years", help="restrict to these years, e.g. 1991-2020")
    d.add_argument("--verify", action="store_true", help="check SHA-256 of present files")
    d.set_defaults(func=cmd_dryad)
