#!/usr/bin/env python3
"""Assemble the static registry website and v1 API for publication."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

_PACKAGE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def build_site(root: Path, output: Path) -> None:
    root = root.resolve()
    output = output.resolve()
    web = root / "web"
    api = root / "generated" / "v1"

    if output == root or output in root.parents:
        raise ValueError("Output must not contain the registry repository")
    if not (web / "index.html").is_file():
        raise ValueError(f"Missing registry website: {web}")
    if not (api / "revision.json").is_file():
        raise ValueError(f"Missing generated registry API: {api}")

    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(web, output)
    shutil.copytree(api, output / "v1")
    for package_record in sorted((api / "package").glob("*.json")):
        package_name = package_record.stem
        if not _PACKAGE_NAME.fullmatch(package_name):
            raise ValueError(f"Invalid generated package name: {package_name}")
        route = output / "package" / package_name
        route.mkdir(parents=True)
        shutil.copy2(web / "index.html", route / "index.html")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Registry repository root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "site",
        help="Static publication directory",
    )
    args = parser.parse_args()
    try:
        build_site(args.root.expanduser(), args.output.expanduser())
    except ValueError as exc:
        parser.exit(1, f"registry site build failed: {exc}\n")
    print(f"Built registry site at {args.output.expanduser().resolve()}")


if __name__ == "__main__":
    main()
