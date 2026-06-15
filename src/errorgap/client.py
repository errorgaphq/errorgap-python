from __future__ import annotations

import json
import logging
import queue
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

from .configuration import Configuration
from .notice import build_notice
from .version import VERSION


@dataclass
class DeliveryResult:
    status: Optional[int] = None
    body: Optional[str] = None
    error: Optional[BaseException] = None
    queued: bool = False

    @property
    def success(self) -> bool:
        return self.error is None and self.status is not None and 200 <= self.status < 300


class Client:
    def __init__(self, configuration: Configuration):
        self._configuration = configuration
        self._queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def configure(self, configuration: Configuration) -> None:
        self._configuration = configuration

    @property
    def configuration(self) -> Configuration:
        return self._configuration

    def notify(
        self,
        exc: BaseException,
        context: Optional[Dict[str, Any]] = None,
        environment: Optional[Dict[str, Any]] = None,
        session: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        sync: bool = False,
    ) -> DeliveryResult:
        try:
            self._configuration.validate()
            notice = build_notice(
                exc,
                self._configuration,
                context=context,
                environment=environment,
                session=session,
                params=params,
            )
        except Exception as caught:  # noqa: BLE001 — SDK must not raise
            self._log(caught)
            return DeliveryResult(error=caught)

        if sync or not self._configuration.async_:
            return self.deliver(notice)

        self._ensure_worker()
        self._queue.put(notice)
        return DeliveryResult(queued=True, status=202)

    def deliver(self, notice: Dict[str, Any]) -> DeliveryResult:
        url = _notices_url(self._configuration)
        body = json.dumps(notice).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"errorgap-python/{VERSION}",
        }
        if self._configuration.api_key:
            headers["X-Errorgap-Project-Key"] = self._configuration.api_key

        req = urlrequest.Request(url, data=body, method="POST", headers=headers)
        try:
            with urlrequest.urlopen(req, timeout=10) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                return DeliveryResult(status=response.status, body=response_body)
        except urlerror.HTTPError as http_err:
            response_body = ""
            try:
                response_body = http_err.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            return DeliveryResult(status=http_err.code, body=response_body, error=http_err)
        except Exception as caught:  # noqa: BLE001 — network/socket errors
            self._log(caught)
            return DeliveryResult(error=caught)

    def flush(self, timeout: Optional[float] = None) -> None:
        """Block until all queued notices have been delivered."""
        with self._lock:
            worker = self._worker
        if worker is None:
            return
        self._queue.join() if timeout is None else _wait_join(self._queue, timeout)

    def shutdown(self, timeout: Optional[float] = None) -> None:
        """Flush and tear down the worker thread. Safe to call multiple times."""
        with self._lock:
            worker = self._worker
            self._worker = None
        if worker is None:
            return
        self.flush(timeout)
        self._queue.put(None)
        worker.join(timeout)

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._worker_loop, name="errorgap-delivery", daemon=True
            )
            self._worker.start()

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                self.deliver(item)
            finally:
                self._queue.task_done()

    def _log(self, exc: BaseException) -> None:
        logger = self._configuration.get_logger()
        if logger is None:
            return
        if isinstance(logger, logging.Logger):
            logger.warning("[errorgap] %s: %s", exc.__class__.__name__, exc)
        else:
            try:
                logger.warning(f"[errorgap] {exc.__class__.__name__}: {exc}")
            except Exception:  # noqa: BLE001
                pass


def _notices_url(configuration: Configuration) -> str:
    base = configuration.endpoint.rstrip("/")
    return f"{base}/api/projects/{configuration.project_slug}/notices"


def _wait_join(q: "queue.Queue[Any]", timeout: float) -> None:
    """queue.Queue has no join-with-timeout. Poll for emptiness."""
    import time

    deadline = time.monotonic() + timeout
    while q.unfinished_tasks > 0 and time.monotonic() < deadline:
        time.sleep(0.01)
