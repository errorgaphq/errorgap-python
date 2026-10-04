from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from . import notify
from .apm import SpanCollector, Transaction, browser_trace_id
from .transaction_context import new_transaction_id, transaction_scope

#: ASGI scope key holding the request's :class:`~errorgap.apm.Transaction`.
TRANSACTION_KEY = "errorgap.transaction"


class ErrorgapMiddleware:
    """Pure ASGI middleware that reports unhandled exceptions to Errorgap and
    times each request as an APM transaction (sent with ``apm_enabled``),
    grouped by its route path (``/orders/{order_id}``). Errors raised during
    the request carry its transaction id, and the browser SDK's
    ``x-errorgap-trace`` header links the browser's view of the call to it.

    Usage::

        from fastapi import FastAPI
        from errorgap.fastapi import ErrorgapMiddleware

        app = FastAPI()
        app.add_middleware(ErrorgapMiddleware)
    """

    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        txn = Transaction(
            kind="web",
            id=new_transaction_id(),
            trace_id=browser_trace_id(headers.get(b"x-errorgap-trace")),
            method=scope.get("method"),
            path_raw=scope.get("path") or "/",
            occurred_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        )
        scope[TRANSACTION_KEY] = txn
        start = time.perf_counter()

        async def _send(message: Dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                txn.status_code = message.get("status")
            await send(message)

        try:
            with transaction_scope(txn.id or new_transaction_id()):
                try:
                    await self.app(scope, receive, _send)
                except Exception as exc:
                    txn.status_code = 500
                    notify(
                        exc,
                        sync=True,
                        context=_context(scope),
                        environment=_environment(scope),
                    )
                    raise
        finally:
            import errorgap

            txn.duration_ms = (time.perf_counter() - start) * 1000.0
            txn.path = _route(scope) or txn.path_raw
            if txn.status_code is None:
                txn.status_code = 500
            errorgap.notify_transaction(txn)


def spans(request: Any) -> Optional[SpanCollector]:
    """The span collector for the request's transaction (a Starlette/FastAPI
    ``Request``), for recording DB and outbound HTTP spans from endpoints."""
    txn = getattr(request, "scope", {}).get(TRANSACTION_KEY)
    return txn.spans if txn is not None else None


def _route(scope: Dict[str, Any]) -> Optional[str]:
    """The matched route's path template, which FastAPI's router records."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else None


def _context(scope: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "url": _build_url(scope),
        "component": scope.get("path"),
        "action": scope.get("method"),
    }


def _environment(scope: Dict[str, Any]) -> Dict[str, Any]:
    headers = {k.decode("latin1"): v.decode("latin1") for k, v in scope.get("headers", [])}
    client = scope.get("client") or (None, None)
    return {
        "method": scope.get("method"),
        "path": scope.get("path"),
        "query_string": scope.get("query_string", b"").decode("utf-8", errors="replace"),
        "user_agent": headers.get("user-agent"),
        "remote_addr": client[0],
    }


def _build_url(scope: Dict[str, Any]) -> str:
    scheme = scope.get("scheme", "http")
    headers = dict(scope.get("headers", []))
    host = headers.get(b"host", b"").decode("latin1") or "localhost"
    path = scope.get("path", "/")
    query = scope.get("query_string", b"").decode("utf-8", errors="replace")
    suffix = f"?{query}" if query else ""
    return f"{scheme}://{host}{path}{suffix}"
