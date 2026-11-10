<div align="center">

# Helix Education

[![CI](https://github.com/Hatemshalaby15071979/Helix-Education/actions/workflows/ci.yml/badge.svg)](https://github.com/Hatemshalaby15071979/Helix-Education/actions)
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

The code is split into four areas: the event store and scoring core
(`state_core/`), lesson generation (`content_engine/`), quizzes
(`quiz_engine/`), and adaptive learning paths (`progress_engine/`). A fifth
area — the gRPC competency contract in `api_layer/grpc/` — exists in business
logic but is not wired up yet.

**Two packages, deliberately separate.** This repository ships two
distributions: `helix-education` (the engine) and `helix-core` (the sealed
scoring service). The scoring service is the small kernel other apps embed —
Study Studio already does. It depends on almost nothing, and nothing in the
engine imports it. Two checker scripts keep them from drifting back together:
one fails if the split breaks, the other fails if the two packages, the
changelog and the git tags don't describe the same release.

```bash
python -m build --wheel --outdir dist packages/helix-core   # helix_core-*.whl
python -m build --wheel --outdir dist .                     # helix_education-*.whl
python scripts/verify_distributions.py                      # asserts the split holds
```

**The scoring service over HTTP.** Register a quiz, score answers, read the
score. The API never returns correct answers or explanations — those live in a
separate sealed key store, verified before every score. Run it two ways:

```bash
helix-core --port 8765                      # loopback only
docker run --rm -p 127.0.0.1:8765:8000 helix-core:2.1.1   # container (CI builds it on version tags)
```

The container image and the PyPI wheels are published only from version tags —
a push to `main` builds and smoke-tests but publishes nothing. Kubernetes
manifests in `deploy/k8s/` deploy one replica on purpose: the store is SQLite,
so more than one writer is corruption, not scale. Full sequence, including
backup/restore: `deploy/DEPLOYMENT_RUNBOOK.md`.

**What "sealed" guarantees — stated exactly:**

- The store's API is append-only: there is no update or delete, so a score
  cannot be quietly changed through the API.
- The answer key lives outside the event log, and its hash — not the key
  itself — is what's recorded. A key edited on disk fails verification and the
  service refuses to grade.
- The log is a plain file, and the default key store is not encrypted: anything
  with filesystem access can edit it. That's the honest boundary; encrypted and
  Vault-backed stores exist in the tree but are not wired in.

## Related work

- [How this project fits the wider work](https://github.com/Hatemshalaby15071979/Hatemshalaby15071979)

## Author

Built by Hatem Shalaby, Contact Centre Operations & AI Implementation Lead | WFM & CX
Transformation. Background: https://github.com/Hatemshalaby15071979

## Licence

MIT
