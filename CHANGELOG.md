# Changelog

## 0.5.1 — 2026-10-13

- Tornado: `errorgap.tornado.ErrorgapMixin` reports handler errors and times
  each request, grouped by the handler's route pattern.

## 0.5.0 — 2026-10-13

- Delivery: a bounded queue (it was unbounded), a `timeout` per request,
  retries after a network failure or 5xx, and a pause for the server's
  `Retry-After` after a 429.
- Fixed: a param JSON cannot serialize raised from `notify(sync=True)` and
  killed the delivery thread.
- `before_notify`, `ignore_environments`, cause chains (`context.causes`),
  release detection, and `filter_keys` applied at any depth, in lists and in
  the session (compiled patterns allowed). The Django middleware names the
  signed-in user.
- Remote settings: errors and performance data can be switched off for a
  project in errorgap and running apps follow within ten minutes. Fails open;
  `remote_settings=False` ignores the switches.
- New integrations: `errorgap.celery.install()`,
  `errorgap.log_handler.ErrorgapHandler`, `errorgap.aiohttp.errorgap_middleware`
  and `errorgap.asgi` for any ASGI framework.

## 0.4.0 — 2026-10-06

- Sign-ins: `init(auth_events=True)` reports sign-ins to errorgap's
  Security › Logins. Django's `user_logged_in` / `user_login_failed` signals
  are reported automatically with the middleware installed;
  `errorgap.sign_in(outcome, user=, request=)` covers Flask, FastAPI and
  other outcomes (`password_reset`, `mfa_failure`, `locked`). `app_name`
  (or `ERRORGAP_APP_NAME`) names the app. Passwords and tokens are never sent.

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
