"""Dryad client: manifest, download ordering, integrity checks, resumable downloads.

Dryad's file downloads require an API bearer token (obtained from an API application
created on the user's Dryad account, see docs/01-data-sources.md). Files placed by hand
in the destination folder are accepted as long as their SHA-256 matches the manifest.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import requests

API_BASE = "https://datadryad.org"
_OBSERVED = re.compile(r"^fwi_era5_(\d{4})\.nc$")
_COUNTERFACTUAL = re.compile(r"^fwi_era5_counter_(\d{4})\.nc$")
_WORLD_RANK = {"observed": 0, "counterfactual": 1}


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    sha256: str
    download_url: str
    world: str | None
    year: int | None


class LocalStatus(Enum):
    MISSING = "missing"
    PARTIAL = "partial"
    COMPLETE_UNVERIFIED = "complete-unverified"
    VERIFIED = "verified"
    CORRUPT = "corrupt"


def _classify(path: str) -> tuple[str | None, int | None]:
    if m := _COUNTERFACTUAL.match(path):
        return "counterfactual", int(m.group(1))
    if m := _OBSERVED.match(path):
        return "observed", int(m.group(1))
    return None, None


def parse_manifest(payload: dict) -> list[FileEntry]:
    entries = []
    for rec in payload.get("_embedded", {}).get("stash:files", []):
        if rec.get("digestType") != "sha-256":
            raise ValueError(f"{rec.get('path')}: unsupported digest type {rec.get('digestType')}")
        world, year = _classify(rec["path"])
        href = rec["_links"]["stash:download"]["href"]
        entries.append(
            FileEntry(
                path=rec["path"],
                size=int(rec["size"]),
                sha256=str(rec["digest"]).lower(),
                download_url=href if href.startswith("http") else API_BASE + href,
                world=world,
                year=year,
            )
        )
    return entries


def fetch_manifest(version_id: int, session: requests.Session | None = None) -> list[FileEntry]:
    s = session or requests.Session()
    entries: list[FileEntry] = []
    page = 1
    while True:
        r = s.get(f"{API_BASE}/api/v2/versions/{version_id}/files",
                  params={"page": page, "per_page": 100}, timeout=60)
        r.raise_for_status()
        batch = parse_manifest(r.json())
        entries.extend(batch)
        if len(batch) < 100:
            return entries
        page += 1


def download_order(
    entries: Iterable[FileEntry], reference_years: tuple[int, int]
) -> list[FileEntry]:
    """Small files first, then reference-period years (observed before counterfactual),
    then everything else, so the threshold step can start as early as possible."""
    first, last = reference_years

    def key(e: FileEntry):
        if e.world is None:
            return (0, 0, 0, e.path)
        in_ref = first <= (e.year or 0) <= last
        return (1 if in_ref else 2, e.year, _WORLD_RANK[e.world], e.path)

    return sorted(entries, key=key)


def sha256_of_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def local_status(entry: FileEntry, dest_dir: Path, verify: bool) -> LocalStatus:
    p = Path(dest_dir) / entry.path
    if not p.is_file():
        return LocalStatus.MISSING
    if p.stat().st_size < entry.size:
        return LocalStatus.PARTIAL
    if not verify:
        return LocalStatus.COMPLETE_UNVERIFIED
    return LocalStatus.VERIFIED if sha256_of_file(p) == entry.sha256 else LocalStatus.CORRUPT


def fetch_token(client_id: str, client_secret: str, session: requests.Session | None = None) -> str:
    s = session or requests.Session()
    r = s.post(f"{API_BASE}/oauth/token", timeout=60,
               data={"client_id": client_id, "client_secret": client_secret,
                     "grant_type": "client_credentials"})
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError("Dryad token endpoint returned no access_token")
    return str(token)


def download_entry(session: requests.Session, entry: FileEntry, dest_dir: Path, token: str,
                   chunk: int = 8 << 20) -> LocalStatus:
    """Download one file to ``<dest>/<name>.part`` with HTTP Range resume, verify, rename."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    final, part = dest_dir / entry.path, dest_dir / (entry.path + ".part")
    have = part.stat().st_size if part.is_file() else 0
    if have > entry.size:
        part.unlink()
        have = 0
    headers = {"Authorization": f"Bearer {token}"}
    if have:
        headers["Range"] = f"bytes={have}-"
    with session.get(entry.download_url, headers=headers, stream=True, timeout=120,
                     allow_redirects=True) as r:
        if r.status_code == 416:  # range not satisfiable: file already complete
            pass
        else:
            r.raise_for_status()
            mode = "ab" if (have and r.status_code == 206) else "wb"
            with open(part, mode) as fh:
                for block in r.iter_content(chunk_size=chunk):
                    fh.write(block)
    if sha256_of_file(part) != entry.sha256:
        part.unlink()
        return LocalStatus.CORRUPT
    part.replace(final)
    return LocalStatus.VERIFIED
