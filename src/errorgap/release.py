from __future__ import annotations

import os
import re
from typing import Mapping, Optional

ENV_KEYS = (
    "ERRORGAP_RELEASE",
    "SOURCE_VERSION",
    "HEROKU_SLUG_COMMIT",
    "HEROKU_BUILD_COMMIT",
    "RENDER_GIT_COMMIT",
    "RAILWAY_GIT_COMMIT_SHA",
    "VERCEL_GIT_COMMIT_SHA",
    "KAMAL_VERSION",
    "GIT_COMMIT",
    "GIT_SHA",
)

_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")


def detect_release(root_directory: str, env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Which commit is running, when ``release`` is not configured: the commit
    variable hosting platforms export, then the checkout's ``.git/HEAD``."""
    env = os.environ if env is None else env
    for key in ENV_KEYS:
        value = (env.get(key) or "").strip()
        if value:
            return value
    try:
        return _git_head(root_directory)
    except Exception:  # noqa: BLE001 — detection is best-effort
        return None


def _git_head(root: str) -> Optional[str]:
    if not root:
        return None
    git = os.path.join(root, ".git")
    head = _read(os.path.join(git, "HEAD"))
    if head is None:
        return None
    if not head.startswith("ref:"):
        return _sha(head)
    ref = head[4:].strip()
    loose = _read(os.path.join(git, ref))
    if loose is not None:
        return _sha(loose)
    packed = _read(os.path.join(git, "packed-refs")) or ""
    for line in packed.splitlines():
        if line.strip().endswith(" " + ref):
            return _sha(line.strip().split(" ")[0])
    return None


def _read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(65536).strip()
    except OSError:
        return None


def _sha(value: str) -> Optional[str]:
    return value if _SHA.match(value) else None
