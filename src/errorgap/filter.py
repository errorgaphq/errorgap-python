from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, Optional, Tuple

FILTERED = "[FILTERED]"
TRUNCATED = "[TRUNCATED]"
CIRCULAR = "[CIRCULAR]"
MAX_STRING = 4096
MAX_ITEMS = 128
MAX_DEPTH = 8


def filter_params(params: Dict[str, Any], filter_keys: Iterable[Any]) -> Dict[str, Any]:
    """Mask sensitive keys at any depth (inside lists too) and make the value
    safe to serialize: long strings and large or deeply nested collections are
    cut, reference cycles are broken, and objects JSON cannot carry become
    strings. ``filter_keys`` are substrings (case-insensitive) or compiled
    patterns."""
    keys = tuple(k if isinstance(k, re.Pattern) else str(k).lower() for k in filter_keys)
    return _as_dict(_walk(params, keys, 0, set()))


def clean(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Truncate and break cycles without masking anything."""
    return _as_dict(_walk(value or {}, None, 0, set()))


def truncate(value: str, limit: int = MAX_STRING) -> str:
    return value[:limit] + TRUNCATED if len(value) > limit else value


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _walk(value: Any, keys: Optional[Tuple[Any, ...]], depth: int, seen: set) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return truncate(value)
    if isinstance(value, (bytes, bytearray)):
        return truncate(bytes(value).decode("utf-8", errors="replace"))
    if isinstance(value, (dict, list, tuple, set, frozenset)):
        if id(value) in seen:
            return CIRCULAR
        if depth >= MAX_DEPTH:
            return TRUNCATED
        seen.add(id(value))
        try:
            if isinstance(value, dict):
                out: Dict[str, Any] = {}
                for key, item in value.items():
                    if len(out) >= MAX_ITEMS:
                        break
                    name = truncate(str(key), 256)
                    out[name] = (
                        FILTERED
                        if keys is not None and _is_sensitive(name, keys)
                        else _walk(item, keys, depth + 1, seen)
                    )
                return out
            return [_walk(item, keys, depth + 1, seen) for item in list(value)[:MAX_ITEMS]]
        finally:
            seen.discard(id(value))
    try:
        return truncate(str(value))
    except Exception:  # noqa: BLE001 — a broken __str__ must not lose the notice
        return "[UNPRINTABLE]"


def _is_sensitive(key: str, keys: Tuple[Any, ...]) -> bool:
    lowered = key.lower()
    for needle in keys:
        if isinstance(needle, re.Pattern):
            if needle.search(key):
                return True
        elif needle and needle in lowered:
            return True
    return False
