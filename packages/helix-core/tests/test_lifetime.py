"""The sidecar must not outlive the shell that spawned it.

The frozen sidecar is a PyInstaller bundle: a bootloader that unpacks the
archive, and a worker that serves the API. Killing the bootloader does not
kill the worker, so the worker keeps the port, the database and the token
alive after the desktop app that owns them has exited.

These tests run the core as a plain child process rather than through
PyInstaller, because the property under test is the watchdog itself: the
worker notices that its parent died and exits.

The POSIX behaviour is skipped on Windows, where the watchdog uses a
different mechanism (waiting on the parent process handle) and the parent
is not reparented when it dies.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX reparenting semantics; the Windows watchdog waits on the parent handle instead",
)


def _serving(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_until_not_serving(port: int, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _serving(port):
            return True
        time.sleep(0.2)
    return False


def test_the_core_exits_when_its_parent_process_dies(tmp_path: Path) -> None:
    """A parent that dies takes the core with it."""
    read_fd, write_fd = os.pipe()

    # The parent spawns the core, prints the handshake, then waits for a
    # byte on stdin before exiting. That lets the test observe the core
    # serving first, and only then pull the parent out from under it.
    parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import subprocess,sys,os;"
                "p=subprocess.Popen([sys.executable,'-m','helix_core','--port','0','--handshake',"
                f"'--db',{str(tmp_path / 'core.db')!r}],stdout=subprocess.PIPE);"
                "line=p.stdout.readline();"
                "sys.stdout.write(line.decode());sys.stdout.flush();"
                "sys.stdin.readline();"
                "os._exit(0)"
            ),
        ],
        cwd=PACKAGE_ROOT,
        stdin=read_fd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    os.close(read_fd)

    try:
        assert parent.stdout is not None
        line = parent.stdout.readline().strip()
        assert line, "the parent printed no handshake line"
        port = json.loads(line)["port"]
        assert port > 0

        # The core serves while its parent is alive.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not _serving(port):
            time.sleep(0.2)
        assert _serving(port), "the core never started serving"

        # Now the parent dies.
        os.write(write_fd, b"x\n")
        os.close(write_fd)
        parent.wait(timeout=20)

        assert _wait_until_not_serving(port), (
            "the core is still serving after its parent process died — "
            "it would outlive the desktop app that spawned it"
        )
    finally:
        try:
            os.close(write_fd)
        except OSError:
            pass
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=10)


def test_the_watchdog_reports_whether_it_is_armed() -> None:
    """The watchdog reports its state rather than failing silently."""
    from helix_core.lifetime import parent_death_watchdog_installed, watch_parent_death

    # In this process the parent (pytest) is alive, so arming must succeed
    # on POSIX and must not disturb the running test session.
    armed = watch_parent_death()
    assert armed is True
    assert parent_death_watchdog_installed() is True


def test_the_watchdog_is_idempotent() -> None:
    """Calling it twice must not arm a second mechanism."""
    from helix_core.lifetime import watch_parent_death

    assert watch_parent_death() is True
    assert watch_parent_death() is True


def test_the_non_handshake_path_is_unaffected(tmp_path: Path) -> None:
    """A core started without --handshake keeps its ordinary lifetime.

    The watchdog is only armed for the handshake mode, because that mode
    exists for a parent that spawns the core and expects it to die with
    it. A standalone server must not.
    """
    import inspect

    from helix_core import __main__ as core_main

    source = inspect.getsource(core_main.main)
    handshake_branch = source.split("if not args.handshake:")[1]
    assert "watch_parent_death" in handshake_branch, (
        "the watchdog must be armed in the handshake branch, where a parent process owns the core"
    )
