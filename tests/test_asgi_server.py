"""Serving-model tests for the ASGI entrypoint (audit P-1).

The claim under test is narrow and measurable: the server no longer serialises
requests on one thread, and existing request logic still works unchanged.
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from helix_education.asgi_app import create_app


class _SlowHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    delay = 0.2

    def do_GET(self):  # noqa: N802 - stdlib naming
        time.sleep(self.delay)
        body = ("ok:" + self.path).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("X-Echo-Path", self.path)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(201)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"got:" + str(len(body)).encode())


async def _call(app, path: str = "/health", method: str = "GET", body: bytes = b""):
    pending = [{"type": "http.request", "body": body, "more_body": False}]
    sent = []

    async def receive():
        return pending.pop(0)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
    }
    await app(scope, receive, send)

    start = next(message for message in sent if message["type"] == "http.response.start")
    payload = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return start, payload


def _app() -> object:
    return create_app(_SlowHandler, initialize=False)


def test_adapter_preserves_status_headers_and_body():
    start, payload = asyncio.run(_call(_app()))
    assert start["status"] == 200
    assert payload == b"ok:/health"
    headers = dict(start["headers"])
    assert headers[b"x-echo-path"] == b"/health"
    assert int(headers[b"content-length"]) == len(payload)


def test_adapter_passes_request_body():
    start, payload = asyncio.run(_call(_app(), path="/submit", method="POST", body=b"abcd" * 100))
    assert start["status"] == 201
    assert payload == b"got:400"


def test_requests_overlap_instead_of_serialising():
    """8 x 200ms. Serial the wall clock is 1.6s; concurrent it must stay well under."""
    app = _app()

    async def run_all():
        return await asyncio.gather(*[_call(app) for _ in range(8)])

    started = time.perf_counter()
    results = asyncio.run(run_all())
    elapsed = time.perf_counter() - started

    assert all(start["status"] == 200 for start, _ in results)
    assert elapsed < 0.8, f"8 concurrent 200ms requests took {elapsed:.2f}s — still serialising"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.integration
def test_uvicorn_serves_the_real_app(tmp_path: Path):
    """The real handler, served by uvicorn, answers /health. Proves the entrypoint."""
    root = Path(__file__).resolve().parents[1]
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "helix_education.asgi_app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(root)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}/health"
    try:
        payload = None
        for _ in range(100):
            if process.poll() is not None:
                output = process.stdout.read().decode(errors="replace") if process.stdout else ""
                pytest.fail(f"uvicorn exited early:\n{output}")
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    payload = json.loads(response.read().decode())
                break
            except Exception:
                time.sleep(0.1)
        assert payload == {"status": "ok"}, f"unexpected /health payload: {payload!r}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
