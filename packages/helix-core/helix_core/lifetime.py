"""Keep the frozen worker tied to the lifetime of the process that started it.

A PyInstaller one-file bundle is two processes: a bootloader that unpacks
the archive, and a worker that runs the application. Killing the bootloader
does not kill the worker. The worker then survives its parent — still
holding the port, the database, and the token.

That matters for a desktop sidecar. The desktop app spawns the core, reads
the handshake, and on exit kills the process it started. If the worker
survives, the next launch of the app finds a previous core still serving
on its port, and the process outlives the app that owns it.

This module makes the worker notice that its parent is gone and exit.

Two mechanisms, because the platforms differ:

- POSIX: `prctl(PR_SET_PDEATHSIG, SIGTERM)`. The kernel sends the signal
  when the parent dies. There is a race — the parent can die between the
  fork and the call — so the parent pid is captured first and re-checked
  afterwards.
- Windows: a thread that waits on a handle to the parent process. When the
  parent terminates, the wait returns and the worker exits.

If neither mechanism can be installed, the watchdog does nothing: the core
still runs, it just may outlive its parent. That is the pre-existing
behaviour, so failing to install the watchdog never turns a working core
into a broken one.
"""

from __future__ import annotations

import os
import threading

__all__ = ["watch_parent_death", "parent_death_watchdog_installed"]

_installed = False


def parent_death_watchdog_installed() -> bool:
    """Whether the watchdog is armed in this process."""
    return _installed


def _install_posix_watchdog() -> bool:
    """Ask the kernel to signal this process when its parent dies."""
    try:
        import ctypes
        import signal

        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        pr_set_pdeathsig = 1

        # The parent may already be gone: capture its pid before arming the
        # watchdog, and check it again afterwards. Without this the race
        # would leave the worker running forever.
        parent_pid = os.getppid()

        if libc.prctl(pr_set_pdeathsig, signal.SIGTERM, 0, 0, 0) != 0:
            return False

        if os.getppid() != parent_pid:
            # The parent died between the fork and the call above.
            os._exit(0)

        return True
    except Exception:
        return False


def _install_windows_watchdog() -> bool:
    """Exit this process when the parent process terminates."""
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        synchronize = 0x00100000
        infinite = 0xFFFFFFFF
        parent_pid = os.getppid()
        if parent_pid <= 0:
            return False

        handle = kernel32.OpenProcess(synchronize, False, parent_pid)
        if not handle:
            return False

        def wait_for_parent() -> None:
            kernel32.WaitForSingleObject(handle, infinite)
            kernel32.CloseHandle(handle)
            # The parent is gone. Leave without running interpreter
            # teardown: the bundle's temporary directory is the parent's
            # to clean up, and a clean exit could run arbitrary atexit
            # handlers against a half-removed directory.
            os._exit(0)

        thread = threading.Thread(target=wait_for_parent, daemon=True)
        thread.start()
        return True
    except Exception:
        return False


def watch_parent_death() -> bool:
    """Arm the parent-death watchdog. Returns True when it was installed.

    Safe to call more than once; only the first call installs anything.
    """
    global _installed
    if _installed:
        return True

    installed = _install_windows_watchdog() if os.name == "nt" else _install_posix_watchdog()
    _installed = installed
    return installed
