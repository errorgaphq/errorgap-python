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
