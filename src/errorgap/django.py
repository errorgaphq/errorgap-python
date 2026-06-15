from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from . import notify


class ErrorgapMiddleware:
    """Django middleware that reports unhandled exceptions to Errorgap.

    Add ``"errorgap.django.ErrorgapMiddleware"`` to ``MIDDLEWARE``. Place it
    early so it sees exceptions raised by inner middleware too.
    """

    def __init__(self, get_response: Callable[..., Any]):
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        return self.get_response(request)

    def process_exception(self, request: Any, exception: BaseException) -> Optional[Any]:
        notify(
            exception,
            sync=True,
            context=_context(request),
            environment=_environment(request),
            session=_session(request),
            params=_params(request),
        )
        # Returning None lets Django continue its exception handling chain.
        return None


def _context(request: Any) -> Dict[str, Any]:
    try:
        resolver = getattr(request, "resolver_match", None)
        view_name = resolver.view_name if resolver else None
    except Exception:  # noqa: BLE001
        view_name = None
    try:
        url = request.build_absolute_uri()
    except Exception:  # noqa: BLE001
        url = getattr(request, "path", None)
    return {
        "url": url,
        "component": view_name or getattr(request, "path", None),
        "action": getattr(request, "method", None),
    }


def _environment(request: Any) -> Dict[str, Any]:
    meta = getattr(request, "META", {}) or {}
    return {
        "method": getattr(request, "method", None),
        "path": getattr(request, "path", None),
        "query_string": meta.get("QUERY_STRING"),
        "user_agent": meta.get("HTTP_USER_AGENT"),
        "remote_addr": meta.get("REMOTE_ADDR"),
    }


def _session(request: Any) -> Dict[str, Any]:
    try:
        session = getattr(request, "session", None)
        if session is None:
            return {}
        return dict(session.items())
    except Exception:  # noqa: BLE001
        return {}


def _params(request: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        for key, value in (getattr(request, "GET", {}) or {}).items():
            out[key] = value
        post = getattr(request, "POST", None)
        if post:
            for key, value in post.items():
                out[key] = value
    except Exception:  # noqa: BLE001
        return out
    return out
