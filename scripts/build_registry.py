#!/usr/bin/env python3
"""Validate registry manifests and build the static v1 API."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import URLError
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import Request, urlopen

from kedi.package_manifest import load_package_manifest, parse_python_requirement
from markdown_it import MarkdownIt

NAME_RE = re.compile(r"[a-z][a-z0-9_]*")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
VERSION_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}")
PACKAGE_STATUSES = {"active", "yanked", "revoked"}
REVISION_STATUSES = {"superseded", "yanked", "revoked"}
MANIFEST_KEYS = {
    "schema_version",
    "name",
    "version",
    "description",
    "author",
    "repository",
    "verified_commit",
    "package_manifest_path",
    "status",
}
REVISION_KEYS = {"version", "repository", "verified_commit", "status"}
REVISION_OPTIONAL_KEYS = {"reason", "advisory_url"}
MAX_METADATA_BYTES = 256 * 1024


class BuildError(ValueError):
    """Raised when reviewed registry source does not satisfy the v1 contract."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BuildError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    _require_regular_file(path)
    if path.stat().st_size > MAX_METADATA_BYTES:
        raise BuildError(f"{path} exceeds {MAX_METADATA_BYTES} bytes")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"{path} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"{path} must contain a JSON object")
    return value


def _require_regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise BuildError(f"required regular file is missing: {path}")


