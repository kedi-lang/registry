from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_site import build_site  # noqa: E402


class BuildSiteTests(unittest.TestCase):
    def test_combines_web_and_versioned_api(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "registry"
            (root / "web").mkdir(parents=True)
            (root / "generated/v1/package").mkdir(parents=True)
            (root / "web/index.html").write_text("registry")
            (root / "web/404.html").write_text("fallback")
            (root / "generated/v1/revision.json").write_text("{}")
            (root / "generated/v1/package/textkit.json").write_text("{}")

            output = root / "site"
            build_site(root, output)

            self.assertEqual((output / "index.html").read_text(), "registry")
            self.assertEqual((output / "404.html").read_text(), "fallback")
            self.assertTrue((output / "v1/revision.json").is_file())
            self.assertTrue((output / "v1/package/textkit.json").is_file())
            self.assertEqual(
                (output / "package/textkit/index.html").read_text(),
                "registry",
            )

    def test_rejects_unsafe_generated_package_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "registry"
            (root / "web").mkdir(parents=True)
            (root / "generated/v1/package").mkdir(parents=True)
            (root / "web/index.html").write_text("registry")
            (root / "generated/v1/revision.json").write_text("{}")
            (root / "generated/v1/package/Bad.json").write_text("{}")

            with self.assertRaisesRegex(ValueError, "Invalid generated package name"):
                build_site(root, root / "site")

    def test_rejects_output_that_contains_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "registry"
            root.mkdir()
            with self.assertRaisesRegex(ValueError, "must not contain"):
                build_site(root, parent)


if __name__ == "__main__":
    unittest.main()
