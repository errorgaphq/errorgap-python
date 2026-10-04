from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi import FastAPI, Request
from starlette.testclient import TestClient

import errorgap
from errorgap.fastapi import ErrorgapMiddleware, spans


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


def test_fastapi_requests_are_transactions_linked_to_their_errors(ingestor, reset_errorgap):
    errorgap.init(
        endpoint=ingestor.endpoint,
        project_slug="demo",
        async_=False,
        capture_globals=False,
        apm_enabled=True,
    )

    app = FastAPI()
    app.add_middleware(ErrorgapMiddleware)

    @app.get("/orders/{order_id}", status_code=201)
    async def order(order_id: int, request: Request):
        spans(request).database("SELECT * FROM orders WHERE id = %d" % order_id, 1.0)
        errorgap.notify(RuntimeError("card declined"))
        return {"id": order_id}

    @app.get("/sync/{n}")
    def sync_boom(n: int):
        raise RuntimeError("fastapi-boom")

    client = TestClient(app, raise_server_exceptions=False)
    ok = client.get("/orders/7", headers={"x-errorgap-trace": "0192F3C4-7A1B-4C2D-9E3F-0123456789AB"})
    boom = client.get("/sync/1")
    assert ok.status_code == 201
    assert boom.status_code == 500

    txns = [r.body for r in ingestor.requests if r.path.endswith("/transactions")]
    notices = [r.body for r in ingestor.requests if r.path.endswith("/notices")]
    ok_txn = next(t for t in txns if t["path_raw"] == "/orders/7")
    boom_txn = next(t for t in txns if t["path_raw"] == "/sync/1")
    assert ok_txn["path"] == "/orders/{order_id}"
    assert ok_txn["status_code"] == 201
    assert ok_txn["trace_id"] == "0192f3c4-7a1b-4c2d-9e3f-0123456789ab"
    assert ok_txn["spans"][0]["sql"] == "SELECT * FROM orders WHERE id = ?"
    assert boom_txn["path"] == "/sync/{n}"
    assert boom_txn["status_code"] == 500
    by_message = {n["errors"][0]["message"]: n["context"].get("transaction_id") for n in notices}
    assert by_message["card declined"] == ok_txn["id"]
    assert by_message["fastapi-boom"] == boom_txn["id"]
