"""ASGI entrypoint for Helix Education. Replaces the single-threaded serve path.

Why this exists (audit P-1): `web_server_v2.main()` constructs a stdlib
`HTTPServer`, which accepts one connection at a time on one thread. Every
endpoint calls the LLM/grounding clients synchronously, so one slow model call
blocked every other request. The fix keeps the proven request logic in
`_Handler` as the single source of truth and changes only the serving model:

* an ASGI app hands each request to a bounded worker thread, so the event loop
  is never blocked and concurrent requests overlap;
* `uvicorn` with `HELIX_WEB_WORKERS` processes gives process-level parallelism,
  which is what actually scales past the GIL.

The handler stays synchronous on purpose. Rewriting 1,200 lines of request
logic to async would be a behaviour change with no measured benefit; moving it
off the loop is the measured bottleneck fix.

Run it:
    python -m helix_education.asgi_app
    # or
    uvicorn helix_education.asgi_app:create_app --factory --workers 4 --port 8080
"""

from __future__ import annotations

import asyncio
import io
import os
from typing import Any, Callable

from .web_server_v2 import _Handler, init_services


class _CaptureWriter:
    """Minimal write-only file object: collects what the handler writes."""

    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.chunks.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        return None

    def getvalue(self) -> bytes:
        return b"".join(self.chunks)


class _StubRequest:
    """The socket surface BaseHTTPRequestHandler actually uses.

    `wbufsize` defaults to 0, so the handler writes through `_SocketWriter`,
    which calls `sendall` — not `makefile("wb")`. Both are provided here so the
    adapter is correct for either buffering mode.
    """

    def __init__(self, raw: bytes, client: tuple[str, int]) -> None:
        self._raw = raw
        self._out = _CaptureWriter()
        self.client_address = client

    def sendall(self, data: bytes) -> None:
        self._out.write(data)

    def makefile(self, mode: str, *args: Any, **kwargs: Any) -> Any:
        if "r" in mode:
            return io.BytesIO(self._raw)
        return self._out

    def getvalue(self) -> bytes:
        return self._out.getvalue()


def _build_raw_request(scope: dict[str, Any], body: bytes) -> bytes:
    """Serialise an ASGI request into the HTTP/1.0 message the handler parses."""
    path = scope.get("raw_path") or scope.get("path", "/").encode("utf-8")
    query = scope.get("query_string") or b""
    target = path + (b"?" + query if query else b"")
    method = scope.get("method", "GET").encode("ascii")

    lines = [method + b" " + target + b" HTTP/1.0"]
    for name, value in scope.get("headers") or []:
        lines.append(bytes(name) + b": " + bytes(value))
    if body:
        lines.append(b"Content-Length: " + str(len(body)).encode("ascii"))
    lines.append(b"")
    lines.append(b"")
    return b"\r\n".join(lines) + body


def _parse_raw_response(raw: bytes) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    head, _, body = raw.partition(b"\r\n\r\n")
    head_lines = head.split(b"\r\n")
    status = 500
    if head_lines and head_lines[0].startswith(b"HTTP/"):
        parts = head_lines[0].split(b" ", 2)
        if len(parts) >= 2 and parts[1].isdigit():
            status = int(parts[1])
    headers: list[tuple[bytes, bytes]] = []
    for line in head_lines[1:]:
        name, sep, value = line.partition(b":")
        if sep:
            headers.append((name.strip().lower(), value.strip()))
    return status, headers, body


class _ASGIAdapter:
    """Serve a BaseHTTPRequestHandler class over ASGI, one thread per request."""

    def __init__(self, handler_cls: Callable[..., Any], client: tuple[str, int]) -> None:
        self._handler_cls = handler_cls
        self._client = client

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return

        body = b""
        while True:
            message = await receive()
            if message["type"] == "http.request":
                body += message.get("body", b"")
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                return

        raw = _build_raw_request(scope, body)

        def run() -> bytes:
            request = _StubRequest(raw, self._client)
            # BaseHTTPRequestHandler.__init__ already runs handle().
            self._handler_cls(request, self._client, None)
            return request.getvalue()

        # Blocking work (LLM, grounding, SQLite) runs off the event loop.
        raw_response = await asyncio.to_thread(run)
        status, headers, payload = _parse_raw_response(raw_response)

        if not any(name == b"content-length" for name, _ in headers):
            headers.append((b"content-length", str(len(payload)).encode("ascii")))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": payload})


def create_app(
    handler_cls: Callable[..., Any] | None = None,
    *,
    initialize: bool = True,
) -> _ASGIAdapter:
    """Build the ASGI app. `initialize=False` is the test seam."""
    if initialize:
        init_services()
    return _ASGIAdapter(handler_cls or _Handler, ("127.0.0.1", 0))


def main() -> None:
    import uvicorn

    host = os.environ.get("HELIX_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("HELIX_WEB_PORT", "8080"))
    workers = int(os.environ.get("HELIX_WEB_WORKERS", "1"))
    print(f"Helix Education ASGI: http://{host}:{port} (workers={workers})")
    uvicorn.run(
        "helix_education.asgi_app:create_app",
        factory=True,
        host=host,
        port=port,
        workers=workers,
        log_level=os.environ.get("HELIX_WEB_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
