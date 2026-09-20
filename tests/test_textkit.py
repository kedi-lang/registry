from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from kedi.lang import compile_program, parse_program
from kedi.package_registry import install_package

ROOT = Path(__file__).resolve().parents[1]


class TextkitTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {"KEDI_HOME": str(self.root / "home")})
        environment.start()
        self.addCleanup(environment.stop)
        install_package(ROOT / "library/textkit/package.kedi")

    def run_helper(self, name: str, value: str):
        source = f"> import: textkit\n= `{name}(value)`\n"
        program = parse_program(source, source_path=str(self.root / "main.kedi"))
        return compile_program(program, runtime_globals={"value": value}).run_main()

    def test_normalize_whitespace(self) -> None:
        for value, expected in (
            ("", ""),
            (" \t\n ", ""),
            ("  Hello\n\tKedi  ", "Hello Kedi"),
            ("one\u00a0two\u2003three", "one two three"),
            ("a,b", "a,b"),
        ):
            with self.subTest(value=value):
                self.assertEqual(self.run_helper("normalize_whitespace", value), expected)

    def test_word_count(self) -> None:
        for value, expected in (
            ("", 0),
            (" \n ", 0),
            ("one two\tthree", 3),
            ("a,b", 1),
            ("a\u00a0b", 2),
        ):
            with self.subTest(value=value):
                self.assertEqual(self.run_helper("word_count", value), expected)

    def test_slugify(self) -> None:
        for value, expected in (
            ("Kedi & Registry!", "kedi-registry"),
            ("---", ""),
            ("", ""),
            ("Cr\u00e8me br\u00fbl\u00e9e", "creme-brulee"),
            ("version 0.1.0", "version-0-1-0"),
            ("\u732b", ""),
            ("already-a-slug", "already-a-slug"),
        ):
            with self.subTest(value=value):
                self.assertEqual(self.run_helper("slugify", value), expected)
                self.assertEqual(self.run_helper("slugify", expected), expected)

    def test_readme_example(self) -> None:
        readme = (ROOT / "library/textkit/README.md").read_text()
        code = readme.split("```kedi\n", 1)[1].split("```", 1)[0]
        program = parse_program(code, source_path=str(self.root / "readme.kedi"))
        self.assertEqual(
            compile_program(program).run_main(), "Kedi Package Index! / kedi-package-index / 3"
        )


if __name__ == "__main__":
    unittest.main()
