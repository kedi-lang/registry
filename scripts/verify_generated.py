#!/usr/bin/env python3
"""Verify cross-file consistency of the committed registry snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def verify_snapshot(api: Path) -> None:
    revision = _load(api / "revision.json").get("registry_revision")
    if not isinstance(revision, str) or not revision:
        raise ValueError("revision.json must contain a registry_revision")

    index = _load(api / "index.json")
    packages = index.get("packages")
    if not isinstance(packages, list):
        raise ValueError("index.json must contain a packages list")

    names: set[str] = set()
    for summary in packages:
        if not isinstance(summary, dict) or not isinstance(summary.get("name"), str):
            raise ValueError("Every index package must have a name")
        name = summary["name"]
        if name in names:
            raise ValueError(f"Duplicate package in index: {name}")
        names.add(name)
        for directory in ("package", "details"):
            record = _load(api / directory / f"{name}.json")
            if record.get("name") != name:
                raise ValueError(f"Package name mismatch in {directory}/{name}.json")
            if record.get("registry_revision") != revision:
                raise ValueError(f"Registry revision mismatch in {directory}/{name}.json")

    audit = _load(api / "audit.json")
    if audit.get("registry_revision") != revision:
        raise ValueError("Registry revision mismatch in audit.json")
    entries = audit.get("entries")
    if not isinstance(entries, list):
        raise ValueError("audit.json must contain an entries list")
    audit_names = {
        entry.get("name")
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    if audit_names != names:
        raise ValueError("Audit and index package names do not match")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    verify_snapshot(root / "generated" / "v1")
    print("Registry snapshot is internally consistent")


if __name__ == "__main__":
    main()
