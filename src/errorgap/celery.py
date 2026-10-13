"""Celery: report task failures and time each task as a ``job`` transaction.

::

    import errorgap
    from errorgap.celery import install

    errorgap.init(...)
    install()          # once, in the module that creates the Celery app

A failed task is reported with its name, id, queue, retry count and
arguments (``filter_keys`` apply to keyword arguments), and linked to the
task's transaction. Celery's own retry handling is untouched.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from .apm import Transaction
from .transaction_context import _current, new_transaction_id

_installed = False
# task id -> (transaction, start time, ContextVar token)
_running: Dict[str, Tuple[Transaction, float, Any]] = {}
_MAX_RUNNING = 10_000


def install() -> bool:
    """Connect to Celery's task signals. Returns ``False`` when Celery is not
    installed. Safe to call more than once."""
    global _installed
    if _installed:
        return True
    try:
        from celery import signals
    except Exception:  # noqa: BLE001 — Celery is optional
        return False
    signals.task_prerun.connect(_on_prerun, weak=False, dispatch_uid="errorgap.prerun")
    signals.task_postrun.connect(_on_postrun, weak=False, dispatch_uid="errorgap.postrun")
    signals.task_failure.connect(_on_failure, weak=False, dispatch_uid="errorgap.failure")
    _installed = True
    return True


def _queue(task: Any) -> str:
    try:
        info = getattr(task.request, "delivery_info", None) or {}
        return str(info.get("routing_key") or info.get("queue") or getattr(task, "queue", None) or "default")
    except Exception:  # noqa: BLE001
        return "default"


def _on_prerun(task_id: Optional[str] = None, task: Any = None, **_kwargs: Any) -> None:
    try:
        if task_id is None or len(_running) >= _MAX_RUNNING:
            return
        txn = Transaction(
            kind="job",
            id=new_transaction_id(),
            job_class=getattr(task, "name", None) or "celery.task",
            queue=_queue(task),
            occurred_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        )
        # Errors reported while the task runs carry its transaction id.
        token = _current.set(txn.id)
        _running[task_id] = (txn, time.perf_counter(), token)
    except Exception:  # noqa: BLE001 — never break a task
        pass


def _on_postrun(task_id: Optional[str] = None, **_kwargs: Any) -> None:
    try:
        entry = _running.pop(task_id or "", None)
        if entry is None:
            return
        txn, start, token = entry
        try:
            _current.reset(token)
        except Exception:  # noqa: BLE001 — a different context: just clear it
            _current.set(None)
        txn.duration_ms = (time.perf_counter() - start) * 1000.0
        import errorgap

        errorgap.notify_transaction(txn)
    except Exception:  # noqa: BLE001
        pass


def _on_failure(
    task_id: Optional[str] = None,
    exception: Optional[BaseException] = None,
    args: Any = None,
    kwargs: Any = None,
    traceback: Any = None,
    sender: Any = None,
    **_kwargs: Any,
) -> None:
    try:
        if exception is None:
            return
        if getattr(exception, "__traceback__", None) is None and traceback is not None:
            exception.__traceback__ = traceback
        import errorgap

        request = getattr(sender, "request", None)
        errorgap.notify(
            exception,
            context={"component": "celery", "action": getattr(sender, "name", None) or "celery.task"},
            environment={
                "queue": _queue(sender),
                "job_id": task_id,
                "retries": getattr(request, "retries", None),
            },
            params={"args": list(args or []), "kwargs": dict(kwargs or {})},
        )
    except Exception:  # noqa: BLE001
        pass
