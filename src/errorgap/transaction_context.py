from __future__ import annotations

import contextlib
import uuid
from contextvars import ContextVar
from typing import Iterator, Optional

# The APM transaction the current thread or task is running in, so errors
# reported during it carry its id as ``context.transaction_id`` and errorgap
# links each error to the request or job that raised it. A ContextVar follows
# awaits and never leaks into a concurrent request or thread.
_current: ContextVar[Optional[str]] = ContextVar("errorgap_transaction_id", default=None)


def current_transaction_id() -> Optional[str]:
    """The id of the transaction running now, if any."""
    return _current.get()


def new_transaction_id() -> str:
    """A new random transaction id (a UUID)."""
    return str(uuid.uuid4())


@contextlib.contextmanager
def transaction_scope(transaction_id: str) -> Iterator[str]:
    """Make ``transaction_id`` current for the ``with`` block."""
    token = _current.set(transaction_id)
    try:
        yield transaction_id
    finally:
        _current.reset(token)