def _require_exact_keys(
    value: dict[str, Any],
    required: set[str],
    *,
    optional: set[str] | None = None,
    source: str,
) -> None:
    allowed = required | (optional or set())
    missing = required - value.keys()
    unknown = value.keys() - allowed
    if missing:
        raise BuildError(f"{source} is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise BuildError(f"{source} has unknown fields: {', '.join(sorted(unknown))}")


def _string(value: Any, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise BuildError(f"{field} must be a non-empty, trimmed string")
    if len(value) > maximum:
        raise BuildError(f"{field} exceeds {maximum} characters")
    return value


def _https_url(value: Any, field: str) -> str:
    text = _string(value, field, maximum=2048)
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise BuildError(f"{field} must be a credential-free HTTPS URL")
    return text.rstrip("/")


def _manifest_path(value: Any) -> str:
    text = _string(value, "package_manifest_path", maximum=512)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or "\\" in text
        or any(character in text for character in "*?[")
        or path.name != "package.kedi"
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise BuildError("package_manifest_path must be a normalized package.kedi path")
    return path.as_posix()


def _manifest_record(package_dir: Path) -> tuple[dict[str, Any], str]:
    manifest_path = package_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    _require_exact_keys(manifest, MANIFEST_KEYS, source=str(manifest_path))
    if manifest["schema_version"] != 1:
        raise BuildError(f"{manifest_path} uses an unsupported schema version")

    name = _string(manifest["name"], "name", maximum=64)
    if NAME_RE.fullmatch(name) is None or name != package_dir.name:
        raise BuildError(f"package name {name!r} must be canonical and match {package_dir.name!r}")
    version = _string(manifest["version"], "version", maximum=64)
    if VERSION_RE.fullmatch(version) is None:
        raise BuildError(f"invalid package version: {version!r}")
    description = _string(manifest["description"], "description", maximum=240)

    author = manifest["author"]
    if not isinstance(author, dict):
        raise BuildError("author must be an object")
    _require_exact_keys(author, {"name", "contact"}, source="author")
    normalized_author = {
        "name": _string(author["name"], "author.name", maximum=120),
        "contact": _string(author["contact"], "author.contact", maximum=254),
    }

    repository = _https_url(manifest["repository"], "repository")
    commit = _string(manifest["verified_commit"], "verified_commit", maximum=40)
    if COMMIT_RE.fullmatch(commit) is None:
        raise BuildError("verified_commit must be a full lowercase Git commit ID")
    status = _string(manifest["status"], "status", maximum=16)
    if status not in PACKAGE_STATUSES:
        raise BuildError(f"unsupported package status: {status!r}")

    for filename in ("README.md", "LICENSE"):
        path = package_dir / filename
        _require_regular_file(path)
        if path.stat().st_size == 0 or path.stat().st_size > MAX_METADATA_BYTES:
            raise BuildError(f"{path} must contain 1..{MAX_METADATA_BYTES} bytes")

    digest = f"sha256:{hashlib.sha256(manifest_path.read_bytes()).hexdigest()}"
    return (
        {
            "schema_version": 1,
            "name": name,
            "version": version,
            "description": description,
            "author": normalized_author,
            "repository": repository,
            "verified_commit": commit,
            "package_manifest_path": _manifest_path(manifest["package_manifest_path"]),
            "status": status,
            "registry_manifest_digest": digest,
        },
        digest,
    )


def _historical_records(package_dir: Path, name: str) -> list[dict[str, Any]]:
    path = package_dir / "revisions.json"
    if not path.exists():
        return []
    ledger = _load_json(path)
    _require_exact_keys(ledger, {"schema_version", "revisions"}, source=str(path))
    if ledger["schema_version"] != 1 or not isinstance(ledger["revisions"], list):
        raise BuildError(f"{path} must contain a v1 revisions list")

    records: list[dict[str, Any]] = []
    for index, value in enumerate(ledger["revisions"]):
        source = f"{path}:revisions[{index}]"
        if not isinstance(value, dict):
            raise BuildError(f"{source} must be an object")
        _require_exact_keys(
            value,
            REVISION_KEYS,
            optional=REVISION_OPTIONAL_KEYS,
            source=source,
        )
        status = _string(value["status"], f"{source}.status", maximum=16)
        if status not in REVISION_STATUSES:
            raise BuildError(f"{source} has unsupported status {status!r}")
        commit = _string(value["verified_commit"], f"{source}.verified_commit", maximum=40)
        if COMMIT_RE.fullmatch(commit) is None:
            raise BuildError(f"{source} commit must be a full lowercase Git commit ID")
        version = _string(value["version"], f"{source}.version", maximum=64)
        if VERSION_RE.fullmatch(version) is None:
            raise BuildError(f"{source} has invalid version {version!r}")
        record: dict[str, Any] = {
            "name": name,
            "version": version,
            "repository": _https_url(value["repository"], f"{source}.repository"),
            "verified_commit": commit,
            "status": status,
        }
        if "reason" in value:
            record["reason"] = _string(value["reason"], f"{source}.reason", maximum=500)
        if "advisory_url" in value:
            record["advisory_url"] = _https_url(value["advisory_url"], f"{source}.advisory_url")
        records.append(record)
    return records


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def package_source_url(record: dict[str, Any], *, raw: bool = False) -> str:
    repository = urlsplit(record["repository"])
    parts = repository.path.strip("/").removesuffix(".git").split("/")
    if (
        repository.netloc != "github.com"
        or len(parts) != 2
        or any(re.fullmatch(r"[\w.-]+", part, flags=re.ASCII) is None for part in parts)
        or any(part in {".", ".."} for part in parts)
    ):
        raise BuildError("package metadata requires a GitHub owner/repository URL")
    base = "https://raw.githubusercontent.com" if raw else "https://github.com"
    commit = record["verified_commit"]
    path = quote(record["package_manifest_path"], safe="/")
    separator = "" if raw else "blob/"
    return f"{base}/{'/'.join(parts)}/{separator}{commit}/{path}"


def fetch_package_manifest(record: dict[str, Any]) -> str:
    """Read only the reviewed commit; never consult the default branch."""
    request = Request(package_source_url(record, raw=True), headers={"User-Agent": "kedi-registry"})
    try:
        with urlopen(request, timeout=20) as response:
            content = response.read(MAX_METADATA_BYTES + 1)
        if not content or len(content) > MAX_METADATA_BYTES:
            raise BuildError("package.kedi must contain 1..256 KiB")
        return content.decode("utf-8")
    except (URLError, TimeoutError, UnicodeError) as exc:
        raise BuildError(
            f"could not read verified package.kedi for {record['name']}: {exc}"
        ) from exc


def python_classifiers(requirement: str | None) -> list[str]:
    if requirement is None:
        return []
    lower, upper = parse_python_requirement(requirement)
    # A cross-major range does not specify which intermediate minor releases exist.
    if lower[0] != upper[0] or upper[1] - lower[1] > 100:
        return [f"Python {requirement.removeprefix('python@')}"]
    return [f"Python {lower[0]}"] + [
        f"Python {lower[0]}.{minor}" for minor in range(lower[1], upper[1] + 1)
    ]


def render_readme(text: str, *, file_base: str, image_base: str) -> str:
    parser = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    tokens = parser.parse(text)
    headings: set[str] = set()
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            title = "".join(
                child.content
                for child in tokens[index + 1].children or []
                if child.type in {"text", "code_inline", "image"}
            )
            slug = re.sub(r"[^\w\s-]", "", title.lower()).replace(" ", "-") or "section"
            identifier = f"readme-{slug}"
            count = 0
            while identifier in headings:
                count += 1
                identifier = f"readme-{slug}-{count}"
            headings.add(identifier)
            token.attrSet("id", identifier)
        if token.type in {"heading_open", "heading_close"}:
            token.tag = f"h{min(int(token.tag[1:]) + 1, 6)}"

    def resolve_links(items: list[Any]) -> None:
        for token in items:
            attribute = {"link_open": "href", "image": "src"}.get(token.type)
            if attribute:
                value = token.attrGet(attribute) or ""
                allowed = (
                    {"https", "http"} if attribute == "src" else {"https", "http", "mailto", ""}
                )
                try:
                    if attribute == "href" and value.startswith("#"):
                        target = "#readme-" + unquote(value[1:])
                    else:
                        target = urljoin(image_base if attribute == "src" else file_base, value)
                    parsed = urlsplit(target)
                    if parsed.scheme not in allowed or parsed.username or parsed.password:
                        target = ""
                except ValueError:
                    target = ""
                token.attrSet(attribute, target)
                if attribute == "src":
                    token.attrSet("loading", "lazy")
                    token.attrSet("referrerpolicy", "no-referrer")
                else:
                    token.attrSet("rel", "nofollow noreferrer")
            if token.children:
                resolve_links(token.children)

    resolve_links(tokens)
    return parser.renderer.render(tokens, parser.options, {})


def package_details(record: dict[str, Any], package_dir: Path, source: str) -> dict[str, Any]:
    try:
        with tempfile.TemporaryDirectory(prefix="registry-manifest-") as temporary:
            path = Path(temporary) / "package.kedi"
            path.write_text(source, encoding="utf-8")
            metadata = load_package_manifest(path)
        if metadata.name != record["name"] or metadata.version != record["version"]:
            raise BuildError(
                "package.kedi name/version does not match the reviewed registry record"
            )
        readme = (package_dir / "README.md").read_text(encoding="utf-8")
    except (ValueError, UnicodeError) as exc:
        raise BuildError(f"invalid package metadata for {record['name']}: {exc}") from exc

    revision = record["registry_revision"]
    ref = revision if COMMIT_RE.fullmatch(revision) else "main"
    file_base = f"https://github.com/kedi-lang/registry/blob/{ref}/packages/{record['name']}/"
    image_base = (
        f"https://raw.githubusercontent.com/kedi-lang/registry/{ref}/packages/{record['name']}/"
    )
    return {
        "schema_version": 1,
        "name": record["name"],
        "version": record["version"],
        "registry_revision": revision,
        "verified_commit": record["verified_commit"],
        "readme_url": file_base + "README.md",
        "readme_html": render_readme(readme, file_base=file_base, image_base=image_base),
        "license": metadata.license,
        "license_url": file_base + "LICENSE",
        "python_requirement": metadata.python_requirement,
        "python_classifiers": python_classifiers(metadata.python_requirement),
        "python_dependencies": metadata.python_dependencies,
        "source_directory": metadata.source,
        "package_manifest_url": package_source_url(record),
    }


def build_registry(root: Path, *, revision: str | None = None) -> str:
    packages_root = root / "packages"
    if not packages_root.is_dir():
        raise BuildError(f"package source directory is missing: {packages_root}")

    records: list[dict[str, Any]] = []
    audit_entries: list[dict[str, Any]] = []
    digests = [f"builder:{hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}"]
    sources: dict[str, str] = {}
    for package_dir in sorted(path for path in packages_root.iterdir() if path.is_dir()):
        if package_dir.is_symlink():
            raise BuildError(f"package directory may not be a symlink: {package_dir}")
        record, digest = _manifest_record(package_dir)
        sources[record["name"]] = fetch_package_manifest(record)
        records.append(record)
        digests.append(f"{record['name']}:{digest}")
        digests.append(hashlib.sha256(sources[record["name"]].encode()).hexdigest())
        for filename in ("README.md", "LICENSE", "revisions.json"):
            path = package_dir / filename
            if path.exists():
                _require_regular_file(path)
                digests.append(f"{filename}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
        audit_entries.append(
            {
                "name": record["name"],
                "version": record["version"],
                "repository": record["repository"],
                "verified_commit": record["verified_commit"],
                "status": record["status"],
            }
        )
        audit_entries.extend(_historical_records(package_dir, record["name"]))

    identities = [
        (entry["name"], entry["repository"], entry["verified_commit"]) for entry in audit_entries
    ]
    if len(identities) != len(set(identities)):
        raise BuildError("audit ledger contains duplicate package/repository/commit identities")

    if revision is None:
        payload = "\n".join(digests).encode()
        revision = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    revision = _string(revision, "registry revision", maximum=256)
    for record in records:
        record["registry_revision"] = revision

    output_root = root / "generated" / "v1"
    output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="registry-v1-", dir=output_root.parent) as temporary:
        stage = Path(temporary)
        _write_json(
            stage / "revision.json",
            {"schema_version": 1, "registry_revision": revision},
        )
        _write_json(
            stage / "index.json",
            {"schema_version": 1, "registry_revision": revision, "packages": records},
        )
        _write_json(
            stage / "audit.json",
            {
                "schema_version": 1,
                "registry_revision": revision,
                "entries": sorted(
                    audit_entries,
                    key=lambda entry: (
                        entry["name"],
                        entry["repository"],
                        entry["verified_commit"],
                    ),
                ),
            },
        )
        for record in records:
            _write_json(stage / "package" / f"{record['name']}.json", record)
            _write_json(
                stage / "details" / f"{record['name']}.json",
                package_details(record, packages_root / record["name"], sources[record["name"]]),
            )

        previous = output_root.with_name(".v1.previous")
        if previous.exists():
            shutil.rmtree(previous)
        if output_root.exists():
            output_root.rename(previous)
        stage.rename(output_root)
        if previous.exists():
            shutil.rmtree(previous)
    return revision


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Registry repository root",
    )
    parser.add_argument("--revision", help="Registry Git revision or publication ID")
    args = parser.parse_args()
    try:
        revision = build_registry(args.root.expanduser().resolve(), revision=args.revision)
    except BuildError as exc:
        parser.exit(1, f"registry build failed: {exc}\n")
    print(f"Built registry API at revision {revision}")


if __name__ == "__main__":
    main()
