from __future__ import annotations

import sys
from types import TracebackType
from typing import Optional, Type

from .client import Client

_installed = False
_previous_excepthook = None


def install_excepthook(client: Client) -> None:
    global _installed, _previous_excepthook
    if _installed:
        return
    _previous_excepthook = sys.excepthook
    _installed = True

    def _hook(
        exc_type: Type[BaseException],
        exc: BaseException,
        tb: Optional[TracebackType],
    ) -> None:
        try:
            exc.__traceback__ = tb
            client.notify(exc, sync=True, context={"source": "sys.excepthook"})
        finally:
            if _previous_excepthook is not None:
                _previous_excepthook(exc_type, exc, tb)

    sys.excepthook = _hook


def uninstall_excepthook() -> None:
    global _installed, _previous_excepthook
    if not _installed:
        return
    sys.excepthook = _previous_excepthook or sys.__excepthook__
    _previous_excepthook = None
    _installed = False
