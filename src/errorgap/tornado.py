"""Tornado: report handler errors and time each request.

Tornado has no middleware, so this is a mixin for your handlers (put it on
the base class they share)::

    import tornado.web
    from errorgap.tornado import ErrorgapMixin

    class BaseHandler(ErrorgapMixin, tornado.web.RequestHandler):
        ...

Unhandled exceptions are reported (not ``HTTPError`` below 500, which is a
deliberate response) and, with ``apm_enabled``, each request is a transaction
grouped by the handler's route pattern.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from .apm import SpanCollector, Transaction, browser_trace_id
from .transaction_context import _current, new_transaction_id


class ErrorgapMixin:
    """Mix into a ``tornado.web.RequestHandler`` (before it in the bases)."""

    _errorgap_txn: Optional[Transaction] = None
    _errorgap_start: float = 0.0
    _errorgap_token: Any = None

    def prepare(self) -> Any:  # type: ignore[override]
        request = self.request  # type: ignore[attr-defined]
        self._errorgap_txn = Transaction(
            kind="web",
            id=new_transaction_id(),
            trace_id=browser_trace_id(request.headers.get("x-errorgap-trace")),
            method=request.method,
            path_raw=request.path,
            occurred_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        )
        self._errorgap_start = time.perf_counter()
        # Errors reported while the request runs carry its transaction id.
        self._errorgap_token = _current.set(self._errorgap_txn.id)
        return super().prepare()  # type: ignore[misc]

    @property
    def errorgap_spans(self) -> Optional[SpanCollector]:
        """The span collector for this request's transaction."""
        return self._errorgap_txn.spans if self._errorgap_txn is not None else None

    def log_exception(self, typ: Any, value: Any, tb: Any) -> None:  # type: ignore[override]
        try:
            status = getattr(value, "status_code", 500)
            if isinstance(value, BaseException) and (not _is_http_error(value) or status >= 500):
                import errorgap

                request = self.request  # type: ignore[attr-defined]
                if getattr(value, "__traceback__", None) is None and tb is not None:
                    value.__traceback__ = tb
                errorgap.notify(
                    value,
                    context={
                        "url": f"{request.protocol}://{request.host}{request.path}",
                        "component": self._errorgap_route() or request.path,
                        "action": request.method,
                    },
                    environment={
                        "method": request.method,
                        "path": request.path,
                        "user_agent": request.headers.get("user-agent"),
                        "remote_addr": request.remote_ip,
                    },
                    params={key: [v.decode("utf-8", "replace") for v in values] for key, values in request.query_arguments.items()},
                )
        except Exception:  # noqa: BLE001 — reporting must never break the handler
            pass
        super().log_exception(typ, value, tb)  # type: ignore[misc]

    def on_finish(self) -> None:  # type: ignore[override]
        try:
            txn = self._errorgap_txn
            if txn is not None:
                import errorgap

                txn.status_code = self.get_status()  # type: ignore[attr-defined]
                txn.duration_ms = (time.perf_counter() - self._errorgap_start) * 1000.0
                txn.path = self._errorgap_route() or txn.path_raw
                errorgap.notify_transaction(txn)
            if self._errorgap_token is not None:
                try:
                    _current.reset(self._errorgap_token)
                except Exception:  # noqa: BLE001 — finished in another context
                    _current.set(None)
        except Exception:  # noqa: BLE001
            pass
        super().on_finish()  # type: ignore[misc]

    def _errorgap_route(self) -> Optional[str]:
        """The matched rule's pattern (``/orders/([0-9]+)``), which groups
        requests better than the concrete path."""
        try:
            for rule in self.application.wildcard_router.rules:  # type: ignore[attr-defined]
                if rule.target is self.__class__ and rule.matcher.match(self.request) is not None:  # type: ignore[attr-defined]
                    pattern = getattr(rule.matcher, "regex", None)
                    if pattern is not None:
                        return pattern.pattern.rstrip("$")
        except Exception:  # noqa: BLE001
            return None
        return None


def _is_http_error(value: BaseException) -> bool:
    try:
        from tornado.web import HTTPError

        return isinstance(value, HTTPError)
    except Exception:  # noqa: BLE001
        return False
