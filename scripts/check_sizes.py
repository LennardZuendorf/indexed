#!/usr/bin/env python3
"""Structural + anti-regrowth size gate for the single ``indexed`` package.

Catches monorepo regrowth after the simplify collapse: a second package dir,
a second AGENTS.md, a second pyproject.toml (or ``una`` sneaking back in), or
src/test LOC creeping back. This script only guards against regression, it does
not chase the simplify feature's aspirational ~6k/~8k targets, which are out of
reach without a v2 rewrite or removing shipped functionality (both out of scope).

Two LOC modes:

``--baseline-ref <ref>`` (what CI runs)
    Measure the *growth* this branch introduces: ``measured(HEAD) <=
    measured(<ref>) + GROWTH_ALLOWANCE``, per bucket (``src/indexed`` and
    ``tests``). Nothing shared is edited, so two branches that each add tests
    can no longer conflict on a ceiling — and the verdict is a function of the
    branch alone rather than of how much slack an unrelated merge left behind.

no argument (legacy, offline)
    Compare against the absolute ``SRC_LOC_MAX`` / ``TEST_LOC_MAX`` constants.
    Kept so the script still runs in a bare copy of the tree, and because it is
    the hard ratchet of record for an offline reader. CI no longer enforces
    these, so no branch needs to edit them; prefer the baseline mode locally
    (``uv run python scripts/check_sizes.py --baseline-ref origin/main``).

The lineage of the absolute ceilings lives in the git history of this file
(each bump carried the measured size and its justification).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Legacy offline ceilings — current `main` values (src 36_4xx / tests 58_9xx after
#: the git-aware and LSP tiers landed), plus headroom for this PR's own
#: `tests/unit/test_check_sizes.py`. CI enforces growth against the merge base
#: instead (--baseline-ref), so this line is no longer a per-branch edit — see
#: GROWTH_ALLOWANCE.
SRC_LOC_MAX = 36_400
TEST_LOC_MAX = 59_400

#: Baseline-mode growth allowance per bucket, in lines. Rule: the largest
#: per-commit growth on main's 40 first-parent commits before 2026-11-15
#: (+2_573 tests / +1_956 src, both feat(eval)'s retrieval harness, #265), plus
#: ~25 % margin, rounded up to the next hundred. Growth beyond it means the
#: branch is bigger than any single reviewed unit this repo has landed — split
#: it, or trim boilerplate first, rather than raising the number. A stack whose
#: branches land in order is measured one branch at a time; a stack merged as
#: one unit (tier-1 LSP evidence: +7_899 tests over main) is exactly what this
#: refuses.
GROWTH_ALLOWANCE = {"src": 2_500, "tests": 3_300}

AGENTS_MD_MAX_LINES = 100

_IGNORED_PARTS = frozenset({".venv", "node_modules", "__pycache__"})


class SizeGateError(RuntimeError):
    """The gate could not reach a verdict (git missing, ref unresolvable)."""


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


def _repo_files(root: Path, pattern: str) -> list[Path]:
    return [p for p in root.rglob(pattern) if not (_IGNORED_PARTS & set(p.parts))]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        lines = (result.stderr or result.stdout).strip().splitlines()
        message = lines[-1] if lines else "no output"
        raise SizeGateError(f"git {args[0]}: {message}")
    return result.stdout


def _resolve_tree(root: Path, ref: str) -> None:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "rev-parse",
            "--verify",
            "--quiet",
            f"{ref}^{{tree}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return
    if "not a git repository" in (result.stderr or ""):
        raise SizeGateError(
            f"{root} is not a git repository; --baseline-ref needs git history"
        )
    raise SizeGateError(
        f"baseline ref {ref!r} is not a tree in {root} "
        "(fetch full history, or omit --baseline-ref for the absolute ceilings)"
    )


def _blob_lines(blob: bytes) -> int:
    # Same count as iterating a text file: a final line without a newline counts.
    return blob.count(b"\n") + (1 if blob and not blob.endswith(b"\n") else 0)


def _baseline_loc(root: Path, ref: str) -> tuple[int, int]:
    """(src/indexed, tests) LOC of the tracked ``.py`` files in ``ref``."""
    _resolve_tree(root, ref)
    listing = _git(root, "ls-tree", "-r", "-z", ref, "--", "src/indexed", "tests")
    entries: list[tuple[str, str]] = []
    for record in listing.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        fields = meta.split()
        if len(fields) == 3 and fields[1] == "blob" and path.endswith(".py"):
            entries.append((path, fields[2]))
    if not entries:
        return 0, 0

    # One process for every blob: `cat-file --batch` answers
    # "<oid> blob <size>\n<content>\n" per requested object, in order.
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch"],
        input="".join(f"{sha}\n" for _, sha in entries).encode(),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        lines = (result.stderr or b"").decode(errors="replace").strip().splitlines()
        message = lines[-1] if lines else "failed to read the baseline blobs"
        raise SizeGateError(f"git cat-file: {message}")

    data = result.stdout
    position = 0
    totals = {"src": 0, "tests": 0}
    for path, _sha in entries:
        eol = data.index(b"\n", position)
        size = int(data[position:eol].split()[2])
        blob = data[eol + 1 : eol + 1 + size]
        position = eol + 1 + size + 1
        totals["src" if path.startswith("src/") else "tests"] += _blob_lines(blob)
    return totals["src"], totals["tests"]


def check(
    root: Path = ROOT, baseline_ref: str | None = None
) -> tuple[list[str], list[str]]:
    """Return (violations, measurements) — measurements always printed."""
    violations: list[str] = []
    measurements: list[str] = []

    # One package dir: src/indexed/, no packages/, no apps/.
    src_dir = root / "src"
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
        if (root / stale).is_dir():
            violations.append(
                f"'{stale}/' must not exist (monorepo collapsed to one package)"
            )

    # One real AGENTS.md at root, <=100 lines.
    agents_files = [p for p in _repo_files(root, "AGENTS.md") if not p.is_symlink()]
    measurements.append(
        f"AGENTS.md files: {[str(p.relative_to(root)) for p in agents_files]}"
    )
    if agents_files != [root / "AGENTS.md"]:
        violations.append(
            f"expected exactly one real AGENTS.md at root, found {[str(p) for p in agents_files]}"
        )
    else:
        agents_lines = sum(1 for _ in (root / "AGENTS.md").open(encoding="utf-8"))
        measurements.append(f"AGENTS.md lines: {agents_lines}")
        if agents_lines > AGENTS_MD_MAX_LINES:
            violations.append(
                f"AGENTS.md is {agents_lines} lines, max {AGENTS_MD_MAX_LINES}"
            )

    # One pyproject.toml (excluding .venv); no [tool.una].
    pyprojects = _repo_files(root, "pyproject.toml")
    measurements.append(
        f"pyproject.toml files: {[str(p.relative_to(root)) for p in pyprojects]}"
    )
    if pyprojects != [root / "pyproject.toml"]:
        violations.append(
            f"expected exactly one pyproject.toml, found {[str(p) for p in pyprojects]}"
        )
    root_pyproject = root / "pyproject.toml"
    if root_pyproject.is_file():
        text = root_pyproject.read_text(encoding="utf-8")
        if "[tool.una]" in text:
            violations.append(
                "pyproject.toml still declares [tool.una] (workspace apparatus)"
            )

    # Src / test LOC: growth against a baseline ref, else absolute ceilings.
    src_loc = _count_loc(root / "src" / "indexed")
    test_loc = _count_loc(root / "tests")
    if baseline_ref is None:
        measurements.append("LOC mode: absolute ceilings (legacy offline fallback)")
        measurements.append(f"src/indexed LOC: {src_loc} (max {SRC_LOC_MAX})")
        measurements.append(f"tests LOC: {test_loc} (max {TEST_LOC_MAX})")
        # Guidance, not a new rule: these constants ratchet main, they are not a
        # per-branch number, so a branch that trips them re-measures instead.
        hint = (
            " (offline ratchet of record, not a per-branch number: on a branch run"
            " --baseline-ref origin/main instead of raising it; raise only when"
            " main itself grew)"
        )
        if src_loc > SRC_LOC_MAX:
            violations.append(
                f"src/indexed LOC {src_loc} exceeds ceiling {SRC_LOC_MAX}{hint}"
            )
        if test_loc > TEST_LOC_MAX:
            violations.append(
                f"tests LOC {test_loc} exceeds ceiling {TEST_LOC_MAX}{hint}"
            )
    else:
        base_src, base_tests = _baseline_loc(root, baseline_ref)
        measurements.append(f"LOC mode: growth against baseline ref {baseline_ref}")
        buckets = (
            ("src/indexed", src_loc, base_src, GROWTH_ALLOWANCE["src"]),
            ("tests", test_loc, base_tests, GROWTH_ALLOWANCE["tests"]),
        )
        for name, measured, baseline, allowance in buckets:
            delta = measured - baseline
            measurements.append(
                f"{name} LOC: {measured} ({delta:+d} vs baseline {baseline}, "
                f"allowance +{allowance})"
            )
            if measured > baseline + allowance:
                violations.append(
                    f"{name} grew {delta:+d} lines over {baseline_ref} "
                    f"({baseline} -> {measured}); the per-branch allowance is "
                    f"+{allowance}. Split the branch, or trim boilerplate first "
                    "(docs/spec/lessons.md, 'CI-only gates'), rather than raising "
                    "GROWTH_ALLOWANCE."
                )

    return violations, measurements


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-ref",
        metavar="REF",
        help=(
            "measure the LOC ceilings as growth against this ref (CI passes the "
            "PR base); omit for the legacy absolute ceilings"
        ),
    )
    args = parser.parse_args(argv)
    try:
        violations, measurements = check(ROOT, args.baseline_ref)
    except SizeGateError as exc:
        print(f"Size gate error: {exc}", file=sys.stderr)
        return 2
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
