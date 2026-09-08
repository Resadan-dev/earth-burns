"""Static server for the Earth Burns bundle.

The frame blobs are brotli-compressed on disk. Serving them with
``Content-Encoding: br`` lets the browser decompress them itself, so the client
gets plain bytes from ``fetch`` with no JavaScript decoder and no extra copy.

Usage: python scripts/serve_web.py [--port 8000] [--source dryad]
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
from pathlib import Path

from earthburns.config import load_config

TYPES = {".json": "application/json", ".js": "text/javascript", ".css": "text/css",
         ".html": "text/html", ".bin": "application/octet-stream"}


class Server(socketserver.ThreadingTCPServer):
    """Threaded: the client fetches several multi-megabyte blobs at once, and a
    single-threaded server would make them queue behind each other."""

    allow_reuse_address = True
    daemon_threads = True


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the app from web/ and the bundle from data/web/<source>/ under /data."""

    protocol_version = "HTTP/1.1"
    web_root: Path
    data_root: Path

    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        root = self.data_root if clean.startswith("data/") else self.web_root
        rel = clean[len("data/"):] if clean.startswith("data/") else clean
        target = (root / (rel or "index.html")).resolve()
        # never serve outside the two roots, whatever the request contains
        roots = (self.web_root.resolve(), self.data_root.resolve())
        if not any(str(target).startswith(str(r)) for r in roots):
            return str(self.web_root / "index.html")
        return str(target)

    def guess_type(self, path):  # noqa: N802 - base class spelling
        suffixes = Path(path).suffixes
        stem = suffixes[-2] if suffixes[-1] == ".br" and len(suffixes) > 1 else suffixes[-1]
        return TYPES.get(stem, "application/octet-stream")

    def end_headers(self) -> None:
        if self.path.split("?")[0].endswith(".br"):
            self.send_header("Content-Encoding", "br")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        if "404" in (fmt % args) or "500" in (fmt % args):
            super().log_message(fmt, *args)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--source", default="dryad")
    args = ap.parse_args()
    cfg = load_config()
    root = Path(__file__).resolve().parent.parent
    handler = functools.partial(Handler)
    Handler.web_root = root / "web"
    Handler.data_root = cfg.paths.web / args.source
    if not (Handler.data_root / "manifest.json").is_file():
        raise SystemExit(f"no bundle at {Handler.data_root}; run `earthburns pack` first")
    with Server(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving {Handler.web_root} and {Handler.data_root} on http://127.0.0.1:{args.port}")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
