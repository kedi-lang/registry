# TMDB for Kedi

Find a film by title and retrieve its director, release date, and runtime using
TMDB's API. No movie IDs or MCP server configuration are needed.

## Install

```console
kedi add tmdb
```

Kedi installs `httpx>=0.27,<1` into the Python environment running the command.
Use Python 3.11-3.14 and a Kedi version with automatic Python dependency installation.

## Credentials

Set `TMDB_API_KEY` to your TMDB **API Read Access Token**, not the shorter API key.
The tool sends the token as a Bearer header. Obtain a token from your
[TMDB API settings](https://www.themoviedb.org/settings/api).

For example, put this in a local `.env` beside your program when using the Kedi CLI:

```dotenv
TMDB_API_KEY=your-tmdb-read-access-token
```

## Use from a model

```kedi
> import: tmdb
> approval: allow
> use: movie_details

>> Look up Spirited Away using movie_details. Its director is [director: str], release year [year: int], and runtime [minutes: int] minutes.

= `{"director": director, "year": year, "minutes": minutes}`
```

Configure your generative model and its credentials separately. For example:

```console
kedi movie_night.kedi --adapter-model google/gemini-3-flash-preview
```

The Google model requires `GOOGLE_API_KEY` and the `pydantic-ai-slim[google]`
provider dependency. The package itself makes no model calls.

## Call directly

```kedi
> import: tmdb

= `movie_details("Dune", 1984)`
```

`movie_details(title: str, year: int = 0) -> dict` returns:

```json
{
  "title": "Dune",
  "release_date": "1984-12-14",
  "runtime": 137,
  "directors": ["David Lynch"]
}
```

A call searches for the title and then requests the matching movie's details and
credits. Exact title matches are preferred; the tool rejects missing or ambiguous
results rather than picking an arbitrary movie. Supply a release year to
distinguish remakes. Each HTTP request has a 10-second timeout. HTTP errors,
rate limits, invalid responses, and timeouts propagate to the caller.

The wrapper is MIT licensed. TMDB data and API access are subject to
[TMDB's terms](https://www.themoviedb.org/terms-of-use). This product uses the
TMDB API but is not endorsed or certified by TMDB.
