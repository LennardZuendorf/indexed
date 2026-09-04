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

SRC_LOC_MAX = 26_450
# Raised from 26_100 by core-v2-discoverability/issue #188 (#191): group-level
# `--engine` on `index create` (`_create_options.py`/`_create_commands.py`/
# `_create_helpers.py`, plus `create.py`/`search.py`/`cli.py`/
# `composition.py` wiring) and config-key discoverability for
# `--rerank`/`--no-rerank` — genuine discoverability surface, not stealth
# regrowth; ceiling = measured (26_235) + headroom.
# Raised from 25_800 by core-v2/6: opt-in `SentenceTransformerRerank` wiring in
# `core/v2/retrieval.py` (+ `CoreV2RerankConfig` / `resolve_rerank_config` /
# registration) and the cross-engine unified-relevance ranking in
# `mcp/formatting.py` + `cli/.../search_render.py` (R10/R11) — genuine
# new-feature surface; ceiling = measured (25_857) + headroom.
# Raised from 25_100 by core-v2/4: the v1->v2 migration service
# (`core/v2/migration.py`: offline + from-source read, build-aside + validate +
# backup/atomic-swap/rollback), the facade-exposed `migrate` in `core/engine.py`,
# and the thin `cli/knowledge/commands/migrate.py` command — genuine new-feature
# surface (R7); ceiling = measured (25_708) + headroom.
# Raised from 24_950 by core-v2/3: the v2 incremental `update` path in
# `core/v2/ingestion.py` (docstore-hash upsert + deletions + build-aside swap +
# per-doc content hashing shared with create) and the service `update` rewire —
# genuine new-feature surface; ceiling = measured (25_005) + headroom.
# Raised from 24_600 by core-v2/2d: R13 engine-aware diagnostics
# (`EngineDescriptor`/`engine_descriptors` in the facade + inspect display),
# v2 search parity (`include_full_text`/`include_all_chunks` reconstruction in
# `core/v2/retrieval.py`), scoreKind-conditional formatter ordering, and the
# check_imports v2-edge guard — genuine new-feature surface; ceiling = measured
# (24_786) + headroom.
# Raised from 23_500 by core-v2/2c, which wires the v2 engine end to end:
# `core/v2/{persist,ingestion,retrieval,_common}.py` + `core/v2/services/` +
# the facade's `_engine_impl("2")` branch and per-engine grouping in
# `core/engine.py` + the CoreV2Error type — genuine new-feature surface, not
# stealth regrowth; ceiling = measured (24_433) + headroom.
# Raised from 23_300 by core-v2/2b, which adds the native embedding factory
# (`core/v2/embedding/local.py`) + vector-store construction/LOAD dispatch
# (`core/v2/stores.py`) + the UnknownVectorStoreError — genuine new-feature
# surface, not stealth regrowth; ceiling = measured (23_416) + headroom.
# Raised from 23_000 by core-v2/2a, which adds the v2 manifest/config-model/
# adapter package (`core/v2/{__init__,manifest,config_models,adapter}.py`) —
# genuine new-feature surface (pre-approved in `.spec/lessons.md`'s v1 surface
# map note), not stealth regrowth; ceiling = measured (23_179) + headroom.
# Raised from 29_000 after the review-remediation feature added ~90 red->green
# regression tests (one per confirmed PR #155 defect). That is legitimate
# defect-guarding coverage, not stealth regrowth; ceiling = measured + headroom.
TEST_LOC_MAX = 39_600
# Raised from 36_850 by core-v2-discoverability/issue #188 (#191)'s tests: the
# new `test_v2_create_search_lifecycle.py` system test, and expanded coverage
# in `test_create.py`/`test_create_helpers.py`/`test_search.py`/
# `test_knowledge_cli.py`/`test_retrieval.py`/`test_engine_facade*.py`/
# `test_engine_selector.py` for the group-`--engine` and `--rerank` surfaces —
# genuine discoverability/regression coverage, not stealth regrowth; ceiling =
# measured (39_283) + headroom.
# Raised from 36_400 by core-v2/8's tests: the v2 cloud-connector lifecycle net
# (`test_lifecycle_cloud_v2.py`: jira/confluence/outline known-hit
# create→search→update→inspect→remove), the v2 benchmark rows + subprocess
# v1-vs-v2 budget-ratio test in `test_e2e_performance.py`, and the
# out-of-process MCP v2 stdio smoke (`test_mcp_v2_out_of_process.py`) — genuine
# parity/perf coverage (R4/R12); ceiling = measured (36_579) + headroom.
# Raised from 35_800 by core-v2/6's tests: the rerank suite (disabled lazy-import
# probe, enabled fake-reranker order/top_n, gated real-CE) in `test_retrieval.py`,
# the cross-engine unified-relevance + v1-only byte-identical tests in
# `test_formatting.py` and `test_search.py`, and the rerank config-model/
# registration tests; ceiling = measured (36_093) + headroom.
# Raised from 35_200 by core-v2/4's tests: the migration service unit suite
# (`test_migration.py`: dry-run/offline/failed-validation/rollback/purge/
# from-source) + the v1->v2 migration CLI system test
# (`test_v2_migration_lifecycle.py`: search parity + offline no-network);
# ceiling = measured (35_553) + headroom.
# Raised from 34_650 by core-v2/3's tests: the v2 incremental-update unit suite
# (`test_ingestion_update.py`: incrementality/embed-count proof, deletions,
# empty no-op, build-aside mid-swap failure), the service + facade update tests,
# and the new v2 files-lifecycle characterization net
# (`test_lifecycle_files_v2.py`); ceiling = measured (35_073) + headroom.
# Raised from 33_800 by core-v2/2d's tests: facade `engine_descriptors`,
# inspect engine-diagnostics, retrieval full-text/all-chunks parity, the
# store-dispatch integration probe, the scoreKind formatter tests, and the v2
# create/search CLI system test; ceiling = measured (34_489) + headroom.
# Raised from 32_800 by core-v2/2c's engine tests (persist crash-safety,
# ingestion/retrieval/services model-free + KNOWN-HIT model-gated, facade
# grouping + mixed v1/v2, cache-drift guard); ceiling = measured (33_599) +
# headroom.
# Raised from 32_500 by core-v2/2b's model-free wiring + real-model
# (offline-proof / parity / store-dispatch) tests; ceiling = measured
# (32_684) + headroom.
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
