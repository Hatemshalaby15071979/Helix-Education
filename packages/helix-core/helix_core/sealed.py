"""Sealed answer-key storage.

An answer key is written once, in a table the HTTP layer never reads
directly, and every read is verified against an HMAC. A key that has
been edited on disk fails verification and the core refuses to score
instead of silently grading against the wrong answer.

Threat model, stated exactly: this is integrity, not secrecy against
someone with write access to the database. The HMAC secret lives in a
separate 0600 file (or `HELIX_CORE_SECRET`), so casual edits are caught;
a determined local attacker who can read both files can still forge a
key. That is the same boundary the Helix Education README already
documents for its JSONL store.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from .models import QuizItem
from .store import SqliteEventStore, utc_now


class TamperError(RuntimeError):
    """Raised when a sealed key fails HMAC verification."""


def default_secret_path() -> str:
    """Resolve the default HMAC secret file path."""
    override = os.environ.get("HELIX_CORE_SECRET_FILE", "").strip()
    if override:
        return override
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "helix-core", "secret.key")


def load_secret(path: str | None = None) -> bytes:
    """Load the HMAC secret, creating a 0600 file on first use.

    Precedence: `HELIX_CORE_SECRET` environment variable, then the
    secret file at `path` (or the default location).
    """
    env = os.environ.get("HELIX_CORE_SECRET", "").strip()
    if env:
        return env.encode("utf-8")

    secret_path = Path(path or default_secret_path())
    if secret_path.exists():
        return secret_path.read_bytes()

    secret_path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_bytes(32)
    secret_path.write_bytes(value)
    try:
        secret_path.chmod(0o600)
    except OSError:
        # Windows does not implement POSIX modes; the file still lives in
        # the per-user data directory.
        pass
    return value


class SealedKeyStore:
    """Write-once answer keys with HMAC verification.

    Inputs:
        store: The event store that owns the database connection.
        secret: HMAC key bytes.
    """

    def __init__(self, store: SqliteEventStore, secret: bytes) -> None:
        if not secret:
            raise ValueError("secret must not be empty")
        self._store = store
        self._secret = secret

    def seal(self, quiz_id: str, item_id: str, item: QuizItem) -> None:
        """Store an answer key and its HMAC. Overwrites are rejected."""
        mac = self._mac(quiz_id, item_id, item.correct_index)
        with self._store.lock:
            self._store.connection.execute(
                "INSERT INTO sealed_keys "
                "(quiz_id, item_id, correct_index, explanation, key_hmac, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (quiz_id, item_id, item.correct_index, item.explanation, mac, utc_now()),
            )

    def reveal(self, quiz_id: str, item_id: str) -> tuple[int, str]:
        """Return `(correct_index, explanation)` after verifying the HMAC.

        Raises:
            KeyError: If the key does not exist.
            TamperError: If the stored key does not match its HMAC.
        """
        with self._store.lock:
            row = self._store.connection.execute(
                "SELECT correct_index, explanation, key_hmac FROM sealed_keys "
                "WHERE quiz_id = ? AND item_id = ?",
                (quiz_id, item_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"no sealed key for item {item_id!r} in quiz {quiz_id!r}")

        correct_index = int(row["correct_index"])
        expected = self._mac(quiz_id, item_id, correct_index)
        if not hmac.compare_digest(str(row["key_hmac"]), expected):
            raise TamperError(f"sealed key for item {item_id!r} failed verification")
        return correct_index, str(row["explanation"])

    def _mac(self, quiz_id: str, item_id: str, correct_index: int) -> str:
        message = f"{quiz_id}\x00{item_id}\x00{correct_index}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()
