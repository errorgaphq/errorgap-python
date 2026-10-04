# Changelog

## 0.3.0 — 2026-10-04

- Django and FastAPI/Starlette middleware now time each request as an APM
  transaction (with `apm_enabled`), grouped by URL pattern / route path, with
  errors linked to their request and the browser's `x-errorgap-trace` header
  recorded. `errorgap.django.spans(request)` / `errorgap.fastapi.spans(request)`
  record spans.

## 0.2.0 — 2026-10-03

- APM: `track_transaction` / `track_job` context managers, `notify_transaction`,
  and `SpanCollector` for DB and HTTP spans; enabled with `apm_enabled=True`,
  sampled by `apm_sample_rate`.
- Errors reported during a transaction carry its id as
  `context.transaction_id` (held in a `ContextVar`), linking each error to
  the request or job that raised it.
- `errorgap.wsgi.ErrorgapMiddleware` times WSGI requests; `errorgap.flask.init_app`
  installs it and groups requests by URL rule.
- Requests record the browser SDK's `x-errorgap-trace` header as the
  transaction's `trace_id`, linking browser API calls to server requests.

## 0.1.1 — 2026-07-18

- Include bounded inline source excerpts for readable application and dependency
  traceback frames so
  Errorgap can render highlighted source without a repository integration.
- Order traceback frames innermost-first so frame 0 and group fingerprints use
  the actual exception site.
