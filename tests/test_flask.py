from __future__ import annotations

import pytest

flask = pytest.importorskip("flask")

from flask import Flask

import errorgap
from errorgap.flask import init_app


def test_flask_signal_reports_exception(ingestor, reset_errorgap):
    errorgap.init(
        endpoint=ingestor.endpoint,
        project_slug="demo",
        api_key="flk_test",
        async_=False,
        capture_globals=False,
    )

    app = Flask(__name__)
    init_app(app)

    @app.route("/boom")
    def boom():
        raise RuntimeError("flask-boom")

    client = app.test_client()
    response = client.get("/boom?x=1")
    assert response.status_code == 500

    errorgap.flush(timeout=5)
    assert len(ingestor.requests) == 1
    body = ingestor.requests[0].body
    assert body["errors"][0]["type"] == "RuntimeError"
    assert body["errors"][0]["message"] == "flask-boom"
    assert body["context"]["action"] == "GET"


def test_flask_requests_are_transactions_linked_to_their_errors(ingestor, reset_errorgap):
    from errorgap.flask import spans

    errorgap.init(
        endpoint=ingestor.endpoint,
        project_slug="demo",
        async_=False,
        capture_globals=False,
        apm_enabled=True,
    )

    app = Flask(__name__)
    init_app(app)

    @app.route("/orders/<int:order_id>")
    def order(order_id):
        spans().database("SELECT * FROM orders WHERE id = %d" % order_id, 1.5)
        raise RuntimeError("flask-boom")

    response = app.test_client().get(
        "/orders/7", headers={"x-errorgap-trace": "0192F3C4-7A1B-4C2D-9E3F-0123456789AB"}
    )
    assert response.status_code == 500
    response.close()  # WSGI servers close the response; the transaction is recorded then

    errorgap.flush(timeout=5)
    [txn] = [r.body for r in ingestor.requests if r.path.endswith("/transactions")]
    [notice] = [r.body for r in ingestor.requests if r.path.endswith("/notices")]
    assert txn["path"] == "/orders/<int:order_id>"
    assert txn["path_raw"] == "/orders/7"
    assert txn["status_code"] == 500
    assert txn["trace_id"] == "0192f3c4-7a1b-4c2d-9e3f-0123456789ab"
    assert txn["spans"][0]["sql"] == "SELECT * FROM orders WHERE id = ?"
    assert notice["context"]["transaction_id"] == txn["id"]
