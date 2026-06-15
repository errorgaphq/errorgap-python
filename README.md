# errorgap

Python notifier for [Errorgap](https://errorgap.com). Captures exceptions,
normalizes tracebacks, and ships notices to an Errorgap server. Single
package covers plain Python, Django, Flask, and FastAPI.

## Install

```sh
pip install errorgap
```

For framework integrations:

```sh
pip install "errorgap[django]"   # or [flask], [fastapi]
```

Requires Python 3.9+.

## Configure

```python
import errorgap

errorgap.init(
    endpoint=...,
    project_slug=...,
    api_key=...,
    environment="production",
)
```

`init` reads the same values from `ERRORGAP_ENDPOINT`,
`ERRORGAP_PROJECT_SLUG`, `ERRORGAP_PROJECT_ID`, and `ERRORGAP_API_KEY` if you
don't pass them. By default it installs a `sys.excepthook` to catch
uncaught exceptions in scripts; pass `capture_globals=False` to skip.

## Manual notification

```python
try:
    risky()
except Exception as exc:
    errorgap.notify(exc, context={"component": "billing"})
    raise
```

`notify` returns a `DeliveryResult` (`status`, `body`, `error`, `queued`).
The SDK never raises.

## Django

Add to `MIDDLEWARE`:

```python
MIDDLEWARE = [
    "errorgap.django.ErrorgapMiddleware",
    # ... your existing middleware ...
]
```

## Flask

```python
from flask import Flask
from errorgap.flask import init_app

app = Flask(__name__)
init_app(app)
```

## FastAPI

```python
from fastapi import FastAPI
from errorgap.fastapi import ErrorgapMiddleware

app = FastAPI()
app.add_middleware(ErrorgapMiddleware)
```

## Configuration reference

| Argument | Default | Notes |
|---|---|---|
| `endpoint` | `ERRORGAP_ENDPOINT` or `http://127.0.0.1:3030` | Base URL, no trailing slash |
| `project_slug` | `ERRORGAP_PROJECT_SLUG` | **Required** |
| `project_id` | `ERRORGAP_PROJECT_ID` | Optional, embedded in payload |
| `api_key` | `ERRORGAP_API_KEY` | Sent as `x-errorgap-project-key` |
| `environment` | `ERRORGAP_ENVIRONMENT`, `ENV`, or `development` | |
| `root_directory` | `os.getcwd()` | Used to mark frames as `in_app` |
| `async_` | `True` | Background-thread delivery |
| `logger` | `logging.getLogger("errorgap")` | Pass `None` to silence |
| `filter_keys` | `("password", "token", ...)` | Substring match, case-insensitive |
| `capture_globals` | `True` | Install `sys.excepthook` |

## Graceful shutdown

```python
errorgap.flush(timeout=5)     # wait for queued deliveries
errorgap.shutdown(timeout=5)  # flush + tear down background thread
```

## Verify

```sh
curl -sS -X POST "$ERRORGAP_ENDPOINT/api/projects/$ERRORGAP_PROJECT_SLUG/notices" \
  -H "content-type: application/json" \
  -H "x-errorgap-project-key: $ERRORGAP_API_KEY" \
  -d '{"errors":[{"type":"ErrorgapInstallTest","message":"Errorgap install verification"}],"context":{"environment":"development"}}'
```

Then trigger a real error and confirm it appears in the Errorgap UI.

## Development

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT.
