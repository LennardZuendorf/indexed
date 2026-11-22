#!/usr/bin/env python3
"""Fail when the spec root drifts from ``docs/spec``.

The installed spec skill names ``docs/spec`` and falls back to a legacy flat
root when it is absent, so a repo that never moved stayed green. This gate makes
the root explicit: ``docs/spec`` must exist with the core specs, the legacy
dot-directory must be gone, and no tracked file may point back at it.

Pinned data is exempt: those bytes are hash-locked and record what the tree
looked like at the revision they were captured from, so rewriting them would
move a baseline rather than fix a reference.

    uv run python scripts/check_spec_root.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SPEC_ROOT = "docs/spec"
LEGACY_ROOT = ".spec"
REQUIRED = ("product.md", "plan.md", "tech.md", "lessons.md")

#: Hash-locked captures of the pre-move tree (eval corpus + manifests, benchmark
#: corpus). Editing them changes their sha256, i.e. the measurement.
PINNED = (
    "eval/corpus/",
    "eval/corpus.json",
    "eval/baseline.json",
    "eval/rerank-baseline.json",
    "tests/benchmarks/fixtures/parsing_corpus/",
)

#: This gate and its test name the legacy root on purpose.
SELF = ("scripts/check_spec_root.py", "tests/unit/test_check_spec_root.py")

_LEGACY_REF = re.compile(r"(?<![\w.])\.spec(?![\w-])")


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8", "surrogateescape")
    return [name for name in out.split("\0") if name]


def check(root: Path, files: list[str]) -> list[str]:
    """Return one message per violation; empty means the root is sound."""
    problems: list[str] = []
    spec = root / SPEC_ROOT
    if not spec.is_dir():
        problems.append(f"{SPEC_ROOT}/ does not exist")
    else:
        problems.extend(
            f"{SPEC_ROOT}/{name} is missing"
            for name in REQUIRED
            if not (spec / name).is_file()
        )
    if (root / LEGACY_ROOT).exists():
        problems.append(f"legacy {LEGACY_ROOT}/ still exists; it moved to {SPEC_ROOT}/")
    for name in files:
        if name.startswith(f"{LEGACY_ROOT}/"):
            problems.append(f"{name}: tracked under the legacy root")
        elif name.startswith(PINNED) or name in SELF:
            continue
        else:
            path = root / name
            if path.is_symlink() or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if _LEGACY_REF.search(line):
                    problems.append(
                        f"{name}:{number}: names {LEGACY_ROOT}; use {SPEC_ROOT}"
                    )
    return problems


def main() -> int:
    problems = check(ROOT, tracked_files(ROOT))
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"spec root check FAILED ({len(problems)} problem(s))", file=sys.stderr)
        return 1
    print(f"spec root OK: {SPEC_ROOT}/ present, {LEGACY_ROOT}/ absent and unreferenced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
