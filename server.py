#!/usr/bin/env python3
"""Serve the Kedi registry UI and generated API on loopback."""

from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class RegistryHandler(SimpleHTTPRequestHandler):
    web_root: Path
    api_root: Path

    def do_GET(self) -> None:
        route = urlsplit(self.path).path
        if route.startswith("/v1/"):
            self.directory = str(self.api_root)
            self.path = route.removeprefix("/v1") or "/"
        elif route == "/" or route.startswith("/package/"):
            self.directory = str(self.web_root)
            self.path = "/index.html"
        else:
            self.directory = str(self.web_root)
            self.path = route
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Registry repository root",
    )
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    web_root = root / "web"
    api_root = root / "generated" / "v1"
    if not (web_root / "index.html").is_file() or not api_root.is_dir():
        parser.error(f"{root} is not a built registry repository")

    handler = type(
        "ConfiguredRegistryHandler",
        (RegistryHandler,),
        {"web_root": web_root, "api_root": api_root},
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Kedi registry: http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
