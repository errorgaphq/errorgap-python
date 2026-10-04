from __future__ import annotations

from typing import Any, Dict, Optional

from . import notify
from .apm import SpanCollector
from .wsgi import ROUTE_KEY, TRANSACTION_KEY, ErrorgapMiddleware


def init_app(app: Any) -> None:
    """Register Errorgap with a Flask application.

    Subscribes to Flask's ``got_request_exception`` signal so all unhandled
    exceptions raised inside a request are reported, and wraps the app in
    :class:`~errorgap.wsgi.ErrorgapMiddleware` so each request is an APM
    transaction (sent with ``apm_enabled``) grouped by its URL rule, and errors
    carry its transaction id.
    """
    try:
        from flask import got_request_exception, request
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Flask is required to use errorgap.flask.init_app") from exc

    if not isinstance(app.wsgi_app, ErrorgapMiddleware):
        app.wsgi_app = ErrorgapMiddleware(app.wsgi_app)

    @app.before_request
    def _errorgap_route() -> None:
        rule = getattr(request, "url_rule", None)
        if rule is not None:
            request.environ[ROUTE_KEY] = rule.rule

    def _on_exception(sender: Any, exception: BaseException, **_: Any) -> None:
        try:
            from flask import request

            ctx = _context(request)
            env = _environment(request)
            params = _params(request)
        except Exception:  # noqa: BLE001
            ctx, env, params = {}, {}, {}

        notify(
            exception,
            sync=True,
            context=ctx,
            environment=env,
            params=params,
        )

    # weak=False: keep a strong reference so the local closure isn't GC'd.
    got_request_exception.connect(_on_exception, app, weak=False)


def spans() -> Optional[SpanCollector]:
    """The span collector for the current request's transaction, for
    recording DB and outbound HTTP spans from views."""
    from flask import has_request_context, request

    if not has_request_context():
        return None
    txn = request.environ.get(TRANSACTION_KEY)
    return txn.spans if txn is not None else None


def _context(request: Any) -> Dict[str, Any]:
    return {
        "url": getattr(request, "url", None),
        "component": getattr(request, "endpoint", None) or getattr(request, "path", None),
        "action": getattr(request, "method", None),
    }


def _environment(request: Any) -> Dict[str, Any]:
    return {
        "method": getattr(request, "method", None),
        "path": getattr(request, "path", None),
        "query_string": getattr(request, "query_string", b"").decode("utf-8", errors="replace")
        if isinstance(getattr(request, "query_string", None), (bytes, bytearray))
        else getattr(request, "query_string", None),
        "user_agent": str(getattr(request, "user_agent", "") or ""),
        "remote_addr": getattr(request, "remote_addr", None),
    }


def _params(request: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        for key, value in (getattr(request, "args", {}) or {}).items():
            out[key] = value
    except Exception:  # noqa: BLE001
        pass
    try:
        form = getattr(request, "form", None)
        if form:
            for key, value in form.items():
                out[key] = value
    except Exception:  # noqa: BLE001
        pass
    try:
        if request.is_json:
            json_body = request.get_json(silent=True)
            if isinstance(json_body, dict):
                for key, value in json_body.items():
                    out[key] = value
    except Exception:  # noqa: BLE001
        pass
    return out
