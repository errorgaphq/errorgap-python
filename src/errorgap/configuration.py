from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

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

    def validate(self) -> None:
        if not self.project_slug or not str(self.project_slug).strip():
            raise ValueError("Errorgap project_slug is required")

    def get_logger(self) -> logging.Logger:
        return self.logger or logging.getLogger("errorgap")
