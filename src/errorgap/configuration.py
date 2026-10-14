from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .release import detect_release

DEFAULT_FILTER_KEYS = (
    "password",
    "password_confirmation",
    "token",
    "secret",
    "api_key",
    "authorization",
    "cookie",
)


def _default_environment() -> str:
    return os.environ.get("ERRORGAP_ENVIRONMENT") or os.environ.get("ENV") or "development"


@dataclass
class Configuration:
    endpoint: str = field(
        default_factory=lambda: os.environ.get("ERRORGAP_ENDPOINT", "http://127.0.0.1:3030")
    )
    project_slug: Optional[str] = field(
        default_factory=lambda: os.environ.get("ERRORGAP_PROJECT_SLUG")
    )
    project_id: Optional[str] = field(
        default_factory=lambda: os.environ.get("ERRORGAP_PROJECT_ID")
    )
    api_key: Optional[str] = field(default_factory=lambda: os.environ.get("ERRORGAP_API_KEY"))
    environment: str = field(default_factory=_default_environment)
    root_directory: str = field(default_factory=os.getcwd)
    async_: bool = True
    logger: Optional[logging.Logger] = None
    filter_keys: tuple = DEFAULT_FILTER_KEYS
    apm_enabled: bool = False
    apm_sample_rate: float = 1.0
    # Sign-ins to this app (Security › Logins). Off until you opt in: they
    # carry user names and IPs.
    auth_events: bool = False
    # The app's name in Security › Logins; defaults to the project slug.
    app_name: Optional[str] = field(default_factory=lambda: os.environ.get("ERRORGAP_APP_NAME"))

    # Seconds allowed for each request to errorgap.
    timeout: float = 5.0
    # Payloads held for the background sender; the oldest is dropped when the
    # queue is full.
    queue_size: int = 100
    # The deployed version or commit, sent as ``context.release``. Unset, it is
    # read from the hosting platform's commit variable or the git checkout.
    release: Optional[str] = None
    # Environments in which nothing is sent.
    ignore_environments: List[str] = field(
        default_factory=lambda: [
            name.strip()
            for name in os.environ.get("ERRORGAP_IGNORE_ENVIRONMENTS", "").split(",")
            if name.strip()
        ]
    )
    # Sees each notice (a dict) before it is sent. Change it in place or
    # return a replacement; return ``False`` to drop it.
    before_notify: Optional[Callable[[Dict[str, Any]], Any]] = None

    # Follow the project's settings in errorgap (Project settings › What SDKs
    # send): stop sending errors or performance data when they are switched
    # off there. ``ERRORGAP_REMOTE_SETTINGS=false`` turns this off.
    remote_settings: bool = field(
        default_factory=lambda: os.environ.get("ERRORGAP_REMOTE_SETTINGS", "").strip().lower() != "false"
    )

    def __post_init__(self) -> None:
        if self.release is None:
            self.release = detect_release(self.root_directory)

    def ignored_environment(self) -> bool:
        return self.environment in (self.ignore_environments or [])

    def validate(self) -> None:
        if not self.project_slug or not str(self.project_slug).strip():
            raise ValueError("Errorgap project_slug is required")

    def get_logger(self) -> logging.Logger:
        return self.logger or logging.getLogger("errorgap")
