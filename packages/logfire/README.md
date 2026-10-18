# Logfire for Kedi

Configure Pydantic AI model/tool tracing from a Kedi program, with optional
HTTPX request spans. No instrumentation runs until `configure_logfire` is called.

## Install

```console
kedi add logfire
```

Kedi installs the manifest's `logfire[httpx]` dependency into the Python
interpreter running the command. Use a Kedi client with automatic
`python_dependencies` installation; older clients require
`python -m pip install 'logfire[httpx]>=4.41,<5'` in the same environment.

For a local checkout, run `kedi install library/logfire/package.kedi` from the
registry repository root instead.

## Use

```kedi
> import: logfire

`configure_logfire("city-guide")`

> model: openai:gpt-5.6-luna
>> The capital of Sweden is [city: str].
> show: The selected city is <city>.

`flush_logfire()`
```

Set `LOGFIRE_TOKEN` or authenticate using the Python Logfire CLI to send data
to a project. Without a token the program still runs and Logfire can display
local console output. Tokens belong in the environment, never in `.kedi` source.

## API

`configure_logfire(service_name="kedi", capture_content=False, httpx=False)`
configures the process-wide Logfire SDK and Pydantic AI instrumentation. In
native Kedi calls, pass options positionally:

```kedi
> import: logfire

`configure_logfire("city-guide", False, True)`
```

The third argument enables HTTPX spans; request/response bodies and headers
are not captured. The second argument opts into model content capture.
Configure once during startup, before model calls. Importing this package
does not select a model or expose tools to an agent.

`flush_logfire()` returns a boolean indicating whether pending telemetry was
flushed within three seconds. Call it when finishing a short-lived program.

This package instruments Pydantic AI and optionally HTTPX. Full Kedi runtime,
artifact, and workflow instrumentation is provided separately by
`opentelemetry-instrumentation-kedi`. When that instrumentor owns Pydantic AI
instrumentation, configure Logfire directly rather than enabling that same
integration a second time through this package.

The wrapper is MIT licensed. Its Python dependencies retain their own licenses.
