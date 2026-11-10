# Shipment-gate pre-registrations

These are the decisions that were written down **before** the measurements that
would justify them. Hatem's operating rules put new CI jobs, new coverage
thresholds and new dependencies in a zone that requires a written
pre-registration first: hypothesis, metric, accept rule, reject rule. This
file is that pre-registration for the shipment-readiness work on this branch.

Nothing here is a target to be hit after the fact. Each item states what
would make it wrong.

**Branch:** `chore/shipment-readiness`
**Base commit:** `608fa1a` (main)

---

## PR-1 — A CI job that builds the packaged desktop app

**What is proposed.** A new workflow, `.github/workflows/tauri-build.yml`, with
two jobs:

- `tauri-build-windows` on `windows-latest`: checks out Helix-Education at the
  tag `v2.1.0`, builds the `helix-core` sidecar with
  `scripts/build-sidecar.mjs`, then runs `npm run tauri:build` and asserts that
  both an NSIS installer and an MSI installer were produced.
- `tauri-build-linux` on `ubuntu-latest`: the same sidecar build for the Linux
  triple, then `cargo test` (which includes the cross-repo contract test) and
  `npm run tauri:build`.

**Hypothesis.** The packaged desktop build is currently unprovable by CI, so a
packaging break — a missing sidecar, a wrong bundle target, a broken
`beforeBuildCommand` — is invisible until someone tries to ship. If the job
runs the real packaging command on a runner that has first built the real
sidecar, that class of break becomes a red check instead of a surprise.

**Metric.** Exit status of `npm run tauri:build`, and the existence of the
installer files under `src-tauri/target/release/bundle/`.

**Data split.** Not a measurement — this is a gate, not an experiment. There
is no tuning set and no reporting set; every run either passes or fails.

**Seeds.** None. The build is deterministic given the pinned inputs
(Helix-Education tag `v2.1.0`, the lockfiles in this repository).

**Accept rule.** The job passes when `npm run tauri:build` exits 0 **and** the
Windows job finds both `*.exe` (NSIS) and `*.msi` (MSI) in the bundle
directory. A build that exits 0 without producing installers is a failure, not
a pass — that is the specific case this job exists to catch.

**Reject rule.** If the job cannot be made to pass on a clean runner for a
reason that is not a defect in the repository — for example the runner image
cannot run the packaging toolchain — then the job is wrong, not the
repository. It must be fixed or removed, never weakened by removing the
installer assertions.

**Known limitation, recorded before measuring.** The NSIS and MSI installers
are Windows-only bundle targets. On Linux, `tauri build` exits 0 and produces
no installer at all. That is a property of the tool, not of this repository,
and it is the reason the Windows job exists as a separate job rather than one
job that pretends to cover both platforms.

---

## PR-2 — Secret scanning over the whole history

**What is proposed.** A `gitleaks` scan of the working tree and the full git
history, on every push, in both repositories.

**Hypothesis.** A secret committed once and later deleted is still in the
history and still leaks. A scan of the working tree alone cannot see it, so
the working tree alone is not a sufficient gate.

**Metric.** `gitleaks` exit status: 0 means no findings, non-zero means
findings.

**Data split.** Not a measurement — a gate over the entire history, every
commit.

**Seeds.** None.

**Accept rule.** The scan exits 0 on the current history of both
repositories.

**Reject rule.** If the scan finds a real secret, that is a hard stop
(§6.6: secret exposure). Fix it by rotating the credential and rewriting the
offending history, and stop the shipment until it is done. The scan is never
loosened, never given an ignore rule for a finding that looks like a real
credential, and never disabled to make the pipeline green.

---

## PR-3 — A coverage floor for Helix-Education

**What is proposed.** `pytest-cov` with a floor on total statement coverage,
run in CI alongside the existing pytest job.

**Hypothesis.** The Helix-Education suite has 465 passing tests but no
coverage floor, so coverage can fall for a long time without anything going
red — the exact failure mode the Study-Studio repository already guards
against with `scripts/check-coverage.mjs`. A floor makes the next silent
regression loud.

**Metric.** Total statement coverage, as reported by `pytest --cov` over the
root package's `testpaths` (`tests/`).

