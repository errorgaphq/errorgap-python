from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

import pytest


@dataclass
class CapturedRequest:
    path: str
    method: str
    headers: Dict[str, str]
    body: Any


@dataclass
class FakeIngestor:
    server: ThreadingHTTPServer
    thread: threading.Thread
    port: int
    requests: List[CapturedRequest] = field(default_factory=list)
    status: int = 201
    response_body: str = '{"group_id":"g_1"}'

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()


def _make_handler(state: FakeIngestor):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("content-length", "0") or "0")
            raw = self.rfile.read(length) if length else b""
            try:
                body: Any = json.loads(raw.decode("utf-8"))
            except Exception:
                body = raw.decode("utf-8", errors="replace")
            state.requests.append(
                CapturedRequest(
                    path=self.path,
                    method=self.command,
                    headers={k.lower(): v for k, v in self.headers.items()},
                    body=body,
                )
            )
            self.send_response(state.status)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(state.response_body.encode("utf-8"))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return  # silence noisy default logging

    return Handler


@pytest.fixture
def ingestor() -> FakeIngestor:
    server = ThreadingHTTPServer(("127.0.0.1", 0), object)
    port = server.server_address[1]
    state = FakeIngestor(server=server, thread=None, port=port)  # type: ignore[arg-type]
    server.RequestHandlerClass = _make_handler(state)
    thread = threading.Thread(target=server.serve_forever, name="errorgap-fake-ingestor", daemon=True)
    state.thread = thread
    thread.start()
    yield state
    state.stop()


@pytest.fixture
def reset_errorgap():
    """Reset the module-level errorgap singleton between tests."""
    import errorgap
    from errorgap.configuration import Configuration

    original_config = errorgap._configuration
    original_client = errorgap._client
    yield
    errorgap._configuration = original_config
    errorgap._client = original_client
    errorgap._client.configure(original_config)
