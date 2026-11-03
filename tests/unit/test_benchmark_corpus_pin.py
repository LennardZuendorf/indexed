"""Pin the parsing benchmark corpus to fixed bytes.

``tests/benchmarks/test_parsing_performance.py`` measures the parsing pipeline
over ``tests/benchmarks/fixtures/parsing_corpus/`` — a frozen snapshot, not the
live spec tree. A benchmark that reads the repo's own documents slows down by
construction whenever a PR adds a spec file, and the benchmark baseline guard
forbids that PR from absorbing the difference, so the gate reds with no in-PR
way to go green.

Refresh the lock only as a deliberate corpus change (and expect a benchmark
baseline refresh to follow)::

    cd tests/benchmarks/fixtures/parsing_corpus
    find . -type f | sort | xargs sha256sum > ../parsing_corpus.sha256
"""

from __future__ import annotations

import hashlib
from pathlib import Path

BENCHMARKS_DIR = Path(__file__).resolve().parents[1] / "benchmarks"
FIXTURES_DIR = BENCHMARKS_DIR / "fixtures"
CORPUS_DIR = FIXTURES_DIR / "parsing_corpus"
CORPUS_LOCK = FIXTURES_DIR / "parsing_corpus.sha256"


def _locked_digests() -> dict[str, str]:
    """Parse the ``sha256sum``-style lock into {relative path: digest}."""
    locked: dict[str, str] = {}
    for line in CORPUS_LOCK.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, relative_path = line.partition("  ")
        locked[relative_path] = digest
    return locked


def _corpus_digests() -> dict[str, str]:
    """sha256 every tracked corpus file, keyed by its ./relative path."""
    return {
        f"./{path.relative_to(CORPUS_DIR).as_posix()}": hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in CORPUS_DIR.rglob("*")
        if path.is_file()
    }


class TestPinnedBenchmarkCorpus:
    """The corpus is a fixed input set: any drift is a deliberate change."""

    def test_corpus_matches_its_lock(self) -> None:
        locked = _locked_digests()
        assert locked, f"{CORPUS_LOCK} is empty — regenerate it"

        actual = _corpus_digests()
        added = sorted(set(actual) - set(locked))
        removed = sorted(set(locked) - set(actual))
        changed = sorted(p for p in set(actual) & set(locked) if actual[p] != locked[p])

        assert not (added or removed or changed), (
            "the pinned benchmark corpus drifted from parsing_corpus.sha256 "
            f"(added={added}, removed={removed}, changed={changed}). A corpus "
            "change is a benchmark change: regenerate the lock deliberately with "
            "`cd tests/benchmarks/fixtures/parsing_corpus && find . -type f | "
            "sort | xargs sha256sum > ../parsing_corpus.sha256`, then refresh the "
            "benchmark baseline through the workflow's refresh lane."
        )

    def test_parsing_benchmarks_read_the_pinned_corpus(self) -> None:
        """Guard the wiring: benchmarks must not derive paths from the spec tree."""
        source = (BENCHMARKS_DIR / "test_parsing_performance.py").read_text(
            encoding="utf-8"
        )
        assert 'PROJECT_ROOT / ".spec"' not in source, (
            "test_parsing_performance.py points a benchmark at the live spec "
            "tree again; read CORPUS_DIR (tests/benchmarks/fixtures/"
            "parsing_corpus) instead, or every spec-bearing PR reds the gate by "
            "construction."
        )
        assert '"fixtures" / "parsing_corpus"' in source, (
            "test_parsing_performance.py no longer resolves CORPUS_DIR to the "
            "pinned fixture corpus."
        )
