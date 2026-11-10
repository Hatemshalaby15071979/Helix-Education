"""HTTP adapter for the Helix Core.

The API is deliberately small: register a quiz, submit an answer, read a
score, read a topic projection. There is no endpoint that returns an
answer key for an unanswered item.

Run it with `helix-core` (or `python -m helix_core`). It binds loopback
by default; set `HELIX_CORE_TOKEN` to require a bearer token.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .models import QuizItem
from .sealed import TamperError
from .service import LearningCore

__all__ = ["create_app"]


class ItemIn(BaseModel):
    """One authored quiz item."""

    question: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=6)
    correct_index: int = Field(ge=0)
    explanation: str = ""


class QuizIn(BaseModel):
    """Payload for registering a quiz."""

    topic: str = Field(min_length=1)
    title: str | None = None
    items: list[ItemIn] = Field(min_length=1)


class PublicItemOut(BaseModel):
    item_id: str
    position: int
    question: str
    options: list[str]


class QuizOut(BaseModel):
    quiz_id: str
    topic: str
    title: str | None
    items: list[PublicItemOut]


class AnswerIn(BaseModel):
    item_id: str = Field(min_length=1)
    selected_index: int = Field(ge=0)


class AnswerOut(BaseModel):
    item_id: str
    correct: bool
    correct_index: int
    explanation: str


class ItemScoreOut(BaseModel):
    item_id: str
    position: int
    question: str
    answered: bool
    selected_index: int | None = None
    correct: bool | None = None
    correct_index: int | None = None
    explanation: str | None = None


class ScoreOut(BaseModel):
    quiz_id: str
    total: int
    answered: int
    correct: int
    percentage: int
    items: list[ItemScoreOut]


class HealthOut(BaseModel):
    status: str
    version: str
    events: int


def create_app(core: LearningCore, *, version: str = "2.1.1") -> FastAPI:
    """Build the FastAPI application around a `LearningCore`."""
    app = FastAPI(title="Helix Core", version=version, docs_url="/docs", redoc_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost|http://tauri\.localhost)$",
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
        if not core.token:
            return
        if authorization != f"Bearer {core.token}":
            raise HTTPException(status_code=401, detail="invalid or missing bearer token")

    auth = Depends(require_token)

    @app.exception_handler(KeyError)
    async def _not_found(_request, exc: KeyError):
        return _json_error(404, str(exc).strip("'"))

    @app.exception_handler(TamperError)
    async def _tampered(_request, exc: TamperError):
        return _json_error(409, str(exc))

    @app.exception_handler(ValueError)
    async def _bad_request(_request, exc: ValueError):
        return _json_error(400, str(exc))

    @app.get("/v1/health", response_model=HealthOut)
    def health() -> HealthOut:
        return HealthOut(status="ok", version=version, events=core.store.count_events())

    @app.post("/v1/quizzes", response_model=QuizOut, dependencies=[auth])
    def register_quiz(body: QuizIn) -> QuizOut:
        quiz = core.register_quiz(
            body.topic,
            [
                QuizItem(
                    question=item.question,
                    options=tuple(item.options),
                    correct_index=item.correct_index,
                    explanation=item.explanation,
                )
                for item in body.items
            ],
            title=body.title,
        )
        return QuizOut(
            quiz_id=quiz.quiz_id,
            topic=quiz.topic,
            title=quiz.title,
            items=[
                PublicItemOut(
                    item_id=item.item_id,
                    position=item.position,
                    question=item.question,
                    options=list(item.options),
                )
                for item in quiz.items
            ],
        )

    @app.post("/v1/quizzes/{quiz_id}/answers", response_model=AnswerOut, dependencies=[auth])
    def submit_answer(quiz_id: str, body: AnswerIn) -> AnswerOut:
        result = core.submit_answer(quiz_id, body.item_id, body.selected_index)
        return AnswerOut(
            item_id=result.item_id,
            correct=result.correct,
            correct_index=result.correct_index,
            explanation=result.explanation,
        )

    @app.get("/v1/quizzes/{quiz_id}/score", response_model=ScoreOut, dependencies=[auth])
    def quiz_score(quiz_id: str) -> ScoreOut:
        summary = core.quiz_score(quiz_id)
        return ScoreOut(
            quiz_id=summary.quiz_id,
            total=summary.total,
            answered=summary.answered,
            correct=summary.correct,
            percentage=summary.percentage,
            items=[
                ItemScoreOut(
                    item_id=item.item_id,
                    position=item.position,
                    question=item.question,
                    answered=item.answered,
                    selected_index=item.selected_index,
                    correct=item.correct,
                    correct_index=item.correct_index,
                    explanation=item.explanation,
                )
                for item in summary.items
            ],
        )

    @app.get("/v1/topics/{topic}/state", dependencies=[auth])
    def topic_state(topic: str) -> dict:
        return core.topic_state(topic)

    return app


def _json_error(status_code: int, detail: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content={"detail": detail})
