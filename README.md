# errorgap

Python notifier for [Errorgap](https://errorgap.com). Captures exceptions,
normalizes tracebacks with bounded source excerpts for readable frames, and ships
notices to an Errorgap server. Single
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

With `apm_enabled=True` each request is also an APM transaction grouped by
its URL pattern (`/orders/<int:order_id>`); errors raised during it carry its
transaction id, and the browser SDK's `x-errorgap-trace` header is recorded.
Record spans from a view with `errorgap.django.spans(request).database(sql, ms)`.

## Flask

```python
from flask import Flask
from errorgap.flask import init_app

app = Flask(__name__)
init_app(app)
```

`init_app` also times each request as an APM transaction (sent with
`apm_enabled=True`) grouped by its URL rule (`/orders/<int:id>`), and errors
raised during the request carry its transaction id. Record spans from a view
with `errorgap.flask.spans()`:

```python
from errorgap.flask import spans

@app.route("/orders/<int:order_id>")
def order(order_id):
    started = time.perf_counter()
    row = db.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
    spans().database("SELECT * FROM orders WHERE id = %s", (time.perf_counter() - started) * 1000)
    return row
```

## WSGI

Any WSGI app gets the same request transactions from
`errorgap.wsgi.ErrorgapMiddleware`. Set `environ["errorgap.route"]` to the
matched route template to group requests (otherwise the raw path is used).

```python
from errorgap.wsgi import ErrorgapMiddleware

application = ErrorgapMiddleware(application)
```

## Transactions and jobs

```python
with errorgap.track_transaction("GET", "/orders/{id}", "/orders/123") as txn:
    txn.spans.database("SELECT * FROM orders WHERE id = 123", 4.2)
    txn.status_code = 200

with errorgap.track_job("ReceiptJob", queue="mailers") as txn:
    send_receipt()
```

Both time the block and deliver on exit even if it raises. Errors reported
inside carry the transaction id (`context.transaction_id`), so errorgap shows
the error a request raised on its trace. The id lives in a `ContextVar`, so
concurrent threads and asyncio tasks never share one;
`errorgap.current_transaction_id()` returns the id in effect.

## Browser trace links

When the errorgap browser SDK (`@errorgap/browser` 0.3+) is on the page, its
API calls send an `x-errorgap-trace` header. The WSGI, Django and FastAPI
middleware (and so Flask's `init_app`) record it, and `track_transaction(..., trace_id=header)` accepts
it, so errorgap's browser Performance view links each call to the server
request that answered it. Malformed values are ignored.

## FastAPI

```python
from fastapi import FastAPI
from errorgap.fastapi import ErrorgapMiddleware

app = FastAPI()
app.add_middleware(ErrorgapMiddleware)
```

With `apm_enabled=True` each request is also an APM transaction grouped by
its route path (`/orders/{order_id}`); errors raised during it carry its
transaction id, and the browser SDK's `x-errorgap-trace` header is recorded.
Record spans from an endpoint with `errorgap.fastapi.spans(request).database(sql, ms)`
(take `request: Request` as a parameter).

## Configuration reference

| Argument | Default | Notes |
|---|---|---|
| `endpoint` | `ERRORGAP_ENDPOINT` or `http://127.0.0.1:3030` | Base URL, no trailing slash |
| `project_slug` | `ERRORGAP_PROJECT_SLUG` | **Required** |
| `project_id` | `ERRORGAP_PROJECT_ID` | Optional, embedded in payload |
| `api_key` | `ERRORGAP_API_KEY` | Sent as `x-errorgap-project-key` |
| `environment` | `ERRORGAP_ENVIRONMENT`, `ENV`, or `development` | |
| `root_directory` | `os.getcwd()` | Marks application frames; readable dependency frames also include bounded source excerpts |
| `async_` | `True` | Background-thread delivery |
| `logger` | `logging.getLogger("errorgap")` | Pass `None` to silence |
| `filter_keys` | `("password", "token", ...)` | Substring match, case-insensitive |
| `apm_enabled` | `False` | Send APM transactions |
| `apm_sample_rate` | `1.0` | Fraction of transactions sent (errors are unaffected) |
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
