"""End-to-end performance benchmarks for CLI commands.

These benchmarks run actual CLI commands against real files to measure
realistic wall-clock performance including model loading, embedding
generation, FAISS indexing, and search.

Unlike the existing hot-path benchmarks in test_search_performance.py,
these tests exercise the FULL pipeline from CLI invocation to completion.

Requirements:
- Embedding model (all-MiniLM-L6-v2) must be cached or downloadable
- Run with: uv run pytest tests/benchmarks/test_e2e_performance.py -v --benchmark-only
"""

import os
import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indexed.cli.app import app


runner = CliRunner()

# Path to real markdown docs in the repo (used as benchmark corpus)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCS_SOURCES = [
    _REPO_ROOT / "docs" / "architecture-internals.md",
    _REPO_ROOT / "docs" / "cli-implementation.md",
    _REPO_ROOT / "docs" / "index.md",
    _REPO_ROOT / "README.md",
    _REPO_ROOT / "packages" / "indexed-core" / "README.md",
    _REPO_ROOT / "packages" / "indexed-connectors" / "README.md",
    _REPO_ROOT / "packages" / "indexed-config" / "README.md",
    _REPO_ROOT / "packages" / "utils" / "README.md",
]


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _check_model_available() -> bool:
    """Check if the embedding model is cached and usable."""
    try:
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            is_model_cached,
        )

        return is_model_cached("all-MiniLM-L6-v2")
    except Exception:
        return False


# Skip all tests in this module if model is not available
pytestmark = pytest.mark.skipif(
    not _check_model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)


@pytest.fixture(scope="module")
def benchmark_docs(tmp_path_factory) -> Path:
    """Copy real markdown files into a temp directory for benchmarking."""
    docs_dir = tmp_path_factory.mktemp("benchmark_docs")

    copied = 0
    for src in _DOCS_SOURCES:
        if src.exists():
            shutil.copy2(src, docs_dir / src.name)
            copied += 1

    # Ensure we have at least some files
    if copied == 0:
        # Fallback: generate a minimal test corpus
        for i in range(5):
            (docs_dir / f"doc-{i}.md").write_text(
                f"# Document {i}\n\nThis is test document number {i}. "
                f"It contains content about software architecture, "
                f"indexing, search, and document management.\n" * 10
            )

    return docs_dir


@pytest.fixture(scope="module")
def benchmark_workspace(tmp_path_factory) -> Path:
    """Create a temp workspace with .indexed/ for local collection storage."""
    workspace = tmp_path_factory.mktemp("benchmark_workspace")
    indexed_dir = workspace / ".indexed"
    indexed_dir.mkdir()
    (indexed_dir / "config.toml").touch()
    return workspace


@pytest.fixture(scope="module")
def created_collection(benchmark_docs, benchmark_workspace) -> str:
    """Create a collection once for search benchmarks to reuse.

    This is NOT benchmarked - it's setup for the search benchmark.
    """
    collection_name = "bench-search"
    original_cwd = os.getcwd()
    try:
        os.chdir(benchmark_workspace)
        result = runner.invoke(
            app,
            [
                "index",
                "create",
                "files",
                "--collection",
                collection_name,
                "--path",
                str(benchmark_docs),
                "--force",
                "--local",
            ],
        )
        if result.exit_code != 0:
            pytest.skip(
                f"Collection creation failed (exit {result.exit_code}): "
                f"{_strip_ansi(result.stdout[:500])}"
            )
    finally:
        os.chdir(original_cwd)

    return collection_name


# ---------------------------------------------------------------------------
# End-to-end benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(min_rounds=2, max_time=60.0)
def test_e2e_create_collection(benchmark, benchmark_docs, benchmark_workspace):
    """Benchmark: full `indexed index create files` on real markdown docs.

    Measures the complete pipeline:
    - CLI startup and config loading
    - File reading and chunking
    - Embedding model loading (cached after first run)
    - Embedding generation for all chunks
    - FAISS index construction
    - Disk persistence (manifest, chunks, index)
    """
    original_cwd = os.getcwd()

    def run_create():
        os.chdir(benchmark_workspace)
        try:
            result = runner.invoke(
                app,
                [
                    "index",
                    "create",
                    "files",
                    "--collection",
                    "bench-create",
                    "--path",
                    str(benchmark_docs),
                    "--force",
                    "--local",
                ],
            )
            assert result.exit_code == 0, (
                f"Create failed (exit {result.exit_code}): "
                f"{_strip_ansi(result.stdout[:500])}"
            )
        finally:
            os.chdir(original_cwd)

    benchmark(run_create)


