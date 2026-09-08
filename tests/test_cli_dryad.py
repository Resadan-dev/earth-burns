"""The dryad sub-command: status, verification and the download loop (no network)."""

import hashlib
from pathlib import Path

import pytest

from earthburns import cli_dryad, dryad
from earthburns.cli import main


class _FakeSession:
    """Serves file bodies from a dict, honouring Range like a well-behaved server."""

    def __init__(self, bodies: dict[str, bytes]):
        self.bodies = bodies
        self.calls: list[tuple[str, str | None]] = []

    def get(self, url, headers=None, stream=False, timeout=None, allow_redirects=True):
        body = self.bodies[url]
        rng = (headers or {}).get("Range")
        self.calls.append((url, rng))
        status = 200
        if rng:
            start = int(rng.removeprefix("bytes=").rstrip("-"))
            body, status = body[start:], 206
        return _FakeResponse(body, status)


class _FakeResponse:
    def __init__(self, body: bytes, status: int):
        self.content, self.status_code = body, status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=1):
        yield self.content


def _entry(name: str, body: bytes, year: int | None = 1991) -> dryad.FileEntry:
    return dryad.FileEntry(
        path=name,
        size=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        download_url=f"https://example.invalid/{name}",
        world="observed" if year else None,
        year=year,
    )


def test_download_entry_writes_verifies_and_renames(tmp_path: Path):
    body = b"x" * 4096
    entry = _entry("fwi_era5_1991.nc", body)
    session = _FakeSession({entry.download_url: body})
    assert dryad.download_entry(session, entry, tmp_path, "tok") is dryad.LocalStatus.VERIFIED
    assert (tmp_path / entry.path).read_bytes() == body
    assert not (tmp_path / (entry.path + ".part")).exists()


def test_download_entry_resumes_from_a_partial_file(tmp_path: Path):
    body = b"y" * 4096
    entry = _entry("fwi_era5_1992.nc", body)
    (tmp_path / (entry.path + ".part")).write_bytes(body[:1000])
    session = _FakeSession({entry.download_url: body})
    assert dryad.download_entry(session, entry, tmp_path, "tok") is dryad.LocalStatus.VERIFIED
    assert session.calls[0][1] == "bytes=1000-"
    assert (tmp_path / entry.path).read_bytes() == body


def test_download_entry_reports_a_checksum_mismatch(tmp_path: Path):
    entry = _entry("fwi_era5_1993.nc", b"z" * 100)
    session = _FakeSession({entry.download_url: b"w" * 100})
    assert dryad.download_entry(session, entry, tmp_path, "tok") is dryad.LocalStatus.CORRUPT
    assert not (tmp_path / (entry.path + ".part")).exists()


def _patch(monkeypatch, entries, session):
    monkeypatch.setattr(dryad, "fetch_manifest", lambda version_id, **kw: entries)
    monkeypatch.setattr(cli_dryad, "token_from_env", lambda: "token")
    monkeypatch.setattr(cli_dryad.requests, "Session", lambda: session, raising=False)


def test_download_reredownloads_a_file_that_fails_verification(
    monkeypatch, config_file, sandbox_cfg, caplog
):
    import requests

    good = b"g" * 512
    entry = _entry("fwi_era5_1994.nc", good)
    (sandbox_cfg.paths.raw_dryad / entry.path).write_bytes(b"b" * 512)  # same size, wrong content
    session = _FakeSession({entry.download_url: good})
    monkeypatch.setattr(dryad, "fetch_manifest", lambda version_id, **kw: [entry])
    monkeypatch.setattr(cli_dryad, "token_from_env", lambda: "token")
    monkeypatch.setattr(requests, "Session", lambda: session)

    # without --verify the wrong file is trusted because its size matches
    assert main(["--config", str(config_file), "dryad", "download"]) == 0
    assert (sandbox_cfg.paths.raw_dryad / entry.path).read_bytes() == b"b" * 512

    # with --verify it is detected and fetched again
    assert main(["--config", str(config_file), "dryad", "download", "--verify"]) == 0
    assert (sandbox_cfg.paths.raw_dryad / entry.path).read_bytes() == good


def test_status_lists_every_entry(monkeypatch, config_file, sandbox_cfg, caplog):
    entry = _entry("fwi_era5_1995.nc", b"k" * 32)
    monkeypatch.setattr(dryad, "fetch_manifest", lambda version_id, **kw: [entry])
    with caplog.at_level("INFO"):
        assert main(["--config", str(config_file), "dryad", "status"]) == 0
    assert "missing" in caplog.text


def test_download_without_a_token_fails_cleanly(monkeypatch, config_file):
    monkeypatch.setattr(dryad, "fetch_manifest", lambda version_id, **kw: [])
    monkeypatch.setattr(cli_dryad, "token_from_env", lambda: None)
    assert main(["--config", str(config_file), "dryad", "download"]) == 2


def test_token_from_env_prefers_an_explicit_token(monkeypatch):
    monkeypatch.setenv("DRYAD_TOKEN", "abc")
    assert cli_dryad.token_from_env() == "abc"
    monkeypatch.delenv("DRYAD_TOKEN")
    monkeypatch.setenv("DRYAD_CLIENT_ID", "id")
    monkeypatch.setenv("DRYAD_CLIENT_SECRET", "secret")
    monkeypatch.setattr(dryad, "fetch_token", lambda cid, sec, session=None: f"minted-{cid}")
    assert cli_dryad.token_from_env() == "minted-id"
    monkeypatch.delenv("DRYAD_CLIENT_ID")
    assert cli_dryad.token_from_env() is None


def test_fetch_token_requires_an_access_token():
    class S:
        def post(self, url, timeout=None, data=None):
            return _TokenResponse({})

    with pytest.raises(RuntimeError, match="access_token"):
        dryad.fetch_token("id", "secret", S())


class _TokenResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload
