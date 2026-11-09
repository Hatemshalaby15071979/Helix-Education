"""`python -m helix_core` entry point."""

from __future__ import annotations

import argparse
import os

from .api import create_app
from .service import LearningCore
from .store import default_db_path


def main(argv: list[str] | None = None) -> int:
    """Start the core API server.

    Inputs:
        argv: Optional argument list (defaults to `sys.argv[1:]`).
    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(prog="helix-core", description="Helix Core learning service")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: loopback)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument("--db", default=default_db_path(), help="SQLite database path")
    parser.add_argument(
        "--token",
        default=os.environ.get("HELIX_CORE_TOKEN", ""),
        help="Bearer token required from clients (default: HELIX_CORE_TOKEN)",
    )
    args = parser.parse_args(argv)

    import uvicorn

    core = LearningCore(args.db, token=args.token or None)
    app = create_app(core)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
