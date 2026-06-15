from __future__ import annotations

from typing import Any, Dict, Iterable

FILTERED = "[FILTERED]"


def filter_params(params: Dict[str, Any], filter_keys: Iterable[str]) -> Dict[str, Any]:
    lowered = tuple(k.lower() for k in filter_keys)
    return _walk(params, lowered)


def _walk(value: Dict[str, Any], lowered: tuple) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, val in value.items():
        if _is_sensitive(str(key), lowered):
            out[key] = FILTERED
        elif isinstance(val, dict):
            out[key] = _walk(val, lowered)
        else:
            out[key] = val
    return out


def _is_sensitive(key: str, lowered: tuple) -> bool:
    lk = key.lower()
    return any(needle in lk for needle in lowered)
