from __future__ import annotations

import json
import logging
import queue
import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib import error as urlerror
from urllib import request as urlrequest

from .apm import Transaction
from .configuration import Configuration
from .notice import build_notice
from .sign_ins import build_sign_in, sign_in_payload
from .transaction_context import current_transaction_id
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


class RateLimited(Exception):
    """Not sent: the server asked for a pause (``Retry-After``)."""


MAX_ATTEMPTS = 3
RETRY_DELAY = 30.0
BACKLOG_SIZE = 100
DEFAULT_RETRY_AFTER = 60
MAX_RETRY_AFTER = 300


def retryable(result: "DeliveryResult") -> bool:
    """Network failures and 5xx responses are worth another try. A 4xx is
    not: the server understood and refused, and after a 429 the payload is
    dropped so a limited project is not sent the same burst again."""
    if isinstance(result.error, RateLimited):
        return False
    if result.status is not None:
        return result.status >= 500
    return result.error is not None


class Client:
    def __init__(self, configuration: Configuration):
        self._configuration = configuration
        self._queue: "queue.Queue[Optional[Tuple[str, Dict[str, Any], int]]]" = queue.Queue()
        # Sending is paused until this monotonic time after a 429 or 503.
        self._paused_until = 0.0
        self._backlog = 0
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
            transaction_id = current_transaction_id()
            if transaction_id and "transaction_id" not in (context or {}):
                context = {**(context or {}), "transaction_id": transaction_id}
            if self._configuration.ignored_environment():
                return DeliveryResult(status=202, body="ignored environment")
            notice = build_notice(
                exc,
                self._configuration,
                context=context,
                environment=environment,
                session=session,
                params=params,
            )
            hooked = self._run_hook(notice)
            if hooked is None:
                return DeliveryResult(status=202, body="dropped by before_notify")
            notice = hooked
        except Exception as caught:  # noqa: BLE001 — SDK must not raise
            self._log(caught)
            return DeliveryResult(error=caught)

        if sync or not self._configuration.async_:
            return self.deliver(notice)
        return self._enqueue("notices", notice)

    def _run_hook(self, notice: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """A hook that raises is logged and skipped: a bug in a filter must
        not lose the error it was filtering."""
        hook = self._configuration.before_notify
        if hook is None:
            return notice
        try:
            result = hook(notice)
        except Exception as caught:  # noqa: BLE001
            self._log(caught)
            return notice
        if result is False:
            return None
        return result if isinstance(result, dict) and "errors" in result else notice

    def _enqueue(self, resource: str, payload: Dict[str, Any], attempt: int = 1) -> DeliveryResult:
        """Queue for the background sender. A full queue drops its oldest
        entry, so the newest errors survive a burst."""
        if self._configuration.ignored_environment():
            return DeliveryResult(status=204)
        self._ensure_worker()
        limit = max(1, int(self._configuration.queue_size or 100))
        while self._queue.qsize() >= limit:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        self._queue.put((resource, payload, attempt))
        return DeliveryResult(queued=True, status=202)

    def notify_transaction(self, transaction: Transaction, sync: bool = False) -> DeliveryResult:
        """Deliver an APM transaction. Dropped unless ``apm_enabled``, and
        sampled by ``apm_sample_rate``."""
        try:
            self._configuration.validate()
            if not self._configuration.apm_enabled:
                return DeliveryResult(status=204)
            rate = self._configuration.apm_sample_rate
            if not (rate >= 1 or (rate > 0 and random.random() < rate)):
                return DeliveryResult(status=204)
            payload = transaction.to_payload(self._configuration)
        except Exception as caught:  # noqa: BLE001 — SDK must not raise
            self._log(caught)
            return DeliveryResult(error=caught)

        if sync or not self._configuration.async_:
            return self._post("transactions", payload)

        return self._enqueue("transactions", payload)

    def sign_in(self, outcome: str, sync: bool = False, **fields: Any) -> DeliveryResult:
        """Report a sign-in to this app (Security › Logins). Dropped unless
        ``auth_events`` is on, or when the outcome is unknown."""
        try:
            self._configuration.validate()
            if not self._configuration.auth_events:
                return DeliveryResult(status=204)
            event = build_sign_in(outcome, **fields)
            if event is None:
                raise ValueError(f"unknown sign-in outcome {outcome!r}")
            payload = sign_in_payload(event, self._configuration)
        except Exception as caught:  # noqa: BLE001 — SDK must not raise
            self._log(caught)
            return DeliveryResult(error=caught)

        if sync or not self._configuration.async_:
            return self._post("logins/web", payload)

        return self._enqueue("logins/web", payload)

    def deliver(self, notice: Dict[str, Any]) -> DeliveryResult:
        return self._post("notices", notice)

    def _post(self, resource: str, payload: Dict[str, Any]) -> DeliveryResult:
        if self._configuration.ignored_environment():
            return DeliveryResult(status=204)
        if self.paused():
            return DeliveryResult(error=RateLimited("rate limited by the server, not sent"))
        try:
            url = _project_url(self._configuration, resource)
            # default=str: a value JSON cannot carry becomes a string rather
            # than losing the payload.
            body = json.dumps(payload, default=str).encode("utf-8")
        except Exception as caught:  # noqa: BLE001 — SDK must not raise
            self._log(caught)
            return DeliveryResult(error=caught)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"errorgap-python/{VERSION}",
        }
        if self._configuration.api_key:
            headers["X-Errorgap-Project-Key"] = self._configuration.api_key

        req = urlrequest.Request(url, data=body, method="POST", headers=headers)
        timeout = float(self._configuration.timeout or 5)
        try:
            with urlrequest.urlopen(req, timeout=timeout) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                return DeliveryResult(status=response.status, body=response_body)
        except urlerror.HTTPError as http_err:
            response_body = ""
            try:
                response_body = http_err.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            if http_err.code in (429, 503):
                self._pause_for(http_err.headers.get("Retry-After") if http_err.headers else None)
            return DeliveryResult(status=http_err.code, body=response_body, error=http_err)
        except Exception as caught:  # noqa: BLE001 — network/socket errors
            self._log(caught)
            return DeliveryResult(error=caught)

    def paused(self) -> bool:
        return time.monotonic() < self._paused_until

    def _pause_for(self, header: Optional[str]) -> None:
        text = (header or "").strip()
        seconds = int(text) if text.isdigit() else DEFAULT_RETRY_AFTER
        seconds = max(1, min(MAX_RETRY_AFTER, seconds))
        self._paused_until = time.monotonic() + seconds
        self._log(RateLimited(f"rate limited, pausing delivery for {seconds}s"))

    def _retry_later(self, resource: str, payload: Dict[str, Any], attempt: int) -> None:
        if attempt >= MAX_ATTEMPTS or self._backlog >= BACKLOG_SIZE:
            return
        self._backlog += 1

        def again() -> None:
            self._backlog -= 1
            self._enqueue(resource, payload, attempt + 1)

        timer = threading.Timer(RETRY_DELAY * attempt, again)
        timer.daemon = True
        timer.start()

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
                resource, payload, attempt = item
                result = self._post(resource, payload)
                if retryable(result):
                    self._retry_later(resource, payload, attempt)
            except Exception as caught:  # noqa: BLE001 — the worker must survive
                self._log(caught)
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


def _project_url(configuration: Configuration, resource: str) -> str:
    base = configuration.endpoint.rstrip("/")
    return f"{base}/api/projects/{configuration.project_slug}/{resource}"


def _wait_join(q: "queue.Queue[Any]", timeout: float) -> None:
    """queue.Queue has no join-with-timeout. Poll for emptiness."""
    import time

    deadline = time.monotonic() + timeout
    while q.unfinished_tasks > 0 and time.monotonic() < deadline:
        time.sleep(0.01)
