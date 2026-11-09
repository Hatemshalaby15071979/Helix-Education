"""Deterministic multiple-choice scoring.

The core grades by index comparison, not by a model. The answer key is
already sealed before this function is called; this module has no
storage and no side effects.
"""

from __future__ import annotations


def score_selection(correct_index: int, selected_index: int) -> bool:
    """Return True when the selected option is the correct one.

    Raises:
        ValueError: If either index is negative.
    """
    if correct_index < 0:
        raise ValueError("correct_index must be non-negative")
    if selected_index < 0:
        raise ValueError("selected_index must be non-negative")
    return correct_index == selected_index


def percentage(correct: int, total: int) -> int:
    """Integer percentage, rounded half-up, clamped to 0..100."""
    if total <= 0:
        return 0
    value = int((correct * 100 + total // 2) // total)
    return max(0, min(100, value))
