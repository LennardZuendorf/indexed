#!/usr/bin/env python3
"""Structural + anti-regrowth size gate for the single ``indexed`` package.

Catches monorepo regrowth after the simplify collapse: a second package dir,
a second AGENTS.md, a second pyproject.toml (or ``una`` sneaking back in), or
src/test LOC creeping back toward the old 7-package scale. The LOC ceilings
are current measured size + headroom (~21.4k src / ~27.7k tests today) — NOT
the simplify feature's aspirational ~6k/~8k targets, which are out of reach
without a v2 rewrite or removing shipped functionality (both out of scope).
This script only guards against regression, it does not chase that target.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SRC_LOC_MAX = 23_300
# Raised from 23_000 by core-v2/2a, which adds the v2 manifest/config-model/
# adapter package (`core/v2/{__init__,manifest,config_models,adapter}.py`) —
# genuine new-feature surface (pre-approved in `.spec/lessons.md`'s v1 surface
# map note), not stealth regrowth; ceiling = measured (23_179) + headroom.
# Raised from 29_000 after the review-remediation feature added ~90 red->green
# regression tests (one per confirmed PR #155 defect). That is legitimate
# defect-guarding coverage, not stealth regrowth; ceiling = measured + headroom.
TEST_LOC_MAX = 32_500
AGENTS_MD_MAX_LINES = 100

_IGNORED_PARTS = frozenset({".venv", "node_modules", "__pycache__"})


def _count_loc(base: Path) -> int:
    if not base.is_dir():
        return 0
    total = 0
    for path in base.rglob("*.py"):
        if _IGNORED_PARTS & set(path.parts):
            continue
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            total += sum(1 for _ in fh)
    return total


def _repo_files(pattern: str) -> list[Path]:
    return [p for p in ROOT.rglob(pattern) if not (_IGNORED_PARTS & set(p.parts))]


def check() -> tuple[list[str], list[str]]:
    """Return (violations, measurements) — measurements always printed."""
    violations: list[str] = []
    measurements: list[str] = []

    # One package dir: src/indexed/, no packages/, no apps/.
    src_dir = ROOT / "src"
    package_dirs = (
        sorted(p.name for p in src_dir.iterdir() if p.is_dir())
        if src_dir.is_dir()
        else []
    )
    measurements.append(f"src/ package dirs: {package_dirs}")
    if package_dirs != ["indexed"]:
        violations.append(
            f"src/ must contain exactly one package dir 'indexed', found {package_dirs}"
        )
    for stale in ("packages", "apps"):
        if (ROOT / stale).is_dir():
            violations.append(
                f"'{stale}/' must not exist (monorepo collapsed to one package)"
            )

    # One real AGENTS.md at root, <=100 lines.
    agents_files = [p for p in _repo_files("AGENTS.md") if not p.is_symlink()]
    measurements.append(
        f"AGENTS.md files: {[str(p.relative_to(ROOT)) for p in agents_files]}"
    )
    if agents_files != [ROOT / "AGENTS.md"]:
        violations.append(
            f"expected exactly one real AGENTS.md at root, found {[str(p) for p in agents_files]}"
        )
    else:
        agents_lines = sum(1 for _ in (ROOT / "AGENTS.md").open(encoding="utf-8"))
        measurements.append(f"AGENTS.md lines: {agents_lines}")
        if agents_lines > AGENTS_MD_MAX_LINES:
            violations.append(
                f"AGENTS.md is {agents_lines} lines, max {AGENTS_MD_MAX_LINES}"
            )

    # One pyproject.toml (excluding .venv); no [tool.una].
    pyprojects = _repo_files("pyproject.toml")
    measurements.append(
        f"pyproject.toml files: {[str(p.relative_to(ROOT)) for p in pyprojects]}"
    )
    if pyprojects != [ROOT / "pyproject.toml"]:
        violations.append(
            f"expected exactly one pyproject.toml, found {[str(p) for p in pyprojects]}"
        )
    root_pyproject = ROOT / "pyproject.toml"
    if root_pyproject.is_file():
        text = root_pyproject.read_text(encoding="utf-8")
        if "[tool.una]" in text:
            violations.append(
                "pyproject.toml still declares [tool.una] (workspace apparatus)"
            )

    # Src / test LOC ceilings (anti-regrowth headroom, not the fantasy target).
    src_loc = _count_loc(ROOT / "src" / "indexed")
    test_loc = _count_loc(ROOT / "tests")
    measurements.append(f"src/indexed LOC: {src_loc} (max {SRC_LOC_MAX})")
    measurements.append(f"tests LOC: {test_loc} (max {TEST_LOC_MAX})")
    if src_loc > SRC_LOC_MAX:
        violations.append(f"src/indexed LOC {src_loc} exceeds ceiling {SRC_LOC_MAX}")
    if test_loc > TEST_LOC_MAX:
        violations.append(f"tests LOC {test_loc} exceeds ceiling {TEST_LOC_MAX}")

    return violations, measurements


def main(argv: list[str]) -> int:
    del argv
    violations, measurements = check()
    print("Size gate measurements:")
    for line in measurements:
        print(f"  {line}")
    if violations:
        print("\nSize gate violations:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print("\nSize gate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
