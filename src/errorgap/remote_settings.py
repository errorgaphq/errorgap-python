"""The project's remote settings: what errorgap wants this app to send.

Someone can turn errors or performance data off for a project in errorgap
(Project settings › What SDKs send) and running apps follow within a poll
interval, with no deploy. Read from ``GET /api/projects/:slug/config`` on a
background thread. Until the first answer, and whenever errorgap cannot be
reached, everything stays on.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Callable, Dict, Optional
from urllib import request as urlrequest

from .version import VERSION

FIELDS = {"errors": "errors_enabled", "apm": "apm_enabled", "logs": "logs_enabled"}
DEFAULT_INTERVAL = 600.0
MIN_INTERVAL = 60.0


class RemoteSettings:
    def __init__(self, configuration: Callable[[], Any]) -> None:
        self._configuration = configuration
        self._settings: Dict[str, Any] = {}
        self._interval = DEFAULT_INTERVAL
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._pid: Optional[int] = None
        self._stop = threading.Event()

    def enabled(self, kind: str) -> bool:
        """False only when errorgap has said to stop sending this kind of data."""
        if not getattr(self._configuration(), "remote_settings", True):
            return True
        self._ensure_polling()
        return self._settings.get(FIELDS[kind]) is not False

    def refresh(self) -> bool:
        """Fetch now, on this thread. Returns whether the settings were read."""
        configuration = self._configuration()
        if not configuration.project_slug:
            return False
        url = f"{configuration.endpoint.rstrip('/')}/api/projects/{configuration.project_slug}/config"
        headers = {"User-Agent": f"errorgap-python/{VERSION}"}
        if configuration.api_key:
            headers["X-Errorgap-Project-Key"] = configuration.api_key
        try:
            req = urlrequest.Request(url, method="GET", headers=headers)
            with urlrequest.urlopen(req, timeout=float(configuration.timeout or 5)) as response:
                if response.status != 200:
                    return False
                body = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001 — unreachable or not JSON: keep what we have
            return False
        if not isinstance(body, dict):
            return False
        self._settings = body
        try:
            seconds = float(body.get("poll_interval_seconds") or 0)
        except (TypeError, ValueError):
            seconds = 0.0
        self._interval = seconds if seconds >= MIN_INTERVAL else DEFAULT_INTERVAL
        return True

    def stop(self) -> None:
        self._stop.set()

    def _ensure_polling(self) -> None:
        # A forked worker (gunicorn, Celery prefork) has the settings but not
        # the thread: start its own.
        if self._pid == os.getpid() and self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            if self._pid == os.getpid() and self._thread is not None and self._thread.is_alive():
                return
            self._pid = os.getpid()
            self._stop = threading.Event()
            self._thread = threading.Thread(target=self._run, name="errorgap-settings", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        stop = self._stop
        while not stop.is_set():
            self.refresh()
            stop.wait(self._interval)
