from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from . import notify
from .apm import SpanCollector, Transaction, browser_trace_id
from .transaction_context import new_transaction_id, transaction_scope

_TRANSACTION_ATTR = "errorgap_transaction"


class ErrorgapMiddleware:
    """Django middleware that reports unhandled exceptions to Errorgap and
    times each request as an APM transaction (sent with ``apm_enabled``),
    grouped by its URL pattern. Errors raised during the request carry its
    transaction id, and the browser SDK's ``x-errorgap-trace`` header links
    the browser's view of the call to it.

    Add ``"errorgap.django.ErrorgapMiddleware"`` to ``MIDDLEWARE``. Place it
    early so it sees exceptions raised by inner middleware too.
    """

    def __init__(self, get_response: Callable[..., Any]):
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        meta = getattr(request, "META", {}) or {}
        txn = Transaction(
            kind="web",
            id=new_transaction_id(),
            trace_id=browser_trace_id(meta.get("HTTP_X_ERRORGAP_TRACE")),
            method=getattr(request, "method", None),
            path_raw=getattr(request, "path", None) or "/",
            occurred_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        )
        try:
            setattr(request, _TRANSACTION_ATTR, txn)
        except Exception:  # noqa: BLE001
            pass
        start = time.perf_counter()
        response = None
        try:
            with transaction_scope(txn.id or new_transaction_id()):
                response = self.get_response(request)
            return response
        finally:
            txn.status_code = getattr(response, "status_code", None) or 500
            txn.duration_ms = (time.perf_counter() - start) * 1000.0
            txn.path = _route(request) or txn.path_raw
            _send_transaction(txn)

    def process_exception(self, request: Any, exception: BaseException) -> Optional[Any]:
        notify(
            exception,
            sync=True,
            context=_context(request),
            environment=_environment(request),
            session=_session(request),
            params=_params(request),
        )
        # Returning None lets Django continue its exception handling chain.
        return None


def spans(request: Any) -> Optional[SpanCollector]:
    """The span collector for ``request``'s transaction, for recording DB and
    outbound HTTP spans from views."""
    txn = getattr(request, _TRANSACTION_ATTR, None)
    return txn.spans if txn is not None else None


def _route(request: Any) -> Optional[str]:
    """The matched URL pattern (``/orders/<int:id>``), when one matched."""
    match = getattr(request, "resolver_match", None)
    route = getattr(match, "route", None) if match is not None else None
    if not route:
        return None
    return route if route.startswith("/") else "/" + route


def _send_transaction(txn: Transaction) -> None:
    import errorgap

    errorgap.notify_transaction(txn)


def _context(request: Any) -> Dict[str, Any]:
    try:
        resolver = getattr(request, "resolver_match", None)
        view_name = resolver.view_name if resolver else None
    except Exception:  # noqa: BLE001
        view_name = None
    try:
        url = request.build_absolute_uri()
    except Exception:  # noqa: BLE001
        url = getattr(request, "path", None)
    return {
        "url": url,
        "component": view_name or getattr(request, "path", None),
        "action": getattr(request, "method", None),
    }


def _environment(request: Any) -> Dict[str, Any]:
    meta = getattr(request, "META", {}) or {}
    return {
        "method": getattr(request, "method", None),
        "path": getattr(request, "path", None),
        "query_string": meta.get("QUERY_STRING"),
        "user_agent": meta.get("HTTP_USER_AGENT"),
        "remote_addr": meta.get("REMOTE_ADDR"),
    }


def _session(request: Any) -> Dict[str, Any]:
    try:
        session = getattr(request, "session", None)
        if session is None:
            return {}
        return dict(session.items())
    except Exception:  # noqa: BLE001
        return {}


def _params(request: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        for key, value in (getattr(request, "GET", {}) or {}).items():
            out[key] = value
        post = getattr(request, "POST", None)
        if post:
            for key, value in post.items():
                out[key] = value
    except Exception:  # noqa: BLE001
        return out
    return out
