"""aiohttp server middleware.

::

    from aiohttp import web
    from errorgap.aiohttp import errorgap_middleware

    app = web.Application(middlewares=[errorgap_middleware])

Reports unhandled exceptions (not ``HTTPException`` responses such as 404)
and, with ``apm_enabled``, times each request as a transaction grouped by its
route (``/orders/{id}``).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from aiohttp import web

from .apm import SpanCollector, Transaction, browser_trace_id
from .transaction_context import new_transaction_id, transaction_scope

#: Request key holding the request's :class:`~errorgap.apm.Transaction`.
TRANSACTION_KEY = "errorgap.transaction"


@web.middleware
async def errorgap_middleware(
    request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
) -> web.StreamResponse:
    import errorgap

    txn = Transaction(
        kind="web",
        id=new_transaction_id(),
        trace_id=browser_trace_id(request.headers.get("x-errorgap-trace")),
        method=request.method,
        path_raw=request.path,
        occurred_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )
    request[TRANSACTION_KEY] = txn
    start = time.perf_counter()
    try:
        with transaction_scope(txn.id or new_transaction_id()):
            try:
                response = await handler(request)
                txn.status_code = response.status
                return response
            except web.HTTPException as http_error:
                # A deliberate response (redirect, 404, 403), not a failure.
                txn.status_code = http_error.status
                raise
            except Exception as exc:
                txn.status_code = 500
                errorgap.notify(
                    exc,
                    context={
                        "url": str(request.url.with_query(None)),
                        "component": _route(request) or request.path,
                        "action": request.method,
                    },
                    environment={
                        "method": request.method,
                        "path": request.path,
                        "user_agent": request.headers.get("user-agent"),
                        "remote_addr": request.remote,
                    },
                    params=dict(request.query),
                )
                raise
    finally:
        txn.duration_ms = (time.perf_counter() - start) * 1000.0
        txn.path = _route(request) or txn.path_raw
        errorgap.notify_transaction(txn)


def spans(request: web.Request) -> Optional[SpanCollector]:
    """The span collector for the request's transaction."""
    txn = request.get(TRANSACTION_KEY)
    return txn.spans if txn is not None else None


def _route(request: web.Request) -> Optional[str]:
    try:
        resource: Any = request.match_info.route.resource
        return resource.canonical if resource is not None else None
    except Exception:  # noqa: BLE001
        return None
