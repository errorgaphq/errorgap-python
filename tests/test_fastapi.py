from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi import FastAPI
from starlette.testclient import TestClient

import errorgap
from errorgap.fastapi import ErrorgapMiddleware


def test_fastapi_middleware_reports_exception(ingestor, reset_errorgap):
    errorgap.init(
        endpoint=ingestor.endpoint,
        project_slug="demo",
        api_key="flk_test",
        async_=False,
        capture_globals=False,
    )

    app = FastAPI()
    app.add_middleware(ErrorgapMiddleware)

    @app.get("/boom")
    def boom():
        raise RuntimeError("fastapi-boom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom?x=1")
    assert response.status_code == 500

    errorgap.flush(timeout=5)
    assert len(ingestor.requests) == 1
    body = ingestor.requests[0].body
    assert body["errors"][0]["type"] == "RuntimeError"
    assert body["errors"][0]["message"] == "fastapi-boom"
    assert body["context"]["action"] == "GET"
