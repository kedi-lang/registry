# kedi registry

The public index for verified third-party Kedi packages. Registry records pin
each package to the exact source commit reviewed through a pull request; the
client never follows a repository's moving default branch.

The static website is designed for `https://registry.kedi-lang.org`. Package
pages use stable routes such as `/package/textkit`.

## Repository layout

```text
packages/<name>/
  manifest.json      reviewed package metadata
  revisions.json     optional append-only history
  README.md           package documentation
  LICENSE             distributed license text
generated/v1/
  revision.json       lightweight browser cache invalidation pointer
  index.json          searchable package catalog
  audit.json          current and historical commit status
  package/<name>.json install record consumed by Kedi
  details/<name>.json rendered README and declared package metadata
web/                   static registry interface
library/textkit/        source of the deterministic textkit package
```

## Build registry data

```console
python -m pip install -r requirements-build.txt
python scripts/build_registry.py
```

The builder validates every source record and writes deterministic JSON. Pass
`--revision "$GITHUB_SHA"` in CI to bind generated records to the registry
commit that published them.

Building requires Kedi's manifest parser and `markdown-it-py`; serving the
generated website requires only Python's standard library. When developing
alongside Kedi, its activated local environment can also run the builder.

For each package, the builder downloads `package.kedi` from its exact
`verified_commit` on GitHub, parses it without executing package code, and
checks its name and version against the registry record. It never reads HEAD.
An unavailable or invalid manifest fails the build without replacing the
previously generated API.

The package page renders `packages/<name>/README.md` with headings, lists,
tables, fenced code and links. Raw HTML is escaped and unsafe URL schemes are
blocked. Relative documentation and image links resolve within the registry's
package directory; fragment links point into the rendered README.

The left sidebar shows the author and contact from the reviewed registry
record, plus the license, source directory, Python requirement and Python
dependencies declared in `package.kedi`. For example, `python@3.11-3.13`
becomes **Python 3**, **Python 3.11**, **Python 3.12**, **Python 3.13**. These
are declared compatibility, not registry testing claims. Missing fields are
labelled **Not declared**; no license or Python version is guessed from a
filename. The license name links to the reviewed `LICENSE` text.

Website details are kept in a separate endpoint so the strict v1 installation
and audit records remain backwards compatible. If details are temporarily
unavailable, the page still shows installation information and a README link.

## Browser data and cache

Both local previews and the public website read the real generated data from
the registry's `/v1/` API. The UI does not substitute local fixture data.
Each page load revalidates the small `revision.json` resource. Catalog, package
records and rendered READMEs are stored in browser `localStorage`, keyed by
registry revision. An unchanged revision reuses them without downloading their
content again. A changed revision removes old entries and fetches fresh data.
This also invalidates yanked/revoked statuses, not just package version numbers.

Storage failures degrade to network reads. If GitHub cannot confirm the current
revision, the page shows a connection error instead of presenting stale active
package records. GitHub's upstream CDN can still delay visibility of a new
publication; the browser cache itself has no time-based retention past a
confirmed revision change. This cache affects browsing only, not CLI verification.

Tests use isolated fixtures, never production package records:

```console
python -m unittest discover -s tests -v
node --test tests/registry-client.test.mjs
```

## Run locally

```console
python server.py
```

Open `http://127.0.0.1:8767`. The local server exposes the generated API below
`/v1/` and supports package routes without a frontend build step.

## Deploy

Pushes to `main` run `.github/workflows/pages.yml`. The workflow verifies the
committed registry snapshot, tests the publication builder and browser client,
assembles the static website with `/v1/` data, and publishes it to
`https://registry.kedi-lang.org` through GitHub Pages. Maintainers rebuild and
fully validate the snapshot locally before committing it, using the commands
above and the Kedi version pinned in `requirements-build.txt`.

## Register a package

Open a pull request that adds `manifest.json`, `README.md`, and `LICENSE` under
`packages/<name>/`. The v1 manifest shape is documented in
[`schemas/package-manifest-v1.schema.json`](schemas/package-manifest-v1.schema.json).

Registry verification records provenance and exact-source identity. It does
not claim that a package is sandboxed, vulnerability-free, or security-audited.
