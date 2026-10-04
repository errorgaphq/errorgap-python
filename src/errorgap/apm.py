from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from .configuration import Configuration

#: The header the errorgap browser SDK sends with API calls.
TRACE_HEADER = "x-errorgap-trace"

_UUID = re.compile(r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_STRING_LITERAL = re.compile(r"'(?:''|[^'])*'")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
_WHITESPACE = re.compile(r"\s+")


def browser_trace_id(header: Union[str, bytes, None]) -> Optional[str]:
    """The trace id in an ``x-errorgap-trace`` header value, lowercased, or
    ``None`` unless it is a well-formed UUID."""
    if isinstance(header, bytes):
        header = header.decode("latin-1")
    if not isinstance(header, str):
        return None
    value = header.strip().lower()
    return value if _UUID.match(value) else None


def normalize_sql(sql: str) -> str:
    """Strip literals so query shapes aggregate: '…' and numbers become ?."""
    sql = _STRING_LITERAL.sub("?", sql)
    sql = _NUMBER.sub("?", sql)
    return _WHITESPACE.sub(" ", sql).strip()


@dataclass
class Span:
    kind: str
    duration_ms: float
    sql: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    function: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"kind": self.kind, "duration_ms": self.duration_ms}
        if self.sql is not None:
            payload["sql"] = self.sql
        if self.file is not None:
            payload["file"] = self.file
        if self.line is not None:
            payload["line"] = self.line
        if self.function is not None:
            payload["fn_name"] = self.function
        return payload


class SpanCollector:
    """Collects the spans recorded while a transaction or job is in flight."""

    def __init__(self) -> None:
        self._spans: List[Span] = []

    def add(self, span: Span) -> None:
        self._spans.append(span)

    def database(
        self,
        sql: str,
        duration_ms: float,
        file: Optional[str] = None,
        line: Optional[int] = None,
        function: Optional[str] = None,
    ) -> None:
        self.add(Span("db", duration_ms, normalize_sql(sql), file, line, function))

    def external(
        self,
        duration_ms: float,
        file: Optional[str] = None,
        line: Optional[int] = None,
        function: Optional[str] = None,
    ) -> None:
        self.add(Span("http", duration_ms, None, file, line, function))

    def snapshot(self) -> List[Span]:
        return list(self._spans)


@dataclass
class Transaction:
    """An APM transaction: a web interaction (``kind="web"``) or a background
    job (``kind="job"``)."""

    kind: str = "web"
    #: Links the errors raised during this transaction to it.
    id: Optional[str] = None
    #: The browser's ``x-errorgap-trace`` header (see :func:`browser_trace_id`).
    trace_id: Optional[str] = None
    method: Optional[str] = None
    #: Normalized route template used for grouping, e.g. ``/orders/<int:id>``.
    path: Optional[str] = None
    #: Concrete path for one request, e.g. ``/orders/123``.
    path_raw: Optional[str] = None
    status_code: Optional[int] = None
    duration_ms: float = 0.0
    environment: Optional[str] = None
    #: ISO-8601; defaults to now.
    occurred_at: Optional[str] = None
    spans: SpanCollector = field(default_factory=SpanCollector)
    job_class: Optional[str] = None
    queue: Optional[str] = None

    def to_payload(self, configuration: Configuration) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "kind": self.kind,
            "duration_ms": self.duration_ms,
            "environment": self.environment or configuration.environment,
            "occurred_at": self.occurred_at or _now(),
            "spans": [span.to_payload() for span in self.spans.snapshot()],
        }
        for key in ("id", "trace_id", "method", "path", "path_raw", "status_code", "job_class", "queue"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
