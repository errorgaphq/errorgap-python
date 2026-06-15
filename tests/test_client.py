from __future__ import annotations

from errorgap.client import Client
from errorgap.configuration import Configuration


def _raise(message: str = "boom") -> Exception:
    try:
        raise TypeError(message)
    except Exception as exc:
        return exc


def test_posts_to_notices_with_canonical_headers(ingestor):
    config = Configuration(
        endpoint=ingestor.endpoint,
        project_slug="demo",
        api_key="flk_test",
        async_=False,
    )
    client = Client(config)

    result = client.notify(_raise(), sync=True)
    assert result.status == 201

    assert len(ingestor.requests) == 1
    req = ingestor.requests[0]
    assert req.method == "POST"
    assert req.path == "/api/projects/demo/notices"
    assert req.headers["content-type"] == "application/json"
    assert req.headers["x-errorgap-project-key"] == "flk_test"
    assert req.headers["user-agent"].startswith("errorgap-python/")


def test_sends_full_notice_envelope(ingestor):
    config = Configuration(
        endpoint=ingestor.endpoint,
        project_slug="demo",
        api_key="flk_test",
        async_=False,
    )
    client = Client(config)
    client.notify(_raise("kaboom"), sync=True)

    body = ingestor.requests[0].body
    assert "errors" in body
    assert "context" in body
    assert body["errors"][0]["type"] == "TypeError"
    assert body["errors"][0]["message"] == "kaboom"
    assert body["context"]["notifier"] == "errorgap-python"


def test_returns_error_result_when_project_slug_missing(ingestor):
    config = Configuration(endpoint=ingestor.endpoint, api_key="flk_test", logger=None)
    client = Client(config)

    result = client.notify(_raise(), sync=True)
    assert result.error is not None
    assert len(ingestor.requests) == 0


def test_async_mode_queues_and_flushes(ingestor):
    config = Configuration(
        endpoint=ingestor.endpoint,
        project_slug="demo",
        api_key="flk_test",
        async_=True,
    )
    client = Client(config)
    try:
        result = client.notify(_raise())
        assert result.queued is True
        assert result.status == 202

        client.flush(timeout=5)
        assert len(ingestor.requests) == 1
    finally:
        client.shutdown(timeout=2)
