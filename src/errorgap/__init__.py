from __future__ import annotations

from typing import Any, Dict, Optional

from .client import Client, DeliveryResult
from .configuration import Configuration
from .handlers import install_excepthook, uninstall_excepthook
from .version import VERSION

__all__ = [
    "init",
    "notify",
    "flush",
    "shutdown",
    "configuration",
    "client",
    "Configuration",
    "Client",
    "DeliveryResult",
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


def flush(timeout: Optional[float] = None) -> None:
    _client.flush(timeout)


def shutdown(timeout: Optional[float] = None) -> None:
    _client.shutdown(timeout)


def configuration() -> Configuration:
    return _configuration


def client() -> Client:
    return _client