@pytest.mark.benchmark(min_rounds=3, max_time=60.0)
def test_e2e_search_collection(benchmark, created_collection, benchmark_workspace):
    """Benchmark: full `indexed index search` on a real collection.

    Measures the complete search pipeline:
    - CLI startup and config loading
    - Query embedding generation
    - FAISS similarity search
    - Result mapping and formatting
    """
    original_cwd = os.getcwd()

    def run_search():
        os.chdir(benchmark_workspace)
        try:
            result = runner.invoke(
                app,
                [
                    "index",
                    "search",
                    "indexing architecture and search",
                    "--collection",
                    created_collection,
                    "--limit",
                    "5",
                    "--compact",
                ],
            )
            assert result.exit_code == 0, (
                f"Search failed (exit {result.exit_code}): "
                f"{_strip_ansi(result.stdout[:500])}"
            )
        finally:
            os.chdir(original_cwd)

    benchmark(run_search)


@pytest.mark.benchmark(min_rounds=2, max_time=60.0)
def test_e2e_search_all_collections(benchmark, created_collection, benchmark_workspace):
    """Benchmark: `indexed index search` without --collection (searches all).

    Measures the overhead of auto-discovering and searching all collections.
    """
    original_cwd = os.getcwd()

    def run_search_all():
        os.chdir(benchmark_workspace)
        try:
            result = runner.invoke(
                app,
                [
                    "index",
                    "search",
                    "document management",
                    "--limit",
                    "5",
                    "--compact",
                ],
            )
            assert result.exit_code == 0, (
                f"Search-all failed (exit {result.exit_code}): "
                f"{_strip_ansi(result.stdout[:500])}"
            )
        finally:
            os.chdir(original_cwd)

    benchmark(run_search_all)


@pytest.mark.benchmark(min_rounds=3, max_time=60.0)
def test_e2e_inspect_collections(benchmark, created_collection, benchmark_workspace):
    """Benchmark: `indexed index inspect` to list all collections.

    Measures collection metadata loading and formatting overhead.
    """
    original_cwd = os.getcwd()

    def run_inspect():
        os.chdir(benchmark_workspace)
        try:
            result = runner.invoke(
                app,
                ["index", "inspect"],
            )
            assert result.exit_code == 0, (
                f"Inspect failed (exit {result.exit_code}): "
                f"{_strip_ansi(result.stdout[:500])}"
            )
        finally:
            os.chdir(original_cwd)

    benchmark(run_inspect)


# ---------------------------------------------------------------------------
# v2 engine benchmarks (core-v2/8, R12)
#
# The v2 cases live in their OWN workspace fixture, isolated from the v1
# ``benchmark_workspace`` — v2 collections must never leak into the v1
# ``search --all`` path (which would perturb the v1 rows and the documented
# order-dependent ``test_e2e_search_collection`` flake). Names avoid the v1
# threshold-map substrings (``e2e_create``/``e2e_search``) so each row maps to
# exactly one CI threshold key (``e2e_v2_create``/``e2e_v2_search``).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def benchmark_workspace_v2(tmp_path_factory) -> Path:
    """A separate temp workspace so v2 collections never share v1's state."""
    workspace = tmp_path_factory.mktemp("benchmark_workspace_v2")
    indexed_dir = workspace / ".indexed"
    indexed_dir.mkdir()
    (indexed_dir / "config.toml").touch()
    return workspace


@pytest.fixture(scope="module")
def created_collection_v2(benchmark_docs, benchmark_workspace_v2) -> str:
    """Create a v2 collection once for the v2 search benchmark to reuse."""
    collection_name = "bench-search-v2"
    original_cwd = os.getcwd()
    try:
        os.chdir(benchmark_workspace_v2)
        result = runner.invoke(
            app,
            [
                "--engine",
                "v2",
                "index",
                "create",
                "files",
                "--collection",
                collection_name,
                "--path",
                str(benchmark_docs),
                "--force",
                "--local",
            ],
        )
        if result.exit_code != 0:
            pytest.skip(
                f"v2 collection creation failed (exit {result.exit_code}): "
                f"{_strip_ansi(result.stdout[:500])}"
            )
    finally:
        os.chdir(original_cwd)

    return collection_name


@pytest.mark.benchmark(min_rounds=2, max_time=60.0)
def test_e2e_v2_create(benchmark, benchmark_docs, benchmark_workspace_v2):
    """Benchmark: full `indexed --engine v2 index create files` (v2 pipeline).

    Same corpus as the v1 ``test_e2e_create_collection`` row so their CI
    baselines are directly comparable. Budget (asserted in
    ``test_v2_vs_v1_performance_budgets``): v2 create ≤ 1.5× v1 create.
    """
    original_cwd = os.getcwd()

    def run_create_v2():
        os.chdir(benchmark_workspace_v2)
        try:
            result = runner.invoke(
                app,
                [
                    "--engine",
                    "v2",
                    "index",
                    "create",
                    "files",
                    "--collection",
                    "bench-create-v2",
                    "--path",
                    str(benchmark_docs),
                    "--force",
                    "--local",
                ],
            )
            assert result.exit_code == 0, (
                f"v2 create failed (exit {result.exit_code}): "
                f"{_strip_ansi(result.stdout[:500])}"
            )
        finally:
            os.chdir(original_cwd)

    benchmark(run_create_v2)


