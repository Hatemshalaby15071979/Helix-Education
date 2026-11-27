# AGENTS.md — Agent Charter & Ledger for Helix Education

> **Read order (mandatory, every landing):** `AGENTS.md` → `CONSTITUTION.md` →
> `GOVERNANCE.md` → `README.md`. Then **sign in** to the ledger below, do the work,
> **sign out**. No entry, no trust: an unlogged session's work is treated as unverified
> until someone checks it.

## 1. Who agents are here

An "agent" is any entity that reads or writes this repository — an AI model, an
automation script, or a human acting as operator. There is exactly **one supreme
authority**: the repository owner (**Hatem Shalaby**). An agent acts only on the
owner's instruction and records every landing.

## 2. The mandatory sign-in / sign-out rule

Every agent, on **every landing** (a landing = one session that ends with the agent
stopping, whether the task is finished or not), must:

1. **SIGN IN** before any write action — who, why, what will be touched, sensitive or
   network actions planned, and the **date and time from the system clock**.
2. **SIGN OUT** when the landing's work is complete or stopped — what changed, why,
   the files touched, evidence of verification, and **the current status when leaving**,
   written so the next agent can continue without re-discovery.

Fail closed: if a task cannot be completed, still sign out and state exactly what is
incomplete. Never claim verification that did not happen.

### Entry format

```
## [YYYY-MM-DD HH:MM TZ] — <agent name / model>
Task: <what was assigned>
Touched: <files created / modified / deleted / moved>
Why: <the reasoning, not just the diff>
Verification: <what was actually checked and the observed result>
Left undone: <what is incomplete, needs review, or is deferred — or "nothing">
Sensitive: <any remote writes, secrets, or destructive actions, or "none">
```

## 3. Environment facts

- **Repo:** Helix Education — an event-sourced learning engine with a SQLite core and sealed quiz scoring. Version 2.1.1. Two distributions ship from this repository and are versioned together.
- **Owner account:** https://github.com/Hatemshalaby15071979
- **Default branch:** main
- **Where it runs:** locally. The core has no AI dependency; a lesson can be recorded, rebuilt and scored with no model and no network. CI runs on GitHub Actions, Python 3.11–3.13.
- **Verification commands:** `ruff check .`, `python scripts/check_release.py` (version, changelog and tags must agree), `python -m compileall -q .`, `pytest -q`, and from `packages/helix-core` its own `pytest -q`. The root-document gate is `python3 scripts/check_root_docs.py` (`--self-test` proves it fails closed).
- **Two traps.** The `helix-core` suite must be run from its own directory, because two `tests` directories collide in pytest's module resolution when collected together. And `ruff` is configured to ignore `F401`, `F811`, `F821` and `F841`, so there is a separate advisory pass for those; it reports and does not fail the build.

## 4. Rules this agent must follow

- Read and obey **CONSTITUTION.md** (philosophy + clean-code policy). On conflict, it
  wins over this file.
- Follow **GOVERNANCE.md** for the repo map, documentation policy, and archiving rules.
- Keep `README.md` the single source of truth; the landing page and dashboard mirror it.
- Keep local and remote in harmony: after a sanctioned change, commit and push so the
  GitHub copy matches the working copy.
- Sign in and sign out every landing, with the real clock time.
- Never weaken the seal on a learner's record to make a test pass. If a scoring test
  fails, the code or the test is wrong — not the seal.

## 5. Ledger (sign-in / sign-out)

## [2026-11-27 05:25 EET] — sami (OpenMausBot), owner-authorised governance landing

STATUS: SIGN-IN (work in progress)

Task: Bring this repository onto the portfolio governance standard, as the owner approved in chat on 2026-11-27 ("bring the remaining eleven onto the same governance standard"). Add the missing `AGENTS.md`, `CONSTITUTION.md` and `SECURITY.md`; write the missing `GOVERNANCE.md`; move the dated remediation report out of the root; land the shared root-document gate and wire it into CI.

Touched: Will add `AGENTS.md`, `CONSTITUTION.md`, `GOVERNANCE.md`, `SECURITY.md`, `scripts/check_root_docs.py`; move `EVIDENCE_TEST_REMEDIATION.md` to `docs/ARCHIVE/`; add one job to `.github/workflows/ci.yml`. Nothing is deleted, and `CHANGELOG.md` is left untouched because `scripts/check_release.py` reads it.

Why: The repository had a changelog and a release gate but no agent charter, no portfolio constitution, no root security policy, no written policy for the root, and a dated remediation report sitting in it. `docs/CONSTITUTION.md` is a different, project-specific constitution referenced from four living documents; it is recorded in `GOVERNANCE.md` and was **not** touched.

Verification: Planned — `python3 scripts/check_root_docs.py` and `--self-test`, then `ruff check .`, `python scripts/check_release.py`, `compileall` and both pytest suites, then the GitHub Actions run on the landing commit.

Left undone: Nothing at sign-in.

Sensitive: `git push origin main` (owner's instruction in chat, 2026-11-27). No force push, no history rewrite, no secrets.
