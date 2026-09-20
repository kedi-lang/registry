# textkit

Three deterministic text helpers for Kedi programs. No model, network request,
API key, or third-party Python dependency is needed to run them.

## Install

```console
kedi add textkit
```

Until the registry domain is live, point the CLI at the GitHub-hosted registry:

```console
KEDI_REGISTRY_URL=https://raw.githubusercontent.com/kedi-lang/registry/main/generated kedi add textkit
```

## Use in Kedi

```kedi
> import: textkit

[title: str] = `"  Kedi   Package Index!  "`

= <normalize_whitespace(<title>)> / <slugify(<title>)> / <word_count(<title>)>
```

Output:

```text
Kedi Package Index! / kedi-package-index / 3
```

## API

| Procedure | Returns | Behavior |
| --- | --- | --- |
| `normalize_whitespace(value: str)` | `str` | Trims and collapses Unicode whitespace to a single ASCII space. |
| `word_count(value: str)` | `int` | Counts whitespace-separated tokens. Punctuation does not create new tokens. |
| `slugify(value: str)` | `str` | Normalizes with NFKD, removes non-ASCII characters, lowercases, and joins alphanumeric runs with hyphens. |

## Edge cases

- Empty and whitespace-only strings normalize to `""` and contain zero words.
- `slugify("Crème brûlée")` returns `"creme-brulee"`.
- Slugs contain only `a-z`, `0-9` and internal hyphens.
- This is not a transliteration library. Non-Latin text may produce an empty
  slug, and names such as `"Café"` and `"Cafe"` produce the same result. Do not
  treat slugs as unique identifiers.
- `word_count` does not perform linguistic segmentation or count model tokens.
- All procedures require strings; no implicit conversion is performed.

## Compatibility

Python 3.11 through 3.13. Uses only the Python standard library.

## License

MIT. See [LICENSE](LICENSE).
