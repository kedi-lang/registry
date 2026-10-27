"""Exercise the installed TMDB package without API credentials or model calls."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from kedi.errors import KediExecutionError
from kedi.lang import compile_program, parse_program
from kedi.package_registry import install_package


ROOT = Path(__file__).resolve().parents[1]


class TmdbPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        environment = patch.dict(
            os.environ,
            {
                "KEDI_HOME": str(home),
                "TMDB_API_KEY": "test-tmdb-token",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        with patch("kedi.package_registry.install_python_dependencies") as install:
            install_package(ROOT / "library/tmdb/package.kedi")
        install.assert_called_once_with(["httpx>=0.27,<1"])

    def run_lookup(self, transport, title="Dune", year=1984):
        client_class = httpx.Client
        with patch.object(
            httpx,
            "Client",
            side_effect=lambda **kwargs: client_class(
                transport=httpx.MockTransport(transport),
                **kwargs,
            ),
        ):
            source = f"> import: tmdb\n= `movie_details({title!r}, {year})`"
            program = compile_program(parse_program(source))
            return program.run_main()

    def test_imported_package_searches_by_title_and_year_before_loading_details(self):
        calls = []

        def transport(request):
            calls.append(request.url.path)
            self.assertEqual(request.headers["Authorization"], "Bearer test-tmdb-token")
            self.assertEqual(request.extensions["timeout"]["read"], 10.0)
            if request.url.path == "/3/search/movie":
                self.assertEqual(request.url.params["query"], "Dune")
                self.assertEqual(request.url.params["primary_release_year"], "1984")
                return httpx.Response(200, json={"results": [{"id": 841, "title": "Dune"}]})
            self.assertEqual(request.url.path, "/3/movie/841")
            self.assertEqual(request.url.params["append_to_response"], "credits")
            return httpx.Response(
                200,
                json={
                    "title": "Dune",
                    "release_date": "1984-12-14",
                    "runtime": 137,
                    "credits": {
                        "crew": [
                            {"job": "Producer", "name": "Producer"},
                            {"job": "Director", "name": "David Lynch"},
                        ]
                    },
                },
            )

        self.assertEqual(
            self.run_lookup(transport),
            {
                "title": "Dune",
                "release_date": "1984-12-14",
                "runtime": 137,
                "directors": ["David Lynch"],
            },
        )
        self.assertEqual(calls, ["/3/search/movie", "/3/movie/841"])

    def test_missing_and_ambiguous_titles_are_not_guessed(self):
        cases = [
            ([], 1, "No movie found"),
            ([{"id": 1, "title": "Dune"}, {"id": 2, "title": "Dune"}], 1, "Ambiguous title"),
            ([{"id": 1, "title": "Dune"}], 2, "Ambiguous title"),
        ]
        for results, pages, message in cases:
            with self.subTest(results=results, pages=pages):

                def transport(request):
                    self.assertEqual(request.url.path, "/3/search/movie")
                    return httpx.Response(200, json={"results": results, "total_pages": pages})

                with self.assertRaisesRegex(KediExecutionError, message):
                    self.run_lookup(transport, year=0)

    def test_http_failures_are_reported_without_the_access_token(self):
        for stage in ("search", "details"):
            for status in (401, 429, 500):
                with self.subTest(stage=stage, status=status):

                    def transport(request):
                        if stage == "details" and request.url.path == "/3/search/movie":
                            return httpx.Response(
                                200, json={"results": [{"id": 841, "title": "Dune"}]}
                            )
                        return httpx.Response(status, json={"status_message": "Request failed"})

                    with self.assertRaisesRegex(KediExecutionError, str(status)) as error:
                        self.run_lookup(transport)
                    self.assertNotIn("test-tmdb-token", str(error.exception))


if __name__ == "__main__":
    unittest.main()
