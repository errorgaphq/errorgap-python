from __future__ import annotations

import asyncio
import logging

import pytest

import errorgap


def _init(ingestor, **overrides):
    errorgap.init(
        endpoint=ingestor.endpoint,
        project_slug="demo",
        async_=False,
        capture_globals=False,
        release="v1",
        **overrides,
    )


def _notices(ingestor):
    return [r.body for r in ingestor.requests if r.path.endswith("/notices")]


def _transactions(ingestor):
    return [r.body for r in ingestor.requests if r.path.endswith("/transactions")]


def test_celery_reports_a_failed_task_and_times_tasks(ingestor, reset_errorgap):
    celery = pytest.importorskip("celery")
    from errorgap.celery import install

    _init(ingestor, apm_enabled=True)
    assert install() is True

    app = celery.Celery("demo")
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = False

    @app.task(name="orders.charge")
    def charge(order_id, token=None):
        raise ValueError(f"card declined for {order_id}")

    @app.task(name="orders.ok")
    def ok():
        return 1

    charge.delay(7, token="secret-token")
    ok.delay()

    [notice] = _notices(ingestor)
    assert notice["errors"][0]["type"] == "ValueError"
    assert notice["context"]["component"] == "celery"
    assert notice["context"]["action"] == "orders.charge"
    assert notice["params"] == {"args": [7], "kwargs": {"token": "[FILTERED]"}}
    assert notice["errors"][0]["backtrace"], "the task's traceback is reported"

    jobs = _transactions(ingestor)
    assert [(job["kind"], job["job_class"]) for job in jobs] == [("job", "orders.charge"), ("job", "orders.ok")]
    # The failure is linked to the task's transaction.
    assert notice["context"]["transaction_id"] == jobs[0]["id"]


def test_logging_handler_reports_exceptions_and_plain_errors(ingestor, reset_errorgap):
    from errorgap.log_handler import ErrorgapHandler

    _init(ingestor)
    logger = logging.getLogger("billing.invoices")
    logger.propagate = False
    handler = ErrorgapHandler()
    logger.addHandler(handler)
    try:
        logger.warning("below the level: not reported")
        try:
            raise KeyError("missing customer")
        except KeyError:
            logger.exception("could not build invoice %s", 42)
        logger.error("invoice %s is overdue", 42)
        logging.getLogger("errorgap").error("the SDK's own log: never reported")
    finally:
        logger.removeHandler(handler)

    first, second = _notices(ingestor)
    assert first["errors"][0]["type"] == "KeyError"
    assert first["context"]["log_message"] == "could not build invoice 42"
    assert first["context"]["component"] == "billing.invoices"
    assert second["errors"][0]["type"] == "LoggedError"
    assert second["errors"][0]["message"] == "invoice 42 is overdue"
    assert second["context"]["severity"] == "error"


def test_aiohttp_middleware_reports_errors_and_times_requests(ingestor, reset_errorgap):
    pytest.importorskip("aiohttp")
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from errorgap.aiohttp import errorgap_middleware

    _init(ingestor, apm_enabled=True)

    async def boom(request):
        raise RuntimeError("aiohttp-boom")

    async def order(request):
        return web.json_response({"id": request.match_info["id"]})

    async def run():
        app = web.Application(middlewares=[errorgap_middleware])
        app.router.add_get("/boom", boom)
        app.router.add_get("/orders/{id}", order)
        async with TestClient(TestServer(app)) as client:
            assert (await client.get("/boom")).status == 500
            assert (await client.get("/orders/7")).status == 200
            assert (await client.get("/nope")).status == 404

    asyncio.run(run())

    [notice] = _notices(ingestor)
    assert notice["errors"][0]["message"] == "aiohttp-boom"
    by_path = {txn["path"]: txn for txn in _transactions(ingestor)}
    assert by_path["/orders/{id}"]["status_code"] == 200
    assert by_path["/boom"]["status_code"] == 500
    assert by_path["/nope"]["status_code"] == 404
    assert notice["context"]["transaction_id"] == by_path["/boom"]["id"]


def test_the_asgi_middleware_is_importable_under_a_framework_neutral_name():
    pytest.importorskip("starlette")
    from errorgap.asgi import ErrorgapMiddleware
    from errorgap.fastapi import ErrorgapMiddleware as FastApiMiddleware

    assert ErrorgapMiddleware is FastApiMiddleware
