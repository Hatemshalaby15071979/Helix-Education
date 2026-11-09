"""SQLite-backed append-only event store.

Design notes:
- The `events` table is protected by triggers that abort UPDATE and
  DELETE. The API cannot rewrite history even if a caller tries.
- WAL mode plus `synchronous=FULL` means a committed event survives a
  process crash. A single lock serialises writes; FastAPI's sync
  endpoints run in a thread pool, so the connection is opened with
  `check_same_thread=False` and every access goes through that lock.
- The store owns the schema for the whole core (events, quizzes, items,
  sealed keys, answers) so one connection and one migration path cover
  all tables.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import CoreEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   TEXT NOT NULL UNIQUE,
    timestamp  TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TABLE IF NOT EXISTS quizzes (
    quiz_id    TEXT PRIMARY KEY,
    topic      TEXT NOT NULL,
    title      TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_items (
    quiz_id  TEXT NOT NULL,
    item_id  TEXT NOT NULL,
    position INTEGER NOT NULL,
    question TEXT NOT NULL,
    options  TEXT NOT NULL,
    PRIMARY KEY (quiz_id, item_id),
    FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS sealed_keys (
    quiz_id       TEXT NOT NULL,
    item_id       TEXT NOT NULL,
    correct_index INTEGER NOT NULL,
    explanation   TEXT NOT NULL,
    key_hmac      TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (quiz_id, item_id),
    FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS answers (
    answer_id      TEXT PRIMARY KEY,
    quiz_id        TEXT NOT NULL,
    item_id        TEXT NOT NULL,
    selected_index INTEGER NOT NULL,
    correct        INTEGER NOT NULL,
    answered_at    TEXT NOT NULL,
    FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_answers_quiz ON answers(quiz_id, item_id);
"""


def default_db_path() -> str:
    """Resolve the default on-disk database path.

    Precedence: `HELIX_CORE_DB` when set, otherwise
    `<user data dir>/helix-core/core.db`. The working directory is never
    used, so running the core cannot write state into a checkout.
    """
    override = os.environ.get("HELIX_CORE_DB", "").strip()
    if override:
        return override
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "helix-core", "core.db")


def utc_now() -> str:
    """Current UTC time as an ISO8601 string."""
    return datetime.now(UTC).isoformat()


class SqliteEventStore:
    """Append-only event log plus the core's relational schema.

    Inputs:
        path: SQLite file path, or `":memory:"` for tests.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript(_SCHEMA)

    # ── connection access ──────────────────────────────────────────────

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection. Callers must hold `lock`."""
        return self._conn

    @property
    def lock(self) -> threading.RLock:
        """The re-entrant lock that serialises access to the connection."""
        return self._lock

    def transaction(self):
        """Context manager for an explicit write transaction."""
        return _Transaction(self._conn, self._lock)

    # ── events ─────────────────────────────────────────────────────────

    def append(
        self,
        event_type: str,
        payload: dict,
        *,
        event_id: str | None = None,
        timestamp: str | None = None,
    ) -> CoreEvent:
        """Append one event and return the stored record.

        Raises:
            ValueError: If `event_type` is empty.
        """
        if not event_type or not isinstance(event_type, str):
            raise ValueError("event_type must be a non-empty string")
        eid = event_id or str(uuid4())
        ts = timestamp or utc_now()
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (event_id, timestamp, event_type, payload) VALUES (?, ?, ?, ?)",
                (eid, ts, event_type, body),
            )
            seq = int(cur.lastrowid)
        return CoreEvent(seq=seq, event_id=eid, timestamp=ts, event_type=event_type, payload=payload)

    def read_all(self) -> list[CoreEvent]:
        """Read every event in append order."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, event_id, timestamp, event_type, payload FROM events ORDER BY seq"
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def read_since(self, seq: int) -> list[CoreEvent]:
        """Read events with a sequence number greater than `seq`."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, event_id, timestamp, event_type, payload FROM events WHERE seq > ? ORDER BY seq",
                (seq,),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def count_events(self) -> int:
        """Number of events in the log."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()
        return int(row["n"])

    def close(self) -> None:
        """Close the connection."""
        with self._lock:
            self._conn.close()

    def __enter__(self) -> SqliteEventStore:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


class _Transaction:
    """BEGIN IMMEDIATE / COMMIT / ROLLBACK wrapper."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = conn
        self._lock = lock

    def __enter__(self) -> sqlite3.Connection:
        self._lock.acquire()
        self._conn.execute("BEGIN IMMEDIATE")
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self._conn.execute("COMMIT")
            else:
                self._conn.execute("ROLLBACK")
        finally:
            self._lock.release()


def _row_to_event(row: sqlite3.Row) -> CoreEvent:
    return CoreEvent(
        seq=int(row["seq"]),
        event_id=row["event_id"],
        timestamp=row["timestamp"],
        event_type=row["event_type"],
        payload=json.loads(row["payload"]),
    )
