"""HTTP adapter: contract, auth, and error mapping."""

from __future__ import annotations

from fastapi.testclient import TestClient

from helix_core.api import create_app
from helix_core.service import LearningCore

SECRET = b"test-secret"


def _client(token: str | None = None) -> tuple[TestClient, LearningCore]:
    core = LearningCore(":memory:", secret=SECRET, token=token)
    return TestClient(create_app(core)), core


def _payload() -> dict:
    return {
        "topic": "safeguarding",
        "title": "Basics",
        "items": [
            {"question": "Name a category.", "options": ["physical", "budget"], "correct_index": 0,
             "explanation": "Physical harm is one of the four categories."},
            {"question": "Name another.", "options": ["emotional", "inventory"], "correct_index": 0},
        ],
    }


def test_health_is_public():
    client, _ = _client()
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_registration_never_returns_the_key():
    client, _ = _client()
    response = client.post("/v1/quizzes", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert "correct_index" not in body["items"][0]
    assert "explanation" not in body["items"][0]


def test_answer_then_score_round_trip():
    client, _ = _client()
    quiz = client.post("/v1/quizzes", json=_payload()).json()
    first, second = quiz["items"]

    right = client.post(
        f"/v1/quizzes/{quiz['quiz_id']}/answers",
        json={"item_id": first["item_id"], "selected_index": 0},
    )
    wrong = client.post(
        f"/v1/quizzes/{quiz['quiz_id']}/answers",
        json={"item_id": second["item_id"], "selected_index": 1},
    )

    assert right.status_code == 200
    assert right.json()["correct"] is True
    assert right.json()["explanation"].startswith("Physical")
    assert wrong.json()["correct"] is False

    score = client.get(f"/v1/quizzes/{quiz['quiz_id']}/score").json()
    assert score["total"] == 2
    assert score["correct"] == 1
    assert score["percentage"] == 50


def test_token_is_required_when_configured():
    client, _ = _client(token="s3cret")

    assert client.post("/v1/quizzes", json=_payload()).status_code == 401
    ok = client.post("/v1/quizzes", json=_payload(), headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_unknown_quiz_maps_to_404():
    client, _ = _client()
    response = client.get("/v1/quizzes/does-not-exist/score")
    assert response.status_code == 404


def test_bad_answer_index_maps_to_400():
    client, _ = _client()
    quiz = client.post("/v1/quizzes", json=_payload()).json()
    response = client.post(
        f"/v1/quizzes/{quiz['quiz_id']}/answers",
        json={"item_id": quiz["items"][0]["item_id"], "selected_index": 99},
    )
    assert response.status_code == 400


def test_tampered_key_maps_to_409():
    client, core = _client()
    quiz = client.post("/v1/quizzes", json=_payload()).json()
    item_id = quiz["items"][0]["item_id"]

    core.store.connection.execute(
        "UPDATE sealed_keys SET correct_index = 1 WHERE quiz_id = ? AND item_id = ?",
        (quiz["quiz_id"], item_id),
    )
    response = client.post(
        f"/v1/quizzes/{quiz['quiz_id']}/answers",
        json={"item_id": item_id, "selected_index": 0},
    )
    assert response.status_code == 409


def test_topic_state_endpoint():
    client, _ = _client()
    quiz = client.post("/v1/quizzes", json=_payload()).json()
    client.post(
        f"/v1/quizzes/{quiz['quiz_id']}/answers",
        json={"item_id": quiz["items"][0]["item_id"], "selected_index": 0},
    )

    state = client.get("/v1/topics/safeguarding/state").json()
    assert state["attempts_total"] == 1
    assert state["correct_count"] == 1
