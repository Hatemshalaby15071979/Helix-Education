"""Service: registration, scoring, projections, and validation."""

from __future__ import annotations

import pytest

from helix_core.models import QuizItem
from helix_core.service import LearningCore

SECRET = b"test-secret"


def _core() -> LearningCore:
    return LearningCore(":memory:", secret=SECRET)


def _items() -> list[QuizItem]:
    return [
        QuizItem(question="2+2?", options=("3", "4"), correct_index=1, explanation="Four."),
        QuizItem(question="Capital of France?", options=("Paris", "Rome", "Madrid"), correct_index=0),
    ]


def test_registration_returns_public_items_only():
    core = _core()
    quiz = core.register_quiz("math", _items(), title="Basics")

    assert quiz.topic == "math"
    assert len(quiz.items) == 2
    assert not hasattr(quiz.items[0], "correct_index")
    assert quiz.items[0].options == ("3", "4")


def test_correct_and_incorrect_answers_are_scored():
    core = _core()
    quiz = core.register_quiz("math", _items())

    right = core.submit_answer(quiz.quiz_id, quiz.items[0].item_id, 1)
    wrong = core.submit_answer(quiz.quiz_id, quiz.items[1].item_id, 2)

    assert right.correct is True and right.correct_index == 1
    assert wrong.correct is False and wrong.correct_index == 0
    assert wrong.explanation == ""


def test_score_summary_counts_unanswered_as_incorrect():
    core = _core()
    quiz = core.register_quiz("math", _items())
    core.submit_answer(quiz.quiz_id, quiz.items[0].item_id, 1)

    summary = core.quiz_score(quiz.quiz_id)

    assert (summary.total, summary.answered, summary.correct, summary.percentage) == (2, 1, 1, 50)
    assert summary.items[1].answered is False
    assert summary.items[1].correct_index is None


def test_retry_uses_the_latest_answer():
    core = _core()
    quiz = core.register_quiz("math", _items())
    item_id = quiz.items[0].item_id

    core.submit_answer(quiz.quiz_id, item_id, 0)
    core.submit_answer(quiz.quiz_id, item_id, 1)

    summary = core.quiz_score(quiz.quiz_id)
    assert summary.answered == 1
    assert summary.correct == 1


def test_topic_state_is_projected_from_events():
    core = _core()
    quiz = core.register_quiz("math", _items())
    core.submit_answer(quiz.quiz_id, quiz.items[0].item_id, 1)
    core.submit_answer(quiz.quiz_id, quiz.items[1].item_id, 1)

    state = core.topic_state("math")
    assert state["attempts_total"] == 2
    assert state["correct_count"] == 1
    assert state["accuracy"] == 0.5
    assert state["last_activity"]


def test_invalid_items_are_rejected():
    core = _core()
    with pytest.raises(ValueError):
        core.register_quiz("math", [])
    with pytest.raises(ValueError):
        core.register_quiz("math", [QuizItem(question="Q", options=("only",), correct_index=0)])
    with pytest.raises(ValueError):
        core.register_quiz("math", [QuizItem(question="Q", options=("a", "b"), correct_index=5)])
    with pytest.raises(ValueError):
        core.register_quiz("", _items())


def test_out_of_range_answer_is_rejected():
    core = _core()
    quiz = core.register_quiz("math", _items())
    with pytest.raises(ValueError):
        core.submit_answer(quiz.quiz_id, quiz.items[0].item_id, 9)


def test_unknown_quiz_and_item_raise_key_error():
    core = _core()
    quiz = core.register_quiz("math", _items())
    with pytest.raises(KeyError):
        core.submit_answer("missing", quiz.items[0].item_id, 0)
    with pytest.raises(KeyError):
        core.submit_answer(quiz.quiz_id, "missing", 0)
