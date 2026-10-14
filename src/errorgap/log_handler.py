"""Report ``logging`` errors to Errorgap.

::

    import logging
    from errorgap.log_handler import ErrorgapHandler

    logging.getLogger().addHandler(ErrorgapHandler())   # ERROR and above

``logger.exception(...)`` (a record with ``exc_info``) reports that exception.
A plain ``logger.error("…")`` is reported as a :class:`LoggedError` carrying
the message. The logger name and level go in the notice's context.
"""

from __future__ import annotations

import logging
from typing import Any, Dict


class LoggedError(Exception):
    """An error-level log record that had no exception attached."""


class ErrorgapHandler(logging.Handler):
    def __init__(self, level: int = logging.ERROR) -> None:
        super().__init__(level)

    def emit(self, record: logging.LogRecord) -> None:
        # The SDK logs its own delivery problems: reporting those would loop.
        if record.name == "errorgap" or record.name.startswith("errorgap."):
            return
        try:
            import errorgap

            context: Dict[str, Any] = {
                "source": "logging",
                "component": record.name,
                "severity": record.levelname.lower(),
            }
            exc = record.exc_info[1] if record.exc_info else None
            if isinstance(exc, BaseException):
                context["log_message"] = record.getMessage()
                errorgap.notify(exc, context=context)
            else:
                error = LoggedError(record.getMessage())
                errorgap.notify(
                    error,
                    context={**context, "file": record.pathname, "line": record.lineno, "function": record.funcName},
                )
        except Exception:  # noqa: BLE001 — a log handler must never raise
            self.handleError(record)
