from __future__ import annotations

import threading

import pytest

import errorgap
from errorgap import browser_trace_id, current_transaction_id
from errorgap.wsgi import ROUTE_KEY, ErrorgapMiddleware

UUID = "0192f3c4-7a1b-4c2d-9e3f-0123456789ab"


@pytest.fixture
def apm(ingestor, reset_errorgap):
    errorgap.init(
        endpoint=ingestor.endpoint,
        project_slug="demo",
        async_=False,
        capture_globals=False,
        apm_enabled=True,
    )
    return ingestor


def _by_resource(ingestor, resource):
    return [r.body for r in ingestor.requests if r.path.endswith("/" + resource)]


def test_browser_trace_id_accepts_only_uuids():
    assert browser_trace_id(" 0192F3C4-7A1B-4C2D-9E3F-0123456789AB ") == UUID
    assert browser_trace_id(UUID.encode()) == UUID
    assert browser_trace_id("not-a-uuid") is None
    assert browser_trace_id(UUID + "0") is None
    assert browser_trace_id(None) is None


def test_track_job_links_errors_and_records_spans(apm):
    with errorgap.track_job("ReceiptJob", queue="mailers") as txn:
        txn.spans.database("SELECT * FROM receipts WHERE id = 7", 3.5)
        errorgap.notify(RuntimeError("smtp down"))
        seen = current_transaction_id()
    assert current_transaction_id() is None

    [job] = _by_resource(apm, "transactions")
    assert job["kind"] == "job"
    assert job["job_class"] == "ReceiptJob"
    assert job["queue"] == "mailers"
    assert job["id"] == seen
    assert job["spans"][0]["sql"] == "SELECT * FROM receipts WHERE id = ?"
    [notice] = _by_resource(apm, "notices")
    assert notice["context"]["transaction_id"] == seen


def test_track_transaction_records_failure_and_trace(apm):
    with pytest.raises(ValueError):
        with errorgap.track_transaction("GET", "/orders/{id}", "/orders/7", trace_id=UUID.upper()):
            raise ValueError("boom")
    [txn] = _by_resource(apm, "transactions")
    assert txn["status_code"] == 500
    assert txn["trace_id"] == UUID
    assert txn["id"] != txn["trace_id"]


def test_transactions_are_dropped_unless_apm_is_enabled(ingestor, reset_errorgap):
    errorgap.init(endpoint=ingestor.endpoint, project_slug="demo", async_=False, capture_globals=False)
    with errorgap.track_transaction("GET", "/", "/"):
        pass
    assert _by_resource(ingestor, "transactions") == []


def test_threads_never_share_a_transaction_id(apm):
    seen = {}

    def work(n):
        with errorgap.track_job("Job%d" % n):
            seen[n] = current_transaction_id()

    threads = [threading.Thread(target=work, args=(n,)) for n in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(seen.values())) == 3


def test_wsgi_middleware_records_the_request(apm):
    def app(environ, start_response):
        environ[ROUTE_KEY] = "/orders/<id>"
        errorgap.notify(RuntimeError("card declined"))
        start_response("201 Created", [("Content-Type", "text/plain")])
        return [b"ok"]

    wrapped = ErrorgapMiddleware(app)
    environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/orders/7", "HTTP_X_ERRORGAP_TRACE": UUID}
    body = wrapped(environ, lambda status, headers: None)
    assert b"".join(body) == b"ok"
    body.close()

    [txn] = _by_resource(apm, "transactions")
    assert txn["method"] == "POST"
    assert txn["path"] == "/orders/<id>"
    assert txn["path_raw"] == "/orders/7"
    assert txn["status_code"] == 201
    assert txn["trace_id"] == UUID
    [notice] = _by_resource(apm, "notices")
    assert notice["context"]["transaction_id"] == txn["id"]
    assert current_transaction_id() is None


def test_wsgi_middleware_records_a_raising_app(apm):
    def app(environ, start_response):
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError):
        ErrorgapMiddleware(app)({"REQUEST_METHOD": "GET", "PATH_INFO": "/x", "HTTP_X_ERRORGAP_TRACE": "nope"}, None)
    [txn] = _by_resource(apm, "transactions")
    assert txn["status_code"] == 500
    assert txn["path"] == "/x"
    assert "trace_id" not in txn
