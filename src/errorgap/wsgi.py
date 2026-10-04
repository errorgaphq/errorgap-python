from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Iterator, Optional

from .apm import Transaction, browser_trace_id
from .transaction_context import _current, new_transaction_id

#: WSGI environ key a framework integration sets to the matched route
#: template (for example Flask's ``/orders/<int:id>``), used to group requests.
ROUTE_KEY = "errorgap.route"
#: WSGI environ key holding the request's :class:`Transaction`, for recording
#: spans from views: ``environ["errorgap.transaction"].spans.database(...)``.
TRANSACTION_KEY = "errorgap.transaction"


class ErrorgapMiddleware:
    """WSGI middleware that times each request as an APM transaction.

    Errors reported while the request runs carry its transaction id, and the
    errorgap browser SDK's ``x-errorgap-trace`` header links the browser's
    view of the call to it. Transactions are sent only with ``apm_enabled``.
    """

    def __init__(self, app: Callable[..., Iterable[bytes]]) -> None:
        self.app = app

    def __call__(self, environ: dict, start_response: Callable[..., Any]) -> Iterable[bytes]:
        txn = Transaction(
            kind="web",
            id=new_transaction_id(),
            trace_id=browser_trace_id(environ.get("HTTP_X_ERRORGAP_TRACE")),
            method=environ.get("REQUEST_METHOD"),
            path_raw=environ.get("PATH_INFO") or "/",
            occurred_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        )
        environ[TRANSACTION_KEY] = txn
        start = time.perf_counter()

        def _start_response(status: str, headers: Any, exc_info: Any = None) -> Any:
            try:
                txn.status_code = int(status.split(" ", 1)[0])
            except (ValueError, IndexError):
                pass
            return start_response(status, headers, exc_info) if exc_info else start_response(status, headers)

        token = _current.set(txn.id)
        try:
            body = self.app(environ, _start_response)
        except BaseException:
            txn.status_code = 500
            _current.reset(token)
            _finish(txn, environ, start)
            raise
        _current.reset(token)
        return _ClosingIterator(body, txn, environ, start)


class _ClosingIterator:
    """Keeps the transaction current while the response body is produced, and
    records it once the server closes the response."""

    def __init__(self, body: Iterable[bytes], txn: Transaction, environ: dict, start: float) -> None:
        self._body = body
        self._iter: Optional[Iterator[bytes]] = None
        self._txn = txn
        self._environ = environ
        self._start = start
        self._closed = False

    def __iter__(self) -> "_ClosingIterator":
        return self

    def __next__(self) -> bytes:
        if self._iter is None:
            self._iter = iter(self._body)
        token = _current.set(self._txn.id)
        try:
            return next(self._iter)
        except StopIteration:
            raise
        except BaseException:
            self._txn.status_code = 500
            raise
        finally:
            _current.reset(token)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            close = getattr(self._body, "close", None)
            if close is not None:
                close()
        finally:
            _finish(self._txn, self._environ, self._start)


def _finish(txn: Transaction, environ: dict, start: float) -> None:
    import errorgap

    txn.duration_ms = (time.perf_counter() - start) * 1000.0
    txn.path = environ.get(ROUTE_KEY) or txn.path_raw
    errorgap.notify_transaction(txn)


__all__ = ["ErrorgapMiddleware", "ROUTE_KEY", "TRANSACTION_KEY"]
