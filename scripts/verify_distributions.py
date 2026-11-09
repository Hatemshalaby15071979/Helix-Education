"""Verify that the two distributions are actually split.

Run after building both wheels:

    python -m build --wheel --outdir dist packages/helix-core
    python -m build --wheel --outdir dist .
    python scripts/verify_distributions.py

Checks, in order:
  1. both wheels exist and there are exactly two
  2. `helix_core` requires only fastapi, pydantic and uvicorn
  3. the core wheel ships the package and no tests
  4. the `helix_education` wheel does not contain `helix_core/`
  5. the `helix-core` entry point moved to the core wheel
  6. neither wheel contains `__pycache__` or `.pyc` files

Exit code 0 = clean, 1 = at least one violation.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

DIST = Path("dist")

CORE_REQUIREMENTS = {"fastapi", "pydantic", "uvicorn"}
HEAVY_DEPS = {"ollama", "requests", "beautifulsoup4", "cryptography"}

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


def _wheel(prefix: str) -> Path | None:
    matches = sorted(DIST.glob(f"{prefix}-*.whl"))
    if len(matches) != 1:
        fail(f"expected exactly one {prefix} wheel in {DIST}/, found {len(matches)}")
        return None
    return matches[0]


def _metadata(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
        return zf.read(name).decode("utf-8")


def _names(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        return zf.namelist()


def _entry_points(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as zf:
        for name in zf.namelist():
            if name.endswith(".dist-info/entry_points.txt"):
                return zf.read(name).decode("utf-8")
    return ""


def _requirements(metadata: str) -> set[str]:
    """Return bare requirement names from Requires-Dist lines.

    Optional dependencies carry an `extra == "..."` marker and are skipped —
    they are not installed by default and are not what this check is about.
    """
    names: set[str] = set()
    for line in metadata.splitlines():
        if not line.startswith("Requires-Dist:"):
            continue
        spec = line.split(":", 1)[1].strip()
        if "extra ==" in spec:
            continue
        name = spec.split(";", 1)[0].strip()
        for sep in ("[", " ", "=", "<", ">", "!", "~"):
            name = name.split(sep, 1)[0]
        names.add(name.lower())
    return names


def main() -> int:
    if not DIST.is_dir():
        fail(f"{DIST}/ does not exist — build the wheels first")
        _report()
        return 1

    wheels = sorted(DIST.glob("*.whl"))
    if len(wheels) != 2:
        fail(f"expected 2 wheels in {DIST}/, found {len(wheels)}: {[w.name for w in wheels]}")

    core = _wheel("helix_core")
    education = _wheel("helix_education")

    if core:
        meta = _metadata(core)
        reqs = _requirements(meta)
        extra = reqs - CORE_REQUIREMENTS
        if extra:
            fail(f"{core.name} requires {sorted(extra)}; expected only {sorted(CORE_REQUIREMENTS)}")
        heavy = reqs & HEAVY_DEPS
        if heavy:
            fail(f"{core.name} pulls heavy dependencies {sorted(heavy)}")

        names = _names(core)
        if not any(n.startswith("helix_core/") and n.endswith(".py") for n in names):
            fail(f"{core.name} does not contain the helix_core package")
        if any("/tests/" in n for n in names):
            fail(f"{core.name} ships tests")
        if any("__pycache__" in n or n.endswith(".pyc") for n in names):
            fail(f"{core.name} contains bytecode caches")

        if "helix-core" not in _entry_points(core):
            fail(f"{core.name} does not declare the helix-core entry point")

    if education:
        names = _names(education)
        if any(n.startswith("helix_core/") for n in names):
            fail(f"{education.name} still bundles helix_core/")
        if any("__pycache__" in n or n.endswith(".pyc") for n in names):
            fail(f"{education.name} contains bytecode caches")

        if "helix-core" in _entry_points(education):
            fail(f"{education.name} still declares the helix-core entry point")

    _report()
    return 0 if not failures else 1


def _report() -> None:
    if not failures:
        print("DISTRIBUTIONS OK: helix-core and helix-education are cleanly split")
        return
    print(f"DISTRIBUTIONS FAIL: {len(failures)} problem(s)")
    for f in failures:
        print(f"  - {f}")


if __name__ == "__main__":
    sys.exit(main())
