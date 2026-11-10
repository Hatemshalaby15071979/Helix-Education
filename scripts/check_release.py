"""Check that the version, the CHANGELOG and the git tags agree.

A release is only real if the same version appears in four places:

  1. the version manifests
  2. the CHANGELOG
  3. a git tag
  4. the published distribution

This script checks the parts it can check locally -- the manifests, the
CHANGELOG and the tags -- and states the rest. It exits non-zero when
the repository is in a state that would make a release lie about what it
contains.

Usage: python scripts/check_release.py
Exits 0 when consistent, 1 otherwise.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "packages" / "helix-core"

# Tags that exist in this repository but do not correspond to a release.
#
# Each entry says what the tag actually is. These are not exceptions to
# hide behind -- they are history that the CHANGELOG cannot describe,
# because it describes releases, and a release is a version plus a tag.
#
# v1.0.0 -- the tree it points at declared version 2.0.0 in its
#   manifests, so the tag name never matched the code it marked. The
#   CHANGELOG records 1.0.0 as the first release, so the entry exists;
#   this entry records the mismatch rather than hiding it.
LEGACY_TAGS: dict[str, str] = {
    "v1.0.0": "the tree it points at declared 2.0.0, so the tag name never matched the code it marked",
}

# Released versions in the CHANGELOG that were never tagged.
UNTAGGED_RELEASES: dict[str, str] = {}

# The version the manifests declare.
ROOT_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
CORE_VERSION = tomllib.loads((CORE / "pyproject.toml").read_text())["project"]["version"]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def main() -> int:
    problems: list[str] = []

    # ── the manifests ───────────────────────────────────────────────────
    if ROOT_VERSION != CORE_VERSION:
        problems.append(
            f"the root package declares {ROOT_VERSION} but helix-core declares {CORE_VERSION}. "
            "They ship together and must be the same version."
        )

    # The package's own __version__ and the version the API reports.
    init_version = re.search(
        r'^__version__ = "([^"]+)"', (CORE / "helix_core" / "__init__.py").read_text(), re.M
    )
    if init_version and init_version.group(1) != CORE_VERSION:
        problems.append(
            f"helix_core.__version__ is {init_version.group(1)} but the package declares {CORE_VERSION}."
        )

    api_version = re.search(
        r'version: str = "([^"]+)"', (CORE / "helix_core" / "api.py").read_text()
    )
    if api_version and api_version.group(1) != CORE_VERSION:
        problems.append(
            f"the API reports version {api_version.group(1)} but the package declares {CORE_VERSION}."
        )

    # ── the CHANGELOG ───────────────────────────────────────────────────
    changelog_path = ROOT / "CHANGELOG.md"
    if not changelog_path.exists():
        print("check:release — no CHANGELOG.md", file=sys.stderr)
        return 1
    changelog = changelog_path.read_text()

    sections: list[tuple[str, bool]] = []
    for match in re.finditer(r"^## \[([^\]]+)\][^\n]*$", changelog, re.M):
        heading = match.group(0)
        released = "Unreleased" not in heading
        sections.append((match.group(1), released))

    if not sections:
        print("check:release — the CHANGELOG has no version sections", file=sys.stderr)
        return 1

    top, top_released = sections[0]

    # The version being prepared must be the one the manifests declare.
    if top != ROOT_VERSION:
        problems.append(
            f"the top CHANGELOG entry is {top} but the manifests declare {ROOT_VERSION}. "
            "The version being prepared must be the one the manifests declare."
        )

    if top_released and top != ROOT_VERSION:
        problems.append(
            f"the CHANGELOG's top entry {top} is marked released, but the manifests declare "
            f"{ROOT_VERSION}. A released version cannot be changed after the fact."
        )

    # ── the tags ─────────────────────────────────────────────────────────
    # A shallow clone has no tags, and "this release was never tagged"
    # would be the wrong conclusion from it. Detect it and say so, rather
    # than reporting a false problem for every release.
    if git("rev-parse", "--is-shallow-repository") == "true":
        print(
            "check:release — this is a shallow clone, so the tags are not available.\n"
            "              Fetch the history (`git fetch --unshallow`) and run this again.",
            file=sys.stderr,
        )
        return 1

    tags = [t for t in git("tag", "--list").split("\n") if t]
    tagged_versions = {t.lstrip("v") for t in tags}

    for version, released in sections:
        if not released:
            # An unreleased section must not have a tag yet: the tag is
            # created when the release is cut.
            if version in tagged_versions:
                problems.append(
                    f"the CHANGELOG records {version} as unreleased, but there is a v{version} tag. "
                    "Either the release was cut — mark it released — or the tag was made by mistake."
                )
            continue
        if version in tagged_versions or version in UNTAGGED_RELEASES:
            continue
        problems.append(
            f"the CHANGELOG records {version} as released but there is no v{version} tag. "
            "Either tag the release or record the gap."
        )

    for tag in tags:
        version = tag.lstrip("v")
        if tag in LEGACY_TAGS:
            continue
        if version in {v for v, _ in sections}:
            continue
        problems.append(
            f"the tag {tag} has no CHANGELOG entry. A tag without a changelog entry is a "
            "release nobody can find out about."
        )

    # ── the report ───────────────────────────────────────────────────────
    print(f"  root package      {ROOT_VERSION}")
    print(f"  helix-core        {CORE_VERSION}")
    print(f"  changelog top     {top}{'' if top_released else ' (unreleased — no tag yet)'}")
    print(f"  tags              {', '.join(tags) or '(none)'}")

    if not top_released:
        print(f"                    the {top} tag is created when the release is cut: git tag v{top}")

    for tag, why in LEGACY_TAGS.items():
        if tag in tags:
            print(f"  legacy tag        {tag} — {why}")
    for version, why in UNTAGGED_RELEASES.items():
        if version in {v for v, _ in sections}:
            print(f"  untagged release  {version} — {why}")

    if problems:
        for problem in problems:
            print(f"\n  - {problem}", file=sys.stderr)
        print(f"\ncheck:release — {len(problems)} problem(s).", file=sys.stderr)
        return 1

    print("\ncheck:release — OK. The manifests, the CHANGELOG and the tags agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
