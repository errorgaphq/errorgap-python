from __future__ import annotations

import pytest

django = pytest.importorskip("django")

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import path

import errorgap
from errorgap.django import ErrorgapMiddleware


@pytest.fixture(scope="module", autouse=True)
def _django_setup():
    if not settings.configured:
        settings.configure(
            DEBUG=False,
            ALLOWED_HOSTS=["*"],
            ROOT_URLCONF=__name__,
            DATABASES={},
            INSTALLED_APPS=[],
            MIDDLEWARE=[],
            SECRET_KEY="test",
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        )
        import django as _django

        _django.setup()


def _boom(_request):
    raise RuntimeError("django-boom")


urlpatterns = [path("boom", _boom)]


def test_middleware_reports_exception(ingestor, reset_errorgap):
    errorgap.init(
        endpoint=ingestor.endpoint,
        project_slug="demo",
        api_key="flk_test",
        async_=False,
        capture_globals=False,
    )

    factory = RequestFactory()
    request = factory.get("/boom?x=1")

    middleware = ErrorgapMiddleware(get_response=lambda req: HttpResponse(""))

    try:
        _boom(request)
    except RuntimeError as exc:
        middleware.process_exception(request, exc)

    errorgap.flush(timeout=5)
    assert len(ingestor.requests) == 1
    body = ingestor.requests[0].body
    assert body["errors"][0]["type"] == "RuntimeError"
    assert body["errors"][0]["message"] == "django-boom"
    assert body["context"]["action"] == "GET"


def _order(request, order_id):
    from errorgap.django import spans

    spans(request).database("SELECT * FROM orders WHERE id = %d" % order_id, 1.0)
    errorgap.notify(RuntimeError("card declined"))
    return HttpResponse("ok", status=201)


urlpatterns.append(path("orders/<int:order_id>", _order))


def test_requests_are_transactions_linked_to_their_errors(ingestor, reset_errorgap):
    from django.test import Client

    errorgap.init(
        endpoint=ingestor.endpoint,
        project_slug="demo",
        async_=False,
        capture_globals=False,
        apm_enabled=True,
    )
    settings.MIDDLEWARE = ["errorgap.django.ErrorgapMiddleware"]
    try:
        client = Client(raise_request_exception=False)
        ok = client.get("/orders/7", HTTP_X_ERRORGAP_TRACE="0192F3C4-7A1B-4C2D-9E3F-0123456789AB")
        boom = client.get("/boom")
    finally:
        settings.MIDDLEWARE = []
    assert ok.status_code == 201
    assert boom.status_code == 500

    txns = [r.body for r in ingestor.requests if r.path.endswith("/transactions")]
    notices = [r.body for r in ingestor.requests if r.path.endswith("/notices")]
    ok_txn = next(t for t in txns if t["path_raw"] == "/orders/7")
    boom_txn = next(t for t in txns if t["path_raw"] == "/boom")
    assert ok_txn["path"] == "/orders/<int:order_id>"
    assert ok_txn["status_code"] == 201
    assert ok_txn["trace_id"] == "0192f3c4-7a1b-4c2d-9e3f-0123456789ab"
    assert ok_txn["spans"][0]["sql"] == "SELECT * FROM orders WHERE id = ?"
    assert boom_txn["status_code"] == 500
    assert "trace_id" not in boom_txn
    by_message = {n["errors"][0]["message"]: n["context"].get("transaction_id") for n in notices}
    assert by_message["card declined"] == ok_txn["id"]
    assert by_message["django-boom"] == boom_txn["id"]


def test_login_signals_report_sign_ins(ingestor, reset_errorgap):
    from django.contrib.auth.signals import user_logged_in, user_login_failed

    errorgap.init(endpoint=ingestor.endpoint, project_slug="demo", api_key="k", async_=False,
                  capture_globals=False, auth_events=True)
    ErrorgapMiddleware(get_response=lambda req: HttpResponse(""))  # connects the signals
    request = RequestFactory().post("/accounts/login/", REMOTE_ADDR="198.51.100.71",
                                    HTTP_USER_AGENT="Firefox/131")

    class User:
        def get_username(self):
            return "mara"

    user_logged_in.send(sender=User, request=request, user=User())
    # Django masks the password before sending the signal.
    user_login_failed.send(sender=None, request=request,
                           credentials={"username": "admin", "password": "********************"})
    # A failed check outside a request is not a sign-in attempt.
    user_login_failed.send(sender=None, request=None, credentials={"username": "cli"})

    events = [r.body["events"][0] for r in ingestor.requests]
    assert [(e["outcome"], e["user"]) for e in events] == [("success", "mara"), ("failure", "admin")]
    assert events[0]["path"] == "POST /accounts/login/"
    assert events[0]["ip"] == "198.51.100.71"
