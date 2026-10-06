from __future__ import annotations

import contextlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

from .apm import TRACE_HEADER, Span, SpanCollector, Transaction, browser_trace_id, normalize_sql
from .client import Client, DeliveryResult
from .configuration import Configuration
from .handlers import install_excepthook, uninstall_excepthook
from .transaction_context import current_transaction_id, new_transaction_id, transaction_scope
from .version import VERSION

__all__ = [
    "init",
    "notify",
    "notify_transaction",
    "track_transaction",
    "track_job",
    "sign_in",
    "current_transaction_id",
    "transaction_scope",
    "browser_trace_id",
    "flush",
    "shutdown",
    "configuration",
    "client",
    "Configuration",
    "Client",
    "DeliveryResult",
    "Span",
    "SpanCollector",
    "Transaction",
    "TRACE_HEADER",
    "normalize_sql",
    "VERSION",
]

_configuration = Configuration()
_client = Client(_configuration)


def init(
    *,
    endpoint: Optional[str] = None,
    project_slug: Optional[str] = None,
    project_id: Optional[str] = None,
    api_key: Optional[str] = None,
    environment: Optional[str] = None,
    root_directory: Optional[str] = None,
    async_: Optional[bool] = None,
    filter_keys: Optional[tuple] = None,
    logger: Optional[Any] = None,
    apm_enabled: Optional[bool] = None,
    apm_sample_rate: Optional[float] = None,
    auth_events: Optional[bool] = None,
    app_name: Optional[str] = None,
    capture_globals: bool = True,
) -> None:
    """Configure the SDK and install global error hooks.

    Reads ``ERRORGAP_ENDPOINT``, ``ERRORGAP_PROJECT_SLUG``,
    ``ERRORGAP_PROJECT_ID``, and ``ERRORGAP_API_KEY`` from the environment when
    the matching keyword argument is omitted.
    """
    global _configuration, _client

    overrides: Dict[str, Any] = {}
    if endpoint is not None:
        overrides["endpoint"] = endpoint
    if project_slug is not None:
        overrides["project_slug"] = project_slug
    if project_id is not None:
        overrides["project_id"] = project_id
    if api_key is not None:
        overrides["api_key"] = api_key
    if environment is not None:
        overrides["environment"] = environment
    if root_directory is not None:
        overrides["root_directory"] = root_directory
    if async_ is not None:
        overrides["async_"] = async_
    if filter_keys is not None:
        overrides["filter_keys"] = filter_keys
    if logger is not None:
        overrides["logger"] = logger
    if apm_enabled is not None:
        overrides["apm_enabled"] = apm_enabled
    if apm_sample_rate is not None:
        overrides["apm_sample_rate"] = apm_sample_rate
    if auth_events is not None:
        overrides["auth_events"] = auth_events
    if app_name is not None:
        overrides["app_name"] = app_name

    _configuration = Configuration(**overrides)
    _client.configure(_configuration)

    if capture_globals:
        install_excepthook(_client)
    else:
        uninstall_excepthook()


def notify(
    exc: BaseException,
    context: Optional[Dict[str, Any]] = None,
    environment: Optional[Dict[str, Any]] = None,
    session: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    sync: bool = False,
) -> DeliveryResult:
    return _client.notify(
        exc,
        context=context,
        environment=environment,
        session=session,
        params=params,
        sync=sync,
    )


def sign_in(
    outcome: str,
    user: Any = None,
    request: Any = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
    sync: bool = False,
) -> DeliveryResult:
    """Report a sign-in to this app: ``"success"``, ``"failure"``,
    ``"password_reset"``, ``"mfa_failure"`` or ``"locked"``. Pass the
    Django, Flask or Starlette ``request`` for its IP, user agent and path.
    Needs ``init(auth_events=True)``; Django's login signals report
    automatically with the middleware installed."""
    return _client.sign_in(
        outcome, sync=sync, user=user, request=request, ip=ip,
        user_agent=user_agent, path=path, method=method,
    )


def notify_transaction(transaction: Transaction, sync: bool = False) -> DeliveryResult:
    """Deliver a pre-measured APM transaction."""
    return _client.notify_transaction(transaction, sync=sync)


@contextlib.contextmanager
def track_transaction(
    method: Optional[str] = None,
    path: Optional[str] = None,
    path_raw: Optional[str] = None,
    trace_id: Optional[str] = None,
    kind: str = "web",
) -> Iterator[Transaction]:
    """Time the ``with`` block as an APM transaction and deliver it on exit,
    even if the block raises. Errors reported inside it carry the
    transaction's id. Yields the :class:`Transaction`: record spans on
    ``txn.spans`` and set ``txn.status_code``. ``trace_id`` takes the raw
    ``x-errorgap-trace`` header value and ignores anything but a UUID."""
    txn = Transaction(
        kind=kind,
        id=new_transaction_id(),
        trace_id=browser_trace_id(trace_id),
        method=method,
        path=path,
        path_raw=path_raw,
    )
    with _timed(txn):
        yield txn


@contextlib.contextmanager
def track_job(job_class: str, queue: str = "default") -> Iterator[Transaction]:
    """Time the ``with`` block as a ``job`` transaction; see
    :func:`track_transaction`."""
    txn = Transaction(kind="job", id=new_transaction_id(), job_class=job_class, queue=queue)
    with _timed(txn):
        yield txn


@contextlib.contextmanager
def _timed(txn: Transaction) -> Iterator[None]:
    txn.occurred_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    start = time.perf_counter()
    try:
        with transaction_scope(txn.id or new_transaction_id()):
            yield
    except BaseException:
        if txn.kind == "web" and txn.status_code is None:
            txn.status_code = 500
        raise
    finally:
        txn.duration_ms = (time.perf_counter() - start) * 1000.0
        _client.notify_transaction(txn)


def flush(timeout: Optional[float] = None) -> None:
    _client.flush(timeout)


def shutdown(timeout: Optional[float] = None) -> None:
    _client.shutdown(timeout)


def configuration() -> Configuration:
    return _configuration


def client() -> Client:
    return _client
