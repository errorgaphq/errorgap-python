from __future__ import annotations

import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from errorgap.client import Client, DeliveryResult, RateLimited, retryable
from errorgap.configuration import Configuration
from errorgap.filter import filter_params
from errorgap.notice import build_notice
from errorgap.release import detect_release


@pytest.fixture
def stub():
    """An HTTP server answering each request with the next scripted
    (status, headers) pair; yields (endpoint, bodies, responses)."""
    bodies: list = []
    responses: list = [(201, {})]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("content-length", 0))
            bodies.append(json.loads(self.rfile.read(length) or b"null"))
            status, headers = responses.pop(0) if len(responses) > 1 else responses[0]
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("content-length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", bodies, responses
    server.shutdown()
    server.server_close()


def config(endpoint: str, **overrides) -> Configuration:
    return Configuration(endpoint=endpoint, project_slug="demo", release="v9", **overrides)


def test_queued_payloads_are_sent_and_flush_waits(stub):
    endpoint, bodies, _ = stub
    client = Client(config(endpoint))
    for n in range(5):
        client.notify(RuntimeError(f"e{n}"))
    client.flush(5)
    client.shutdown(2)
    assert [body["errors"][0]["message"] for body in bodies] == [f"e{n}" for n in range(5)]


def test_a_429_pauses_sending_for_retry_after(stub):
    endpoint, bodies, responses = stub
    responses[:] = [(429, {"Retry-After": "120"})]
    client = Client(config(endpoint, async_=False))
    assert client.notify(RuntimeError("one")).status == 429
    assert client.paused()
    assert isinstance(client.notify(RuntimeError("two")).error, RateLimited)
    assert len(bodies) == 1


def test_only_network_and_server_errors_are_retried():
    assert retryable(DeliveryResult(status=500, error=OSError()))
    assert retryable(DeliveryResult(error=ConnectionRefusedError()))
    assert not retryable(DeliveryResult(status=422, error=OSError()))
    assert not retryable(DeliveryResult(status=429, error=OSError()))
    assert not retryable(DeliveryResult(error=RateLimited()))
    assert not retryable(DeliveryResult(status=201))


def test_a_full_queue_drops_the_oldest_payload():
    client = Client(config("http://127.0.0.1:1", queue_size=2))
    client._ensure_worker = lambda: None  # hold the worker so nothing leaves
    for n in range(3):
        client._enqueue("notices", {"n": n})
    assert [client._queue.get_nowait()[1]["n"] for _ in range(2)] == [1, 2]


def test_filter_masks_keys_in_lists_and_survives_cycles_and_objects():
    loop: dict = {"name": "a"}
    loop["self"] = loop
    out = filter_params(
        {"users": [{"password": "p", "ssn": "1"}], "loop": loop, "obj": object(), "long": "x" * 10_000,
         "raw": b"\xff\xfe"},
        ("password", re.compile(r"^ssn$")),
    )
    assert out["users"][0] == {"password": "[FILTERED]", "ssn": "[FILTERED]"}
    assert out["loop"]["self"] == "[CIRCULAR]"
    assert out["long"].endswith("[TRUNCATED]")
    json.dumps(out)


def test_notices_carry_causes_release_and_a_filtered_session():
    try:
        try:
            raise KeyError("inner")
        except KeyError as inner:
            raise ValueError("outer") from inner
    except ValueError as error:
        notice = build_notice(error, config("http://x"), session={"auth_token": "t", "cart": 1})

    assert notice["context"]["causes"] == [{"type": "KeyError", "message": "'inner'"}]
    assert notice["context"]["release"] == "v9"
    assert notice["session"] == {"auth_token": "[FILTERED]", "cart": 1}
    frames = notice["errors"][0]["backtrace"]
    assert [frame["index"] for frame in frames] == list(range(len(frames)))
    assert len(frames) == 2


def test_before_notify_can_drop_or_change_and_a_raising_hook_is_skipped(stub):
    endpoint, bodies, _ = stub

    def tag(notice):
        notice["context"]["team"] = "billing"

    def broken(_notice):
        raise RuntimeError("bug in the hook")

    dropped = Client(config(endpoint, async_=False, before_notify=lambda n: False)).notify(RuntimeError("no"))
    assert dropped.body == "dropped by before_notify"
    Client(config(endpoint, async_=False, before_notify=tag)).notify(RuntimeError("yes"))
    Client(config(endpoint, async_=False, before_notify=broken)).notify(RuntimeError("still sent"))
    assert [body["errors"][0]["message"] for body in bodies] == ["yes", "still sent"]
    assert bodies[0]["context"]["team"] == "billing"


def test_nothing_is_sent_in_an_ignored_environment():
    client = Client(config("http://127.0.0.1:1", environment="test", ignore_environments=["test"]))
    assert client.notify(RuntimeError("x"), sync=True).body == "ignored environment"


def test_an_unserializable_payload_does_not_raise(stub):
    endpoint, bodies, _ = stub
    client = Client(config(endpoint, async_=False))
    result = client.notify(RuntimeError("x"), context={"when": object()})
    assert result.status == 201 and len(bodies) == 1


def test_release_is_read_from_the_platform_variable_then_the_git_checkout(tmp_path):
    assert detect_release(str(tmp_path), {}) is None
    heads = tmp_path / ".git" / "refs" / "heads"
    heads.mkdir(parents=True)
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (heads / "main").write_text("a" * 40 + "\n")
    assert detect_release(str(tmp_path), {}) == "a" * 40
    assert detect_release(str(tmp_path), {"SOURCE_VERSION": "env1"}) == "env1"
    assert os.path.isdir(tmp_path)
