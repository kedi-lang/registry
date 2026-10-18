from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from kedi.lang import compile_program, parse_program
from kedi.package_manifest import load_package_manifest
from kedi.package_registry import install_package

ROOT = Path(__file__).resolve().parents[1]


class LogfireTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {"KEDI_HOME": str(self.root / "home")})
        environment.start()
        self.addCleanup(environment.stop)
        self.logfire = SimpleNamespace(
            configure=Mock(),
            instrument_pydantic_ai=Mock(),
            instrument_httpx=Mock(),
            force_flush=Mock(return_value=True),
        )
        modules = patch.dict(sys.modules, {"logfire": self.logfire})
        modules.start()
        self.addCleanup(modules.stop)
        with patch("kedi.package_registry.install_python_dependencies") as installer:
            install_package(ROOT / "library/logfire/package.kedi")
        installer.assert_called_once_with(["logfire[httpx]>=4.41,<5"])

    def run_program(self, source: str):
        program = parse_program(source, source_path=str(self.root / "main.kedi"))
        return compile_program(program).run_main()

    def test_manifest_and_side_effect_free_import(self) -> None:
        metadata = load_package_manifest(ROOT / "library/logfire/package.kedi")
        self.assertEqual(metadata.name, "logfire")
        self.run_program("> import: logfire\n= ready\n")
        self.logfire.configure.assert_not_called()
        self.logfire.instrument_pydantic_ai.assert_not_called()
        self.logfire.instrument_httpx.assert_not_called()

    def test_defaults_and_flush(self) -> None:
        result = self.run_program("> import: logfire\n`configure_logfire()`\n= `flush_logfire()`\n")
        self.assertIs(result, True)
        self.logfire.configure.assert_called_once_with(
            service_name="kedi", send_to_logfire="if-token-present"
        )
        self.logfire.instrument_pydantic_ai.assert_called_once_with(include_content=False)
        self.logfire.instrument_httpx.assert_not_called()
        self.logfire.force_flush.assert_called_once_with()

    def test_explicit_instrumentation_options(self) -> None:
        self.run_program('> import: logfire\n`configure_logfire("service", True, True)`\n= ready\n')
        self.logfire.configure.assert_called_once_with(
            service_name="service", send_to_logfire="if-token-present"
        )
        self.logfire.instrument_pydantic_ai.assert_called_once_with(include_content=True)
        self.logfire.instrument_httpx.assert_called_once_with()

    def test_flush_failure_is_returned(self) -> None:
        self.logfire.force_flush.return_value = False
        self.assertIs(self.run_program("> import: logfire\n= `flush_logfire()`\n"), False)

    def test_sdk_failure_is_not_swallowed(self) -> None:
        self.logfire.configure.side_effect = ValueError("invalid configuration")
        with self.assertRaisesRegex(Exception, "invalid configuration"):
            self.run_program("> import: logfire\n`configure_logfire()`\n= ready\n")

    def test_readme_programs_parse(self) -> None:
        readme = (ROOT / "library/logfire/README.md").read_text()
        for block in readme.split("```kedi\n")[1:]:
            parse_program(block.split("```", 1)[0])


if __name__ == "__main__":
    unittest.main()
