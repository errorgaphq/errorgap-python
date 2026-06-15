from __future__ import annotations

from typing import Any, Callable, Dict

from . import notify


class ErrorgapMiddleware:
    """Pure ASGI middleware that reports unhandled exceptions to Errorgap.

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

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            notify(
                exc,
                sync=True,
                context=_context(scope),
                environment=_environment(scope),
            )
            raise


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