@pytest.mark.benchmark(min_rounds=3, max_time=60.0)
def test_e2e_v2_search(benchmark, created_collection_v2, benchmark_workspace_v2):
    """Benchmark: full `indexed index search` on a v2 collection (v2 retrieval).

    Budget (asserted in ``test_v2_vs_v1_performance_budgets``): v2 warm search
    ≤ 2× v1 warm search.
    """
    original_cwd = os.getcwd()

    def run_search_v2():
        os.chdir(benchmark_workspace_v2)
        try:
            result = runner.invoke(
                app,
                [
                    "index",
                    "search",
                    "indexing architecture and search",
                    "--collection",
                    created_collection_v2,
                    "--limit",
                    "5",
                    "--compact",
                ],
            )
            assert result.exit_code == 0, (
                f"v2 search failed (exit {result.exit_code}): "
                f"{_strip_ansi(result.stdout[:500])}"
            )
        finally:
            os.chdir(original_cwd)

    benchmark(run_search_v2)


# ---------------------------------------------------------------------------
# v1-vs-v2 performance-budget ratio assertion (core-v2/8, R12)
# ---------------------------------------------------------------------------


def _time_cli_subprocess(args: list[str], cwd: Path, env: dict, rounds: int) -> float:
    """Best-of-``rounds`` wall time of one full `indexed` CLI invocation.

    Measured OUT-OF-PROCESS (a fresh ``python -m indexed.cli.app`` per run) so
    BOTH engines pay the same disk-cached-model load — the realistic steady
    state for a CLI tool (every real ``indexed search`` is a new process). An
    in-process ``CliRunner`` would instead hand v1 a cross-invocation
    process-global model cache that v2's per-call ``HuggingFaceEmbedding`` does
    not share, inflating the ratio with an artifact unrelated to the
    search-algorithm cost the tech.md budget is about (NumPy vs FAISS, same
    O(N·d)). ``min`` over rounds discards scheduler noise.
    """
    import subprocess
    import sys
    import time

    best = float("inf")
    for _ in range(rounds):
        start = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "-m", "indexed.cli.app", *args],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
        )
        elapsed = time.perf_counter() - start
        assert proc.returncode == 0, proc.stdout + proc.stderr
        best = min(best, elapsed)
    return best


def test_v2_vs_v1_performance_budgets(benchmark_docs, tmp_path):
    """R12: v2 create ≤ 1.5× v1 create AND v2 warm search ≤ 2× v1 warm search.

    Measures both engines on the SAME corpus at the full-CLI (subprocess) level
    — see ``_time_cli_subprocess`` for why out-of-process is the fair basis.
    Skipped under ``--benchmark-only`` (no ``benchmark`` fixture); runs in the
    normal gate. Isolated tmp workspace, so it never touches the v1 benchmark
    collections or the known order-dependent flake.
    """
    import os

    ws = tmp_path / "budget_ws"
    (ws / ".indexed").mkdir(parents=True)
    (ws / ".indexed" / "config.toml").touch()
    env = {**os.environ, "TQDM_DISABLE": "1"}

    def create_args(engine: list[str], name: str) -> list[str]:
        return [
            *engine,
            "--local",
            "--log-level",
            "ERROR",
            "create",
            "files",
            "--collection",
            name,
            "--path",
            str(benchmark_docs),
            "--local",
            "--force",
            "--no-cache",
        ]

    def search_args(name: str) -> list[str]:
        return [
            "--local",
            "--log-level",
            "ERROR",
            "search",
            "indexing architecture and search",
            "--collection",
            name,
            "--limit",
            "5",
            "--compact",
        ]

    # --- create ratio (best of 2; the create also seeds the search corpus) ---
    v1_create = _time_cli_subprocess(create_args([], "budget-v1"), ws, env, rounds=2)
    v2_create = _time_cli_subprocess(
        create_args(["--engine", "v2"], "budget-v2"), ws, env, rounds=2
    )
    create_ratio = v2_create / v1_create

    # --- warm-search ratio (best of 3) ---
    v1_search = _time_cli_subprocess(search_args("budget-v1"), ws, env, rounds=3)
    v2_search = _time_cli_subprocess(search_args("budget-v2"), ws, env, rounds=3)
    search_ratio = v2_search / v1_search

    print(
        f"\n[core-v2/8 budgets] create v1={v1_create:.3f}s v2={v2_create:.3f}s "
        f"ratio={create_ratio:.2f}x (≤1.5x); "
        f"search v1={v1_search:.3f}s v2={v2_search:.3f}s "
        f"ratio={search_ratio:.2f}x (≤2.0x)"
    )

    assert create_ratio <= 1.5, (
        f"v2 create {v2_create:.3f}s is {create_ratio:.2f}× v1 {v1_create:.3f}s "
        f"(budget ≤1.5×)"
    )
    assert search_ratio <= 2.0, (
        f"v2 warm search {v2_search:.3f}s is {search_ratio:.2f}× v1 "
        f"{v1_search:.3f}s (budget ≤2.0×)"
    )
