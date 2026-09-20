from __future__ import annotations

import importlib.util
import json
import threading
import unittest
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load_module("registry_builder", ROOT / "scripts" / "build_registry.py")
server_module = _load_module("registry_server", ROOT / "server.py")

PACKAGE_SOURCE = """> package: tmdb:
  author: Kedi Community
  version: 0.1.0
  source: src/tmdb
  python: python@3.11-3.13
  license: MIT
  python_dependencies:
    httpx>=0.27
    pydantic>=2
"""


class Elements(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def _write_package(root: Path, *, name: str = "tmdb") -> None:
    package = root / "packages" / name
    package.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "name": name,
        "version": "0.1.0",
        "description": "Search films and retrieve structured movie details.",
        "author": {"name": "Kedi Community", "contact": "packages@kedi-lang.org"},
        "repository": "https://github.com/kedi-lang/example-package",
        "verified_commit": "a" * 40,
        "package_manifest_path": "package.kedi",
        "status": "active",
    }
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "README.md").write_text("# tmdb\n", encoding="utf-8")
    (package / "LICENSE").write_text("MIT\n", encoding="utf-8")


class RegistryBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        loader = patch.object(builder, "fetch_package_manifest", return_value=PACKAGE_SOURCE)
        self.loader = loader.start()
        self.addCleanup(loader.stop)

    def test_builds_package_index_and_audit_records(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_package(root)

            revision = builder.build_registry(root, revision="test-revision")

            self.assertEqual(revision, "test-revision")
            package = json.loads((root / "generated/v1/package/tmdb.json").read_text())
            index = json.loads((root / "generated/v1/index.json").read_text())
            audit = json.loads((root / "generated/v1/audit.json").read_text())
            pointer = json.loads((root / "generated/v1/revision.json").read_text())
            self.assertEqual(pointer, {"schema_version": 1, "registry_revision": revision})
            self.assertEqual(package["verified_commit"], "a" * 40)
            self.assertEqual(package["registry_revision"], "test-revision")
            self.assertEqual(index["packages"], [package])
            self.assertEqual(audit["entries"][0]["status"], "active")
            details = json.loads((root / "generated/v1/details/tmdb.json").read_text())
            self.assertEqual(details["license"], "MIT")
            self.assertEqual(details["source_directory"], "src/tmdb")
            self.assertEqual(details["python_dependencies"], ["httpx>=0.27", "pydantic>=2"])
            self.assertEqual(
                details["python_classifiers"],
                ["Python 3", "Python 3.11", "Python 3.12", "Python 3.13"],
            )
            self.assertEqual(details["registry_revision"], package["registry_revision"])
            self.assertIn('<h2 id="readme-tmdb">tmdb</h2>', details["readme_html"])
            self.assertEqual(
                set(package),
                builder.MANIFEST_KEYS | {"registry_revision", "registry_manifest_digest"},
            )
            self.assertNotIn("details", audit["entries"][0])

    def test_missing_metadata_is_not_guessed_from_license_file(self) -> None:
        self.loader.return_value = "> package: tmdb:\n  version: 0.1.0\n  source: src/tmdb\n"
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_package(root)
            builder.build_registry(root)
            details = json.loads((root / "generated/v1/details/tmdb.json").read_text())
            self.assertIsNone(details["license"])
            self.assertIsNone(details["python_requirement"])
            self.assertEqual(details["python_classifiers"], [])
            self.assertEqual(details["python_dependencies"], [])

    def test_rejects_mismatched_or_executable_source_without_replacing_output(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_package(root)
            builder.build_registry(root, revision="before")
            before = (root / "generated/v1/index.json").read_bytes()
            for source in (
                PACKAGE_SOURCE.replace("tmdb:", "movies:"),
                PACKAGE_SOURCE.replace("0.1.0", "0.2.0"),
                PACKAGE_SOURCE + "\n[x: int] = `1`\n",
                PACKAGE_SOURCE.replace("python@3.11-3.13", "python@3.13-3.11"),
            ):
                with self.subTest(source=source):
                    self.loader.return_value = source
                    with self.assertRaises(builder.BuildError):
                        builder.build_registry(root, revision="after")
                    self.assertEqual((root / "generated/v1/index.json").read_bytes(), before)

    def test_readme_and_license_changes_update_revision(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_package(root)
            revisions = [builder.build_registry(root)]
            for filename in ("README.md", "LICENSE"):
                (root / "packages/tmdb" / filename).write_text("Changed content", encoding="utf-8")
                revisions.append(builder.build_registry(root))
            self.assertEqual(len(set(revisions)), 3)
            self.assertEqual(builder.build_registry(root), revisions[-1])

    def test_git_revision_pins_documentation_links(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_package(root)
            builder.build_registry(root, revision="b" * 40)
            details = json.loads((root / "generated/v1/details/tmdb.json").read_text())
            self.assertIn(f"/blob/{'b' * 40}/", details["readme_url"])
            self.assertIn(f"/blob/{'a' * 40}/", details["package_manifest_url"])

    def test_invalid_readme_does_not_replace_existing_build(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_package(root)
            builder.build_registry(root, revision="before")
            (root / "packages/tmdb/README.md").write_bytes(b"\xff")
            with self.assertRaisesRegex(builder.BuildError, "invalid package metadata"):
                builder.build_registry(root)
            index = json.loads((root / "generated/v1/index.json").read_text())
            self.assertEqual(index["registry_revision"], "before")

    def test_rejects_directory_and_manifest_name_mismatch(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_package(root, name="tmdb")
            manifest_path = root / "packages/tmdb/manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["name"] = "movies"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(builder.BuildError, "must be canonical and match"):
                builder.build_registry(root)


class PackageDetailsTests(unittest.TestCase):
    def test_version_classifiers(self) -> None:
        for requirement, expected in (
            (None, []),
            ("python@3.12", ["Python 3", "Python 3.12"]),
            ("python@3.11-3.13", ["Python 3", "Python 3.11", "Python 3.12", "Python 3.13"]),
            ("python@3.11-4.1", ["Python 3.11-4.1"]),
        ):
            with self.subTest(requirement=requirement):
                self.assertEqual(builder.python_classifiers(requirement), expected)

    def test_pinned_source_url_and_nested_manifest(self) -> None:
        record = {
            "repository": "https://github.com/kedi-lang/example-package.git",
            "verified_commit": "a" * 40,
            "package_manifest_path": "packages/tmdb/package.kedi",
            "name": "tmdb",
        }
        with patch.object(
            builder, "urlopen", return_value=BytesIO(PACKAGE_SOURCE.encode())
        ) as fetch:
            self.assertEqual(builder.fetch_package_manifest(record), PACKAGE_SOURCE)
        self.assertEqual(
            fetch.call_args.args[0].full_url,
            f"https://raw.githubusercontent.com/kedi-lang/example-package/{'a' * 40}/packages/tmdb/package.kedi",
        )
        self.assertEqual(fetch.call_args.kwargs["timeout"], 20)
        for url in (
            "https://evil.example/org/repo",
            "https://github.com/org/repo/extra",
            "https://github.com/../repo",
        ):
            with self.subTest(url=url), self.assertRaises(builder.BuildError):
                builder.package_source_url(dict(record, repository=url))

    def test_fetch_failure_never_falls_back_to_head(self) -> None:
        record = {
            "repository": "https://github.com/kedi-lang/example-package",
            "verified_commit": "a" * 40,
            "package_manifest_path": "package.kedi",
            "name": "tmdb",
        }
        with patch.object(builder, "urlopen", side_effect=URLError("offline")) as fetch:
            with self.assertRaisesRegex(builder.BuildError, "could not read verified"):
                builder.fetch_package_manifest(record)
            self.assertEqual(fetch.call_count, 1)
        with patch.object(
            builder, "urlopen", return_value=BytesIO(b"x" * (builder.MAX_METADATA_BYTES + 1))
        ):
            with self.assertRaisesRegex(builder.BuildError, "256 KiB"):
                builder.fetch_package_manifest(record)

    def test_markdown_features_and_relative_links(self) -> None:
        source = """# Movie tools

**Structured** details and *search*.

## Usage

- Find a film
- Read its details

```kedi
> import: tmdb
```

| Field | Type |
| --- | --- |
| title | str |

[Example](examples/search.kedi) [Usage](#usage)
![Logo](images/logo.png)
"""
        html = builder.render_readme(
            source,
            file_base="https://github.com/org/registry/blob/main/packages/tmdb/",
            image_base="https://raw.githubusercontent.com/org/registry/main/packages/tmdb/",
        )
        for markup in (
            "<strong>Structured</strong>",
            "<em>search</em>",
            "<ul>",
            "<table>",
            'class="language-kedi"',
            "&gt; import: tmdb",
            'href="#readme-usage"',
        ):
            self.assertIn(markup, html)
        self.assertIn('id="readme-usage"', html)
        self.assertIn(
            'href="https://github.com/org/registry/blob/main/packages/tmdb/examples/search.kedi"',
            html,
        )
        self.assertIn(
            'src="https://raw.githubusercontent.com/org/registry/main/packages/tmdb/images/logo.png"',
            html,
        )

    def test_markdown_cannot_inject_html_or_unsafe_links(self) -> None:
        source = """<script>alert(1)</script>
<img src=x onerror=alert(1)>
[run](javascript:alert%281%29)
[run](java&#x73;cript:alert%281%29)
[run](vbscript:test)
[local](file:///etc/passwd)
![svg](data:image/svg+xml,anything)
[credential](https://secret@example.com/)
## app
## app
## app-1
## **Quick** `start`
[broken](https://[invalid/)
```html
<script>alert(2)</script>
```
"""
        html = builder.render_readme(
            source,
            file_base="https://github.com/org/repo/",
            image_base="https://raw.githubusercontent.com/org/repo/",
        )
        elements = Elements(html).elements
        ids = []
        for tag, attributes in elements:
            self.assertNotIn(tag, {"script", "iframe", "object", "style"})
            self.assertFalse(any(name.lower().startswith("on") for name in attributes))
            for name in ("src", "href"):
                value = attributes.get(name, "") or ""
                self.assertFalse(value.startswith(("javascript:", "vbscript:", "file:", "data:")))
                self.assertNotIn("secret@", value)
            if "id" in attributes:
                ids.append(attributes["id"])
        self.assertEqual(
            ids, ["readme-app", "readme-app-1", "readme-app-1-1", "readme-quick-start"]
        )
        self.assertIn("&lt;script&gt;", html)


class RegistryServerTests(unittest.TestCase):
    def test_serves_api_and_package_routes(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        _write_package(root)
        with patch.object(builder, "fetch_package_manifest", return_value=PACKAGE_SOURCE):
            builder.build_registry(root)
        handler = type(
            "TestRegistryHandler",
            (server_module.RegistryHandler,),
            {
                "web_root": ROOT / "web",
                "api_root": root / "generated" / "v1",
                "log_message": lambda *args: None,
            },
        )
        httpd = server_module.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{httpd.server_port}"
            with urlopen(f"{base}/v1/index.json") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response)["schema_version"], 1)
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            with urlopen(f"{base}/package/tmdb") as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b'<main id="app"', response.read())
            with urlopen(f"{base}/v1/details/tmdb.json") as response:
                details = json.load(response)
                self.assertEqual(details["license"], "MIT")
                self.assertIn("Python 3.12", details["python_classifiers"])
                self.assertIn("<h2", details["readme_html"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
