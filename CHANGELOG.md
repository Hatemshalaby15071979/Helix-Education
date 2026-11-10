# Changelog

All notable changes to Helix Education are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Two distributions ship from this repository and are versioned together:

- **`helix-core`** (`packages/helix-core/`) — the sealed quiz scoring
  service and the append-only SQLite event store. This is what the Study
  Studio desktop app runs as a sidecar.
- **`helix-education`** (the repository root) — the wider learning engine:
  content generation, adaptive paths, projections and the API layer.

## [2.1.1] - 2026-11-10

### Fixed
- **The frozen sidecar outlived the shell that spawned it.** A PyInstaller
  one-file bundle is a bootloader process plus a worker that runs the
  application, and killing the bootloader does not kill the worker. The
  worker then kept serving — holding the port, the SQLite database and the
  bearer token — after the desktop app that owned them had exited.
  Reproduced with the built sidecar on Linux: after killing the parent,
  the worker was still answering `/v1/health` 30 seconds later.

  In `--handshake` mode the core now arms a parent-death watchdog:
  `prctl(PR_SET_PDEATHSIG)` on POSIX, and a wait on the parent process
  handle on Windows. The watchdog is armed only in handshake mode, which
  is the mode that exists for a parent that owns the core; a standalone
  server keeps its ordinary lifetime. If the watchdog cannot be
  installed, the core behaves exactly as it did before.

### Added
- A `CHANGELOG.md`, so the two distributions' versions and the git tags
  can be checked against each other rather than assumed to agree.
- A coverage floor for the root package, and a release-consistency check
  that fails when the version, this file and the tags disagree.

## [2.1.0] - 2026-11-09

### Added
- **`--handshake` mode for the core.** `helix-core --port 0 --handshake`
  binds its own socket, prints one JSON line
  `{"event":"ready","port":N,"token":"..."}` and then serves. The desktop
  shell reads that line to learn the port and the bearer token, neither of
  which it can know in advance. The token is generated per launch and is
  never written to disk.
- **`helix-core` as its own distribution** (`packages/helix-core/`). The
  core ships as a separate wheel with only three dependencies —
  fastapi, pydantic and uvicorn. The parent package keeps the heavier
  runtime dependencies and does not import the core.
- **A container image and single-replica Kubernetes manifests** for the
  core, built from `packages/helix-core` and published to GHCR.
- **CI gates for test, lint, compile and bandit**, run on Python 3.11,
  3.12 and 3.13.

### Changed
- The core's SQLite event store and sealed scoring engine were extracted
  from the parent package into `packages/helix-core`, with the answer key
  held in a separate table and verified against an HMAC before every
  score. A key edited on disk fails verification and the core refuses to
  score rather than scoring against the wrong answer.
- The parent package no longer depends on a repository-root sealed-key
  file; the key store lives in the per-user data directory.

### Fixed
- **The GHCR image name is lowercased.** GHCR rejects an uppercase
  repository name, and the GitHub owner is `Hatemshalaby15071979`.

## [1.1.0] - 2026-08-29

### Changed
- Aligned the package version with the release and declared the runtime
  dependencies explicitly, so an install does not depend on what happens
  to be present on the machine.

### Added
- Setup scripts for the local development environment.

## [1.0.0] - 2026-08-27

### Added
- The first public release of Helix Education: the event-sourced learning
  engine, with a replayable append-only event log, citation-grounded
  content generation, and sealed quiz scoring.

[2.1.1]: https://github.com/Hatemshalaby15071979/Helix-Education/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/Hatemshalaby15071979/Helix-Education/compare/v1.1.0...v2.1.0
[1.1.0]: https://github.com/Hatemshalaby15071979/Helix-Education/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Hatemshalaby15071979/Helix-Education/releases/tag/v1.0.0
