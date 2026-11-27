# Security Policy

Helix Education is a learning engine that keeps a learner's record as evidence: it
records what a person learns as a chain of events, rebuilds their progress from that
chain, and scores quizzes in a way that cannot be silently edited afterwards. It runs
locally. The core has no AI dependency, so a lesson can be recorded, rebuilt and scored
with no model, no network and no account.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 2.1.1   | Yes — the current release. |
| 2.1.0   | Superseded by 2.1.1; no separate fixes. |

`CHANGELOG.md` is the release record, and `scripts/check_release.py` asserts that the
version in the manifests, the changelog and the git tags describe the same release.

## Design commitments that are security-relevant

- **The record is sealed.** A score that could be quietly changed after the fact would
  make the whole record worthless. Anything that weakens the seal — a mutable score, a
  chain edit, a rebuild that ignores the event log — is a security change, not a
  feature, and must be treated as one.
- **Local by default, no account.** The evidence path holds no credentials and needs no
  network. There is no telemetry.
- **Secrets never enter the tree.** Keys live outside the repository, in a git-ignored
  source, never in code or commits.
- **Honest about limits.** Where data is simulated it is labelled, and no production
  claim is made from a fixture.

## Reporting a vulnerability

**Reporting contact: to be set by the owner.** There is no monitored security mailbox or
private reporting channel in this repository yet; do not send vulnerability reports to
any address guessed from this file.

Until the owner publishes a contact channel:

1. Do not open a public issue containing exploit details.
2. Do not include real learner data, credentials or personal data in any report.
3. The owner will add a private reporting channel (for example GitHub Private
   Vulnerability Reporting) and this section will name it.
