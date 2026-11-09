# helix-core

Sealed quiz scoring and an append-only event store over SQLite. This is the
kernel of [Helix Education](https://github.com/Hatemshalaby15071979/Helix-Education),
extracted so that product shells can depend on it without pulling in an LLM
client, an HTML scraper, or the rest of the platform.

```bash
pip install helix-core
helix-core --port 8765              # loopback only
HELIX_CORE_TOKEN=... helix-core     # require a bearer token
```

| Endpoint | Purpose |
|---|---|
| `GET /v1/health` | liveness and event count |
| `POST /v1/quizzes` | register a quiz; returns public items only |
| `POST /v1/quizzes/{id}/answers` | score one answer |
| `GET /v1/quizzes/{id}/score` | current score summary |
| `GET /v1/topics/{topic}/state` | projection from `answer_scored` events |

## What "sealed" means

Registration returns questions and options and nothing else. The correct
index and the explanation are written to a separate `sealed_keys` table with
an HMAC over `(quiz_id, item_id, correct_index)`. Every scoring read verifies
that HMAC first. A key edited on disk fails verification and the API returns
**409** rather than grading against the wrong answer.

This is integrity, not secrecy against someone who can read both the database
and the secret. The threat model is stated in `helix_core/sealed.py`.

## Storage

One SQLite file, WAL mode, `synchronous=FULL`, with triggers that abort any
`UPDATE` or `DELETE` on the event log. State is a projection over that log,
not a mutable table, so the same numbers can be replayed from an export.

Default location is `<user data dir>/helix-core/core.db`; override with
`HELIX_CORE_DB`. The working directory is never used.

**Single writer.** Do not run two processes against one database file. For a
multi-replica deployment the store needs a Postgres implementation; the
manifests and the reasoning are in the parent repository's
`deploy/DEPLOYMENT_RUNBOOK.md`.

## Configuration

| Variable | Purpose |
|---|---|
| `HELIX_CORE_DB` | SQLite path |
| `HELIX_CORE_TOKEN` | bearer token required on every endpoint except `/v1/health` |
| `HELIX_CORE_SECRET` | HMAC key for sealed answers (or `HELIX_CORE_SECRET_FILE`) |

`HELIX_CORE_SECRET` is part of the data. Rotating it without re-sealing makes
every existing quiz unscoreable.

## Development

```bash
pip install -e ".[dev]"
pytest
```

27 tests. The parent repository also runs them as part of its suite.
