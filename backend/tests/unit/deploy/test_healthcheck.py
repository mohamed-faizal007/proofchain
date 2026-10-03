"""`python -m app.scripts.healthcheck`: exit 0 only when /health says status == "ok"."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.scripts.healthcheck import is_healthy, main


def _serve(code: int, body: bytes) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(code)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/health"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def ok_url() -> Iterator[str]:
    yield from _serve(200, json.dumps({"status": "ok"}).encode())


@pytest.fixture
def degraded_url() -> Iterator[str]:
    # /health answers 200 even when degraded (04_API_SPEC); the body is what matters.
    yield from _serve(200, json.dumps({"status": "degraded", "mongo": "down"}).encode())


@pytest.fixture
def garbage_url() -> Iterator[str]:
    yield from _serve(200, b"<html>not json</html>")


@pytest.fixture
def error_url() -> Iterator[str]:
    yield from _serve(500, json.dumps({"status": "ok"}).encode())


def test_ok_body_is_healthy(ok_url: str) -> None:
    assert is_healthy(ok_url) is True


def test_degraded_body_is_unhealthy_despite_http_200(degraded_url: str) -> None:
    assert is_healthy(degraded_url) is False


def test_non_json_body_is_unhealthy(garbage_url: str) -> None:
    assert is_healthy(garbage_url) is False


def test_http_error_is_unhealthy(error_url: str) -> None:
    assert is_healthy(error_url) is False


def test_connection_refused_is_unhealthy() -> None:
    assert is_healthy("http://127.0.0.1:1/health", timeout=1.0) is False


def test_main_exit_codes(ok_url: str, degraded_url: str) -> None:
    assert main([ok_url]) == 0
    assert main([degraded_url]) == 1
