"""Helix Core — the SQLite-backed, event-sourced learning core.

This package is the extracted, product-facing kernel: an append-only
event store, a sealed answer-key store, deterministic scoring, and a
small HTTP API that product shells (Study Studio, L&D Command Center)
call instead of scoring quizzes themselves.

The core never returns an answer key for an unanswered item. Answer
keys are held in a separate table and verified with an HMAC before use,
so a tampered key refuses to score rather than scoring silently.
"""

from .models import AnswerResult, CoreEvent, PublicQuizItem, QuizItem, RegisteredQuiz, ScoreSummary
from .service import LearningCore
from .store import SqliteEventStore

__all__ = [
    "AnswerResult",
    "CoreEvent",
    "LearningCore",
    "PublicQuizItem",
    "QuizItem",
    "RegisteredQuiz",
    "ScoreSummary",
    "SqliteEventStore",
]

__version__ = "2.1.1"