**Data split.** Not a measurement — a single number over the whole suite, the
same number on every run.

**Seeds.** None; the suite is deterministic.

**Accept rule.** The floor is set at the measured baseline, rounded down to
the nearest whole percent, so the first run of the gate is green by
construction and any later drop below it is red.

**Reject rule.** If the measured baseline is so low that a meaningful floor
cannot be set, the floor is set at the measured value regardless — a low floor
is honest, a flattering one is not. The floor may be raised later. It may
never be lowered after a result is seen.

---

## PR-4 — Tag-gated publish workflows

**What is proposed.** In Helix-Education, a PyPI publish workflow triggered
only by a `v*` tag, and the existing GHCR publish step in `docker.yml`
narrowed from "every push to main" to "version tags only".

**Hypothesis.** A publish workflow that fires on every push can publish a
build nobody intended to release, and a publish workflow that is not wired to
a tag at all has no defined release moment. Both are fixed by gating on the
tag, which is the moment a release is actually declared.

**Metric.** Not a measurement — a switch. The publish steps either run (on a
tag, with the credentials present) or they do not.

**Data split.** None.

**Seeds.** None.

**Accept rule.** The workflow files exist, are gated on a tag, and the publish
steps are gated on the credential being present, so that pushing to a branch
never publishes anything.

**Reject rule.** The publish workflows must not be left in a state where
pushing a branch uploads an artefact to PyPI or pushes an image to GHCR.
Publishing itself stays parked with the owner: no upload and no push happens
as part of this work, whatever the workflow files say.

---

## PR-5 — CI on every branch push

**What is proposed.** The Helix-Education CI workflow triggers on every
branch push rather than only on `main` and `master`.

**Hypothesis.** A workflow limited to `main` cannot be exercised on a
topic branch at all, so a change is only verifiable after it has landed.
That is the same reasoning the Study-Studio repository already acts on: its
CI workflow runs on every push, and its comment says why — "a workflow
limited to `main` cannot be exercised on a topic branch at all (verified
2026-10-01). Running on every push makes a branch verifiable before it
reaches `main`."

Without this, a gate added to a branch — the coverage floor, the release
consistency check — would not actually run until after it was merged, which
is the point at which a gate is least useful.

**Metric.** Not a measurement — a trigger. The workflow either runs for a
push to a branch or it does not.

**Data split.** None.

**Seeds.** None.

**Accept rule.** A push to any branch runs the full gate set: the test
suite on every supported Python version, the coverage floor, ruff, bandit,
and the distribution build check.

**Reject rule.** If the workflow becomes slow enough that branches stop
being verified — the failure mode of running everything on every push — then
the fix is to make the suite faster or to split the jobs, not to narrow the
trigger back to `main`. Narrowing the trigger silently restores the gap
this change closes.

The container workflow is scoped the same way, but for a different reason:
it builds an image, and building an image on every branch push costs
runner minutes without proving anything a branch cannot prove. It keeps its
`paths` filter, so it runs when the core, the Dockerfile or the workflow
itself changes.

---

## PR-6 — A release-consistency check

**What is proposed.** A check in each repository that fails when the
version in the manifests, the CHANGELOG and the git tags do not describe
the same release.

**Hypothesis.** Study-Studio already had `check:versions`, which compares
the four manifests against each other. It cannot see the CHANGELOG or the
tags, so a version could be bumped in the manifests while the CHANGELOG
still described the previous release, and the check would pass. The
Helix-Education repository had no check at all: two packages that ship
together could declare different versions, and nothing would notice.

**Metric.** The exit status of the check: 0 when the version, the CHANGELOG
and the tags agree, 1 when they do not.

**Data split.** Not a measurement — a gate over the whole repository state.

**Seeds.** None.

**Accept rule.** The check passes on the current repositories, and the
version, the CHANGELOG's newest section and the tag set describe one
release.

**Reject rule.** The check must not be weakened to accommodate a
disagreement it finds. Either the manifests, the CHANGELOG or the tags are
wrong, and the right one is fixed — the check is not edited to make the
disagreement go away. The one exception is a historical gap that cannot be
fixed without rewriting history (a release that was never tagged); those
are listed explicitly in the check with the reason, so they are visible
rather than silent.
