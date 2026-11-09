"""The core service: registration, scoring, and projection.

This is the only object product shells need. It owns the store and the
sealed key store; the HTTP layer is a thin adapter over it.
"""

from __future__ import annotations

import json
from uuid import uuid4

from .models import (
    AnswerResult,
    ItemScore,
    PublicQuizItem,
    QuizItem,
    RegisteredQuiz,
    ScoreSummary,
)
from .scoring import percentage, score_selection
from .sealed import SealedKeyStore, load_secret
from .store import SqliteEventStore, utc_now

_MAX_OPTIONS = 6


class LearningCore:
    """Register quizzes, score answers, and project topic state.

    Inputs:
        db_path: SQLite path, or `":memory:"` for tests.
        secret: HMAC key for sealed answer keys. Loaded from the
            environment or the user-data secret file when omitted.
        token: Optional bearer token required by the HTTP API. When
            omitted, the API is loopback-only and unauthenticated.
    """

    def __init__(self, db_path: str, *, secret: bytes | None = None, token: str | None = None) -> None:
        self.store = SqliteEventStore(db_path)
        self.sealed = SealedKeyStore(self.store, secret or load_secret())
        self.token = token

    # ── quiz lifecycle ─────────────────────────────────────────────────

    def register_quiz(
        self,
        topic: str,
        items: list[QuizItem],
        *,
        title: str | None = None,
    ) -> RegisteredQuiz:
        """Validate and persist a quiz, sealing every answer key.

        Returns the client-safe items (no keys, no explanations).

        Raises:
            ValueError: If the topic is empty, no items are supplied, or
                an item is malformed.
        """
        topic = (topic or "").strip()
        if not topic:
            raise ValueError("topic must not be empty")
        if not items:
            raise ValueError("at least one quiz item is required")

        quiz_id = str(uuid4())
        prepared: list[tuple[str, int, QuizItem]] = []
        for position, item in enumerate(items):
            self._validate_item(item)
            prepared.append((str(uuid4()), position, item))

        public: list[PublicQuizItem] = []
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO quizzes (quiz_id, topic, title, created_at) VALUES (?, ?, ?, ?)",
                (quiz_id, topic, title, utc_now()),
            )
            for item_id, position, item in prepared:
                conn.execute(
                    "INSERT INTO quiz_items (quiz_id, item_id, position, question, options) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (quiz_id, item_id, position, item.question, json.dumps(list(item.options), ensure_ascii=False)),
                )
                self.sealed.seal(quiz_id, item_id, item)
                public.append(
                    PublicQuizItem(
                        item_id=item_id,
                        position=position,
                        question=item.question,
                        options=item.options,
                    )
                )
            self.store.append(
                "quiz_registered",
                {"quiz_id": quiz_id, "topic": topic, "title": title, "item_count": len(prepared)},
            )

        return RegisteredQuiz(quiz_id=quiz_id, topic=topic, title=title, items=tuple(public))

    def submit_answer(self, quiz_id: str, item_id: str, selected_index: int) -> AnswerResult:
        """Score one answer against the sealed key.

        Raises:
            KeyError: If the quiz or item does not exist.
            ValueError: If `selected_index` is out of range.
            TamperError: If the sealed key fails verification.
        """
        quiz = self._quiz_row(quiz_id)
        item = self._item_row(quiz_id, item_id)
        options = json.loads(item["options"])
        if selected_index < 0 or selected_index >= len(options):
            raise ValueError(f"selected_index {selected_index} is outside 0..{len(options) - 1}")

        correct_index, explanation = self.sealed.reveal(quiz_id, item_id)
        correct = score_selection(correct_index, selected_index)

        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO answers (answer_id, quiz_id, item_id, selected_index, correct, answered_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid4()), quiz_id, item_id, selected_index, int(correct), utc_now()),
            )
            self.store.append(
                "answer_scored",
                {
                    "quiz_id": quiz_id,
                    "quiz_item_id": item_id,
                    "topic": quiz["topic"],
                    "selected_index": selected_index,
                    "correct": correct,
                },
            )

        return AnswerResult(
            item_id=item_id,
            correct=correct,
            correct_index=correct_index,
            explanation=explanation,
        )

    def quiz_score(self, quiz_id: str) -> ScoreSummary:
        """Return the current score for a quiz.

        Each item uses its most recent answer; unanswered items count as
        incorrect in `percentage`.
        """
        self._quiz_row(quiz_id)
        with self.store.lock:
            items = self.store.connection.execute(
                "SELECT item_id, position, question, options FROM quiz_items "
                "WHERE quiz_id = ? ORDER BY position",
                (quiz_id,),
            ).fetchall()
            answers = self.store.connection.execute(
                "SELECT item_id, selected_index, correct FROM answers "
                "WHERE quiz_id = ? ORDER BY answered_at DESC, rowid DESC",
                (quiz_id,),
            ).fetchall()

        latest: dict[str, tuple[int, bool]] = {}
        for row in answers:
            latest.setdefault(row["item_id"], (int(row["selected_index"]), bool(row["correct"])))

        scored: list[ItemScore] = []
        correct_count = 0
        for row in items:
            item_id = row["item_id"]
            if item_id in latest:
                selected, correct = latest[item_id]
                correct_index, explanation = self.sealed.reveal(quiz_id, item_id)
                correct_count += int(correct)
                scored.append(
                    ItemScore(
                        item_id=item_id,
                        position=int(row["position"]),
                        question=row["question"],
                        answered=True,
                        selected_index=selected,
                        correct=correct,
                        correct_index=correct_index,
                        explanation=explanation,
                    )
                )
            else:
                scored.append(
                    ItemScore(
                        item_id=item_id,
                        position=int(row["position"]),
                        question=row["question"],
                        answered=False,
                    )
                )

        return ScoreSummary(
            quiz_id=quiz_id,
            total=len(items),
            answered=len(latest),
            correct=correct_count,
            percentage=percentage(correct_count, len(items)),
            items=tuple(scored),
        )

    # ── projections ────────────────────────────────────────────────────

    def topic_state(self, topic: str) -> dict:
        """Project topic state from `answer_scored` events.

        This is a pure fold over the event log, not a table read, so the
        same numbers can be reproduced from an exported log.
        """
        attempts = 0
        correct = 0
        last_activity = ""
        for event in self.store.read_all():
            if event.event_type != "answer_scored":
                continue
            if event.payload.get("topic") != topic:
                continue
            attempts += 1
            correct += int(bool(event.payload.get("correct")))
            if event.timestamp > last_activity:
                last_activity = event.timestamp

        return {
            "topic": topic,
            "attempts_total": attempts,
            "correct_count": correct,
            "accuracy": round(correct / attempts, 4) if attempts else 0.0,
            "last_activity": last_activity,
        }

    def close(self) -> None:
        """Close the underlying store."""
        self.store.close()

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _validate_item(item: QuizItem) -> None:
        if not item.question or not item.question.strip():
            raise ValueError("quiz item question must not be empty")
        if not 2 <= len(item.options) <= _MAX_OPTIONS:
            raise ValueError(f"quiz item must have 2..{_MAX_OPTIONS} options")
        if any(not str(option).strip() for option in item.options):
            raise ValueError("quiz item options must not be empty")
        if not 0 <= item.correct_index < len(item.options):
            raise ValueError("correct_index is outside the option range")

    def _quiz_row(self, quiz_id: str):
        with self.store.lock:
            row = self.store.connection.execute(
                "SELECT quiz_id, topic, title FROM quizzes WHERE quiz_id = ?", (quiz_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown quiz {quiz_id!r}")
        return row

    def _item_row(self, quiz_id: str, item_id: str):
        with self.store.lock:
            row = self.store.connection.execute(
                "SELECT item_id, position, question, options FROM quiz_items "
                "WHERE quiz_id = ? AND item_id = ?",
                (quiz_id, item_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown item {item_id!r} in quiz {quiz_id!r}")
        return row
