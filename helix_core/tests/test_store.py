"""Event store: append-only guarantees, ordering, and durability."""

from __future__ import annotations

import sqlite3

import pytest

from helix_core.store import SqliteEventStore


def test_append_and_read_in_order():
    store = SqliteEventStore(":memory:")
    first = store.append("topic_started", {"topic": "safeguarding"})
    second = store.append("answer_scored", {"topic": "safeguarding", "correct": True})

    assert first.seq < second.seq
    events = store.read_all()
    assert [event.event_type for event in events] == ["topic_started", "answer_scored"]
    assert events[1].payload["correct"] is True
    assert store.count_events() == 2


def test_read_since_returns_only_newer_events():
    store = SqliteEventStore(":memory:")
    first = store.append("a", {})
    store.append("b", {})
    store.append("c", {})

    assert [event.event_type for event in store.read_since(first.seq)] == ["b", "c"]


def test_events_cannot_be_updated_or_deleted():
    store = SqliteEventStore(":memory:")
    store.append("topic_started", {"topic": "x"})

    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute("UPDATE events SET event_type = 'rewritten'")
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute("DELETE FROM events")

    assert store.count_events() == 1


def test_events_survive_reopen(tmp_path):
    path = str(tmp_path / "core.db")
    with SqliteEventStore(path) as store:
        store.append("topic_started", {"topic": "persisted"})

    with SqliteEventStore(path) as reopened:
        assert reopened.count_events() == 1
        assert reopened.read_all()[0].payload["topic"] == "persisted"


def test_empty_event_type_is_rejected():
    store = SqliteEventStore(":memory:")
    with pytest.raises(ValueError):
        store.append("", {})
