"""Sign-ins to this app, shown beside SSH logins in errorgap's
Security › Logins. Only who, from where and the result are sent: never
passwords, tokens or session ids."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .configuration import Configuration
from .version import VERSION

OUTCOMES = ("success", "failure", "password_reset", "mfa_failure", "locked")


def _request_fields(request: Any) -> Dict[str, Optional[str]]:
    """IP, user agent and path from a Django, Flask/Werkzeug or Starlette
    request. Paths never include the query string."""
    meta = getattr(request, "META", None)
    if isinstance(meta, dict):  # Django
        return {
            "ip": meta.get("REMOTE_ADDR"),
            "user_agent": meta.get("HTTP_USER_AGENT"),
            "path": f"{request.method} {request.path}",
        }
    client = getattr(request, "client", None)
    url = getattr(request, "url", None)
    if client is not None and hasattr(url, "path"):  # Starlette / FastAPI
        return {
            "ip": getattr(client, "host", None),
            "user_agent": request.headers.get("user-agent"),
            "path": f"{request.method} {url.path}",
        }
    headers = getattr(request, "headers", None) or {}
    return {  # Flask / Werkzeug
        "ip": getattr(request, "remote_addr", None),
        "user_agent": headers.get("User-Agent") if hasattr(headers, "get") else None,
        "path": f"{getattr(request, 'method', '')} {getattr(request, 'path', '')}".strip() or None,
    }


def build_sign_in(
    outcome: str,
    user: Any = None,
    request: Any = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """The event to send, or ``None`` for an unknown outcome."""
    if outcome not in OUTCOMES:
        return None
    if request is not None:
        found = _request_fields(request)
        ip = ip or found["ip"]
        user_agent = user_agent or found["user_agent"]
        path = path or found["path"]
    at = (occurred_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    event: Dict[str, Any] = {
        "occurred_at": at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "outcome": outcome,
    }
    name = "" if user is None else str(user).strip()
    if name:
        event["user"] = name
    if ip:
        event["ip"] = str(ip)
    if user_agent:
        event["user_agent"] = str(user_agent)[:512]
    if path:
        event["path"] = str(path)[:200]
    if method:
        event["method"] = str(method)
    return event


def sign_in_payload(event: Dict[str, Any], configuration: Configuration) -> Dict[str, Any]:
    return {
        "app": configuration.app_name or configuration.project_slug,
        "environment": configuration.environment,
        "sdk": f"errorgap-python {VERSION}",
        "events": [event],
    }
