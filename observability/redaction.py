"""Redaction helpers for log lines.

Why: CodeQL js/py clear-text-logging alerts fired on employee ids, skill names,
lesson ids and quiz scores written straight to the logger. That data is
personal and assessment-sensitive. A log line is a copy of data in a place with
a different retention policy from the database, so identifiers are hashed and
scores are bucketed before they are written anywhere.

This is deliberately not reversible: nothing in the product needs to recover an
id from a log line. Correlation works because the same input hashes to the same
token.
"""

from __future__ import annotations

import hashlib
from typing import Any


def redact_id(value: Any, *, length: int = 10) -> str:
    """Return a stable, non-reversible correlation token for an identifier."""
    if value is None:
        return "none"
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:length]
    return f"id:{digest}"


def bucket_score(value: Any) -> str:
    """Reduce a score to a coarse band, so logs cannot reconstruct an answer."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "score:unknown"
    if score >= 0.9:
        return "score:0.9-1.0"
    if score >= 0.75:
        return "score:0.75-0.9"
    if score >= 0.5:
        return "score:0.5-0.75"
    if score >= 0:
        return "score:0.0-0.5"
    return "score:invalid"
