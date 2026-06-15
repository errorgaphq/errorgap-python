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
