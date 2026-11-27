# GOVERNANCE.md — Operating Policy & Repo Map for Helix Education

> Companion to `CONSTITUTION.md` (the *why* — philosophy and clean-code policy, which
> this file enforces operationally) and `AGENTS.md` (the agent charter + ledger).
> Read all three before acting. This file may be updated by any agent **as a logged
> governance change**; the CONSTITUTION itself is owner-only.

## 1. Repository map

Authoritative directory map for **Helix Education**. Any file you add, move, rename, or
delete gets reflected here in the same landing.

| Path | Purpose (one line) |
|---|---|
| `learning_service/`, `content_engine/`, `quiz_engine/`, `progress_engine/`, `delivery_engine/` | The engines that make up the learning pipeline: what is taught, how it is scored, how progress is rebuilt, how a lesson is delivered. |
| `cognitive_engine/`, `grounding_engine/`, `cognitive_agent/`, `analytics_engine/` | The cognitive and analytics layer. |
| `state_core/`, `packages/helix-core/` | The event-sourced state core. `helix-core` is its own distribution and runs its own suite from its own directory. |
| `api_layer/` | The API surface. |
| `helix_education/` | The application package. |
| `lessons/`, `exercises/`, `data/` | Authored lessons, exercises and their data. |
| `dashboard/`, `marketing/`, `assets/` | Presentation and brand. |
| `deploy/`, `observability/` | Deployment and telemetry. |
| `docs/`, `docs/ARCHIVE/`, `wiki/`, `LEARNING-RECORDS/` | Documentation, historical findings, the wiki, and learner records. |
| `scripts/`, `tests/` | Release gates and the test suite. |
| `.github/` | CI workflows. |

**`docs/ARCHIVE/` is spelled in capitals in this repository.** Every other repository in
the portfolio uses `docs/archive/`. It is left as it is here rather than renaming a
directory and every link into it during a documentation landing; unifying the spelling
is a tidy the owner may want, and it is recorded here so nobody "fixes" one of the two.

## 2. Documentation policy (what belongs where)

**Root holds only the requested set** — nothing else:

| File | State | Purpose |
|---|---|---|
| `README.md` | required | The single source of truth: what this is, why it's here, how to use it — in simple English for a professional reader. Carries the Helix Solutions logo. |
| `AGENTS.md` | required | Agent charter + sign-in/out ledger. |
| `CONSTITUTION.md` | required | The owner's engineering philosophy and clean-code policy (unified across every repo). |
| `GOVERNANCE.md` | required | This file: repo map, documentation policy, sync policy, archiving rules. |
| `CHANGELOG.md` | standard | Dated user-visible changes. Read by `scripts/check_release.py`, which requires it to agree with the version manifests and the git tags. |
| `LICENSE` / `LICENSE.md` | standard | MIT, unless the repo states otherwise. |
| `SECURITY.md` | standard | Threat model, vulnerability reporting, secret handling. |

**Everything else lives in `docs/`** — reports, audit logs, execution plans, research
notes, ADRs, runbooks, anything dated or one-off. No stray `.md`/`.txt` at the root.
If a document at the root is not in the table above, move it to `docs/` (or
`docs/ARCHIVE/` if it is historical) and record the move in the `AGENTS.md` ledger.

### Second constitution-shaped document, recorded not resolved

The portfolio standard puts one `CONSTITUTION.md` at the root of every repository, with
the same text everywhere. This repository already carried a different one at
**`docs/CONSTITUTION.md`** — *"HELIX EDUCATION CENTER — CONSTITUTION: the absolute
mandates and constraints that govern all development"* — which is linked from
`docs/README.md`, `docs/ARCHITECTURE.md`, `docs/ARCHITECTURE_DIAGRAM.md` and
`docs/SESSION_LOG.md`.

Both now exist: the portfolio text at the root, the project's mandate list in `docs/`.
That is a duplication the owner should settle — either the mandates move to a name that
says what they are, or this repository deliberately carries its own constitution — but
neither half may be silently rewritten, because one is the shared text and the other is
referenced from four living documents. **`docs/CONSTITUTION.md` was not touched.**

## 3. Synchronization & harmony policy

The owner's rule: **the repository's actual status must match its README at all times,
locally and remotely.**

1. `README.md` is the canonical account. `index.html` and the dashboard mirror it; they
   never fork it.
2. When reality changes, update `README.md` **first**, then mirror it to the pages.
3. Every sanctioned change is committed **and pushed** to the default branch, so the
   GitHub copy, the local working copy, and any local platform that reads the repo
   all show the same truth.
4. A number published anywhere (README, page, badge) must be reproducible from this
   repository. A stale figure is removed, not left to rot.

## 4. Archiving rule

- Archive (move to `docs/ARCHIVE/`), never delete: historical reports, superseded plans,
  dated audits, and one-off execution logs.
- Delete outright only regenerable artifacts: caches, build output, coverage files.
- Record every move in the `AGENTS.md` ledger with date and time.

## 5. Engineering philosophy & clean-code policy (operational summary)

The full text is `CONSTITUTION.md`. The operational reminders, enforced here:

- **Fail closed.** Missing input or missing authority is a refusal, never a default.
- **Evidence before claims.** Published numbers carry a command, a date, and an artifact.
- **No duplicates, no temp files, one file one job, every file explains itself.**
- **Secrets never enter the tree.**
- **Simple English** in code, docs, and UI, so a non-technical professional reader
  (recruiter, partner) can follow.
- **One brand mark:** the Helix Solutions logo, everywhere.

## 6. Definition of done

It works; it has a test or a documented manual check; the `AGENTS.md` ledger has an
entry; the docs reflect the new reality; no temporary file was left behind; and every
published number can be re-run to reproduce itself.
