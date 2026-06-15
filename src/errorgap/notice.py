from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .backtrace import parse_backtrace
from .configuration import Configuration
from .filter import filter_params
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
    if context:
        default_context.update(context)

    return {
        "project_id": configuration.project_id,
        "received_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "errors": [
            {
                "type": _error_type(exc),
                "message": str(exc),
                "backtrace": parse_backtrace(exc, configuration.root_directory),
            }
        ],
        "context": default_context,
        "environment": environment or {},
        "session": session or {},
        "params": filter_params(params or {}, configuration.filter_keys),
    }


def _error_type(exc: BaseException) -> str:
    return exc.__class__.__name__
