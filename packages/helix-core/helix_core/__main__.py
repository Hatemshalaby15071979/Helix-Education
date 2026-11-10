"""`python -m helix_core` entry point."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket

from .api import create_app
from .lifetime import watch_parent_death
from .service import LearningCore
from .store import default_db_path


def handshake_line(port: int, token: str) -> str:
    """The single line the desktop shell parses to find the service.

    Printed once, on stdout, before uvicorn starts logging. One JSON object
    per line so the parent can read lines and ignore anything that is not
    this shape.
    """
    return json.dumps({"event": "ready", "port": port, "token": token}, separators=(",", ":"))


def bind_socket(host: str, port: int) -> socket.socket:
    """Bind and listen ourselves so the real port is known before serving.

    With `port=0` the kernel picks a free port; the only way to learn it is
    to own the socket. uvicorn then serves on the socket we already hold.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(128)
    return sock


def main(argv: list[str] | None = None) -> int:
    """Start the core API server.

    Inputs:
        argv: Optional argument list (defaults to `sys.argv[1:]`).
    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(prog="helix-core", description="Helix Core learning service")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: loopback)")
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Bind port (default: 8765; 0 lets the kernel pick a free one)",
    )
    parser.add_argument("--db", default=default_db_path(), help="SQLite database path")
    parser.add_argument(
        "--token",
        default=os.environ.get("HELIX_CORE_TOKEN", ""),
        help="Bearer token required from clients (default: HELIX_CORE_TOKEN)",
    )
    parser.add_argument(
        "--handshake",
        action="store_true",
        help=(
            "Print one JSON line with the bound port and token, then serve. "
            "Used by the desktop shell, which spawns this process and needs "
            "both values before it can talk to it."
        ),
    )
    args = parser.parse_args(argv)

    import uvicorn

    # In handshake mode the parent is the only reader of stdout, so a token
    # that never touches disk or a config file is generated here. Without
    # handshake the previous behaviour is unchanged: no token means no auth.
    token = args.token
    if args.handshake and not token:
        token = secrets.token_urlsafe(32)

    core = LearningCore(args.db, token=token or None)
    app = create_app(core)

    if not args.handshake:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return 0

    # The frozen sidecar is a bootloader plus a worker. The worker must not
    # outlive the shell that spawned it, or it keeps the port, the database
    # and the token alive after the app that owns them has gone.
    watch_parent_death()

    sock = bind_socket(args.host, args.port)
    bound_port = sock.getsockname()[1]
    print(handshake_line(bound_port, token), flush=True)

    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=bound_port, log_level="info"))
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
