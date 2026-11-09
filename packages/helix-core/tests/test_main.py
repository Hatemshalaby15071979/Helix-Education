"""The `--handshake` contract the desktop shell depends on."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from helix_core.__main__ import bind_socket, handshake_line

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_handshake_line_is_one_json_object() -> None:
    line = handshake_line(43210, "abc123")

    assert "\n" not in line
    payload = json.loads(line)
    assert payload == {"event": "ready", "port": 43210, "token": "abc123"}


def test_bind_socket_reports_the_port_the_kernel_chose() -> None:
    sock = bind_socket("127.0.0.1", 0)
    try:
        port = sock.getsockname()[1]
        assert port > 0
        # A listening socket accepts a connection on the port it reported.
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            pass
    finally:
        sock.close()


def _read_line(proc: subprocess.Popen[str], timeout: float = 20.0) -> str | None:
    """Read one line without blocking forever on a stuck child."""
    box: dict[str, str] = {}

    def reader() -> None:
        box["line"] = proc.stdout.readline() if proc.stdout else ""

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    thread.join(timeout)
    return box.get("line")


def _get(url: str, token: str | None = None) -> int:
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_handshake_process_serves_the_port_and_token_it_printed(tmp_path: Path) -> None:
    """End to end: spawn, read the line, use the token it gave us."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "helix_core",
            "--port",
            "0",
            "--handshake",
            "--db",
            str(tmp_path / "core.db"),
        ],
        cwd=PACKAGE_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        line = _read_line(proc)
        assert line, "the process printed no handshake line"
        payload = json.loads(line)
        assert payload["event"] == "ready"
        assert payload["port"] > 0
        assert len(payload["token"]) >= 20

        base = f"http://127.0.0.1:{payload['port']}"
        # The socket is already listening, but uvicorn may need a moment
        # before it answers the first request.
        status = None
        for _ in range(40):
            try:
                status = _get(f"{base}/v1/health")
                break
            except (urllib.error.URLError, ConnectionError):
                threading.Event().wait(0.1)
        assert status == 200

        # The generated token is real: it is required on everything but health.
        assert _get(f"{base}/v1/quizzes/does-not-exist/score") == 401
        assert _get(f"{base}/v1/quizzes/does-not-exist/score", payload["token"]) == 404
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            proc.kill()
            proc.wait(timeout=5)


def test_port_zero_without_handshake_is_still_an_ordinary_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    """The non-handshake path is untouched: no token, no printed line."""
    calls: dict[str, object] = {}

    import uvicorn

    def fake_run(app, **kwargs):
        calls["host"] = kwargs.get("host")
        calls["port"] = kwargs.get("port")

    monkeypatch.setattr(uvicorn, "run", fake_run)

    from helix_core.__main__ import main

    assert main(["--port", "0", "--db", ":memory:"]) == 0
    assert calls == {"host": "127.0.0.1", "port": 0}
