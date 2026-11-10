<div align="center">

# Helix Education

[![CI](https://github.com/Hatemshalaby15071979/Helix-Education/actions/workflows/Python%20application/badge.svg)](https://github.com/Hatemshalaby15071979/Helix-Education/actions)
![licence](https://img.shields.io/badge/licence-MIT-blue)
![python](https://img.shields.io/badge/python-3.11%2B%20%E2%80%93%203.13-3776ab)
![status](https://img.shields.io/badge/status-2.1.1%20released-brightgreen)

**A learning engine that keeps a learner's record as evidence — replayable, inspectable, and sealed so a score can't be quietly changed.**

</div>

## What it is

Helix Education is a learning engine. It records what a person learns as a chain of
events, rebuilds their progress from that chain, and scores quizzes in a way that
cannot be silently edited afterwards. The core has **no AI dependency**, so a lesson
or a scored quiz works without a model in the loop.

It is the engine that powers the scoring behind Study Studio: the desktop app runs a
small piece of it, called `helix-core`, as a local sidecar on your machine.

## What you can do with it

- **Keep learning as evidence.** Every change is an event; current progress is
  rebuilt from the event log, not stored as one mutable blob.
- **Generate citation-grounded lessons** through the content engine.
- **Score quizzes that can't be tampered with.** A result is written once and sealed;
  the store exposes no way to edit it.
- **Build adaptive learning paths** and track progress and milestones.
- **Run it privately.** The core engine needs no cloud and no account.

## Before you start

You need **Python 3.11, 3.12 or 3.13**. The engine core itself needs nothing else.
To generate lessons you will want a local model runtime (Ollama or LM Studio); to
run the scoring service as a container you will need Docker.

## Get it and run it

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q          # 465 tests, all passing
```

The scoring service (`helix-core`) is its own distribution:

```bash
pip install helix-core
helix-core --port 8765        # loopback only
HELIX_CORE_TOKEN=... helix-core   # require a bearer token
```

## Is it private and safe? Straight answers

- **Your record stays yours.** Learning state is stored locally (a SQLite event log);
  the core needs no cloud and no account.
- **Scores are sealed, not just stored.** A scored result is append-only at the store
  API level, and the answer key lives in a separate store, verified with an HMAC before
  every score. A key edited on disk fails verification and the service refuses to grade
  rather than grading against the wrong answer.
- **Verified.** 465 automated tests pass on Python 3.11, 3.12 and 3.13, and every CI
  check is green. The parts that protect a learner's record — the event store, scoring,
  projections and the sealed-key store — are covered by tests.
- **Honest limits.** This is an early release (alpha). The gRPC competency service
  exists in business logic but is not wired up, external grounding and LLM calls are
  stubbed in tests, and it has not had an outside security audit.

## Status

<!-- docs-sync:start -->
**Version 2.1.1 — released 10 November 2026.** Two distributions ship from this repository: `helix-education` (the engine) and `helix-core` (the sealed scoring service, also published as a PyPI wheel and a GHCR container image). The CI badge at the top is the live build status.
<!-- docs-sync:end -->

## For developers

### How it fits the wider work

Helix Education is the learning foundation the wider Helix work is designed to build
on. Today it is **independently proven**: the desktop app Study Studio already calls
its `helix-core` scoring service as a sidecar. Its wiring into Helix Prime is designed
but not yet built — the gRPC competency service exists in business logic
(`CompetencyProfileLogic`) but its bindings are not generated and nothing mounts it.

### Architecture

- `state_core/` — event sourcing, scoring, projections, sealed-key store.
- `content_engine/` — citation-grounded lesson generation.
- `quiz_engine/` — assessment and scoring.
- `progress_engine/adaptive_paths/` — adaptive learning logic.
- `api_layer/grpc/` — competency contract; service wiring remains pending.

### Core service (`helix_core`)

`helix_core` is the extracted kernel: a SQLite-backed append-only event store, a
sealed answer-key store, deterministic multiple-choice scoring, and a small HTTP API.
Product shells call this instead of scoring quizzes themselves.

It is a **separate distribution**, `helix-core`, in `packages/helix-core/`. It depends
on `fastapi`, `pydantic` and `uvicorn` and on nothing else — this package's heavier
dependencies (`ollama`, `requests`, `beautifulsoup4`, `cryptography`) are not installed
with it. The two wheels are siblings, not parent and child: nothing in
`helix_education` imports `helix_core`.

| Endpoint | Purpose |
|---|---|
| `GET /v1/health` | liveness and event count |
| `POST /v1/quizzes` | register a quiz; returns public items only |
| `POST /v1/quizzes/{id}/answers` | score one answer |
| `GET /v1/quizzes/{id}/score` | current score summary |
| `GET /v1/topics/{topic}/state` | projection from `answer_scored` events |

Registration never returns `correct_index` or `explanation`. Those live in a separate
`sealed_keys` table and are verified with an HMAC before every score; a key edited on
disk fails verification and the API returns 409 instead of grading against the wrong
answer.

Build the wheels — one per distribution:

```bash
python -m build --wheel --outdir dist packages/helix-core   # helix_core-2.1.1-*.whl
python -m build --wheel --outdir dist .                     # helix_education-2.1.1-*.whl
python scripts/verify_distributions.py                      # asserts the split holds
```

`scripts/verify_distributions.py` is what stops the two from quietly drifting back
together: it fails if the core wheel grows a fourth dependency, if the parent wheel
still contains `helix_core/`, or if either ships bytecode.

`scripts/check_release.py` is what stops the version from drifting: it fails if the two
packages, the CHANGELOG and the git tags do not describe the same release.

### Container image

The core also ships as a container. The image contains `helix_core/` only — no Ollama
client, no scraper.

```bash
docker build -t helix-core:2.1.1 .
docker run --rm -p 127.0.0.1:8765:8000 \
  -e HELIX_CORE_SECRET=dev-secret -e HELIX_CORE_TOKEN=dev-token \
  helix-core:2.1.1
```

`.github/workflows/docker.yml` builds it, runs a register/answer/score smoke test
against `/v1/health`, and pushes `ghcr.io/<owner>/helix-core:{2.1.1,<sha>,latest}` **on
version tags only**. A push to `main` builds and smoke-tests the image but does not
publish it: an image published from a branch push is one nobody declared as a release.

`.github/workflows/publish-pypi.yml` publishes the wheels to PyPI, and is gated the
same way — it runs for a `v*` tag, and the upload step also requires the
`PYPI_API_TOKEN` secret to be present. Without the token the wheels are still built and
checked, and nothing is uploaded.

Kubernetes manifests live in `deploy/k8s/` and deploy **one replica** — the store is
SQLite, so more than one writer is corruption, not scale. Apply with
`kubectl apply -k deploy/k8s` after creating the namespace secret;
`deploy/DEPLOYMENT_RUNBOOK.md` has the full sequence, including backup and restore.

### See it work

Replay a learner's state from an event log, then check that a sealed quiz result cannot
be edited through the store API. Run from the repository root.

```python
from tempfile import TemporaryDirectory
from state_core.event_store import EventStore, SealedAnswerKeyStore, StoreConfig
from state_core.event_models import AnswerScoredEvent, QuizItemCreatedEvent
from state_core.scoring_engine import AnswerKey
from state_core.projections import project_topic_state
from learning_service import LearningService

with TemporaryDirectory() as tmp:
    store = EventStore(StoreConfig(path=f"{tmp}/learner.jsonl"))
    svc = LearningService(store, SealedAnswerKeyStore(StoreConfig(path="", sealed_keys_path=f"{tmp}/keys.jsonl")))
    svc.create_quiz_item("safeguarding", "saf-1", "q1", "Name the four categories.", "short_answer", "easy",
                         AnswerKey(required_keywords=["physical", "emotional", "neglect", "sexual"]))
    svc.submit_and_score_answer("q1", "physical, emotional, neglect and sexual harm")
    state = project_topic_state(store.read_all(), "safeguarding")
    next(e for e in store.read_all() if isinstance(e, AnswerScoredEvent)).raw_score = 0.0  # rewrite attempt
    print("replayed :", state.topic, "| attempts", state.attempts_total, "| passes", state.pass_count)
    print("sealed   :", next(e.answer_key_hash for e in store.read_all() if isinstance(e, QuizItemCreatedEvent))[:16])
    print("edit API :", [m for m in ("update", "delete", "remove") if hasattr(store, m)] or "none (append-only)")
    print("persisted:", next(e.raw_score for e in store.read_all() if isinstance(e, AnswerScoredEvent)))
```

Real output:

```
replayed : safeguarding | attempts 1 | passes 1
sealed   : 6ec99c50195ae0a7
edit API : none (append-only)
persisted: 1.0
```

The learner state is rebuilt from the log alone — nothing is carried in memory between
the write and the replay. The last three lines are the sealing check: the store exposes
no `update`, `delete` or `remove`, only `append`, so the rewrite attempt on the
in-memory event never reaches the persisted record, which still reads `1.0`. The answer
key is never written to the log; only its SHA-256 hash appears in the
`QuizItemCreatedEvent`.

What "sealed" guarantees, stated exactly:

- **Append-only at the store API level.** `EventStore` exposes `append` and the read
  methods, and no operation that rewrites or removes an event already written. That is
  an API contract, not tamper-evidence: the log is a plain JSONL file, and anything with
  write access to the filesystem can edit it.
- **Where keys live.** The answer key is held in a separate key store, never in the
  event log. The default location is `<user data dir>/helix-education/sealed_answer_keys.jsonl`
  — `%LOCALAPPDATA%` on Windows, `$XDG_DATA_HOME` or `~/.local/share` elsewhere. Override
  it with the `HELIX_SEALED_KEY_PATH` environment variable, or pass
  `StoreConfig.sealed_keys_path`. The working directory is never used, so running the
  engine cannot write state into a checkout.
- **Not encrypted by default.** The default key store is plaintext JSONL.
  `EncryptedSealedKeyStore` (which now refuses to start without a configured master key
  rather than falling back to a built-in default) and the Vault adapter both exist in the
  tree, but neither is wired in.

## Related work

- [How this project fits the wider work](https://github.com/Hatemshalaby15071979/Hatemshalaby15071979)

## Author

Built by Hatem Shalaby, Contact Centre Operations & AI Implementation Lead | WFM & CX
Transformation. Background: https://github.com/Hatemshalaby15071979

## Licence

MIT
