"""Domain models for the Helix Core.

The models are intentionally small and framework-free. The HTTP layer
(`helix_core.api`) maps them to request/response schemas; the store and
service layers never import FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CoreEvent:
    """One immutable record in the append-only event log.

    Inputs:
        seq: Monotonic sequence number assigned by SQLite.
        event_id: UUID4 string, unique across the log.
        timestamp: ISO8601 UTC timestamp.
        event_type: Registered snake_case event name.
        payload: JSON-serialisable event body.
    """

    seq: int
    event_id: str
    timestamp: str
    event_type: str
    payload: dict


@dataclass(frozen=True)
class QuizItem:
    """An authored quiz item, including its answer key.

    This type never leaves the core. `correct_index` and `explanation`
    are sealed at registration and revealed only after an answer is
    submitted.
    """

    question: str
    options: tuple[str, ...]
    correct_index: int
    explanation: str = ""


@dataclass(frozen=True)
class PublicQuizItem:
    """The client-safe view of a quiz item: no key, no explanation."""

    item_id: str
    position: int
    question: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class RegisteredQuiz:
    """Result of registering a quiz with the core."""

    quiz_id: str
    topic: str
    title: str | None
    items: tuple[PublicQuizItem, ...]


@dataclass(frozen=True)
class AnswerResult:
    """Result of scoring one submitted answer.

    `correct_index` and `explanation` are returned only here, after the
    learner has committed to an answer, so the UI can reveal feedback.
    """

    item_id: str
    correct: bool
    correct_index: int
    explanation: str


@dataclass(frozen=True)
class ItemScore:
    """Per-item state in a quiz score summary."""

    item_id: str
    position: int
    question: str
    answered: bool
    selected_index: int | None = None
    correct: bool | None = None
    correct_index: int | None = None
    explanation: str | None = None


@dataclass(frozen=True)
class ScoreSummary:
    """Aggregate score for one quiz.

    `percentage` is 0 when nothing has been answered, and is computed
    over the whole quiz (unanswered items count as incorrect).
    """

    quiz_id: str
    total: int
    answered: int
    correct: int
    percentage: int
    items: tuple[ItemScore, ...] = field(default_factory=tuple)
