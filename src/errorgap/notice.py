from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .backtrace import exception_chain, parse_backtrace
from .configuration import Configuration
from .filter import clean, filter_params, truncate
from .version import VERSION


def build_notice(
    exc: BaseException,
    configuration: Configuration,
    context: Optional[Dict[str, Any]] = None,
    environment: Optional[Dict[str, Any]] = None,
    session: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    default_context: Dict[str, Any] = {
        "notifier": "errorgap-python",
        "notifier_version": VERSION,
        "environment": configuration.environment,
        "root_directory": configuration.root_directory,
    }
    if configuration.release:
        default_context["release"] = configuration.release
    causes = [
        {"type": _error_type(link), "message": truncate(_message(link), MAX_MESSAGE_LENGTH)}
        for link in exception_chain(exc)[1:]
    ]
    if causes:
        default_context["causes"] = causes
    default_context.update(clean(context))

    return {
        "project_id": configuration.project_id,
        "received_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "errors": [
            {
                "type": _error_type(exc),
                "message": truncate(_message(exc), MAX_MESSAGE_LENGTH),
                "backtrace": parse_backtrace(exc, configuration.root_directory),
            }
        ],
        "context": default_context,
        "environment": clean(environment),
        "session": filter_params(session or {}, configuration.filter_keys),
        "params": filter_params(params or {}, configuration.filter_keys),
    }


MAX_MESSAGE_LENGTH = 8192


def _message(exc: BaseException) -> str:
    try:
        return str(exc)
    except Exception:  # noqa: BLE001 — a broken __str__ must not lose the notice
        return ""


def _error_type(exc: BaseException) -> str:
    return exc.__class__.__name__
