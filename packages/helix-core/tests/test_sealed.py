"""Sealed key store: round-trip and tamper detection."""

from __future__ import annotations

import sqlite3

import pytest

from helix_core.models import QuizItem
from helix_core.sealed import SealedKeyStore, TamperError, load_secret
from helix_core.store import SqliteEventStore

SECRET = b"test-secret"


def _store() -> SqliteEventStore:
    store = SqliteEventStore(":memory:")
    store.connection.execute(
        "INSERT INTO quizzes (quiz_id, topic, title, created_at) VALUES ('q1', 't', NULL, 'now')"
    )
    return store


def test_seal_and_reveal_round_trip():
    store = _store()
    sealed = SealedKeyStore(store, SECRET)
    item = QuizItem(question="Q", options=("a", "b"), correct_index=1, explanation="because")

    sealed.seal("q1", "i1", item)
    assert sealed.reveal("q1", "i1") == (1, "because")


def test_tampered_key_is_rejected():
    store = _store()
    sealed = SealedKeyStore(store, SECRET)
    sealed.seal("q1", "i1", QuizItem(question="Q", options=("a", "b", "c"), correct_index=0))

    store.connection.execute("UPDATE sealed_keys SET correct_index = 2 WHERE item_id = 'i1'")

    with pytest.raises(TamperError):
        sealed.reveal("q1", "i1")


def test_missing_key_raises_key_error():
    sealed = SealedKeyStore(_store(), SECRET)
    with pytest.raises(KeyError):
        sealed.reveal("q1", "absent")


def test_duplicate_seal_is_rejected():
    store = _store()
    sealed = SealedKeyStore(store, SECRET)
    item = QuizItem(question="Q", options=("a", "b"), correct_index=0)
    sealed.seal("q1", "i1", item)

    with pytest.raises(sqlite3.IntegrityError):
        sealed.seal("q1", "i1", item)


def test_secret_file_is_created_and_reused(tmp_path, monkeypatch):
    monkeypatch.delenv("HELIX_CORE_SECRET", raising=False)
    path = tmp_path / "secret.key"

    first = load_secret(str(path))
    second = load_secret(str(path))

    assert len(first) == 32
    assert first == second
    assert path.exists()


def test_empty_secret_is_rejected():
    with pytest.raises(ValueError):
        SealedKeyStore(_store(), b"")
