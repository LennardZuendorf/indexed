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

from indexed.app import app


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
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

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
# V2 engine benchmarks
# ---------------------------------------------------------------------------


def _v2_model_available() -> bool:
    """Check if the v2 embedding model (same as v1) is cached."""
    try:
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

        return is_model_cached("all-MiniLM-L6-v2")
    except Exception:
        return False


v2_skip = pytest.mark.skipif(
    not _v2_model_available(),
    reason="v2 embedding model not cached (requires all-MiniLM-L6-v2)",
)


@pytest.fixture(scope="module")
def created_collection_v2(benchmark_docs, benchmark_workspace) -> str:
    """Create a v2 collection once for search benchmarks to reuse.

    This is NOT benchmarked — it is setup for the v2 search benchmark.
    """
    collection_name = "bench-search-v2"
    original_cwd = os.getcwd()
    try:
        os.chdir(benchmark_workspace)
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
                f"V2 collection creation failed (exit {result.exit_code}): "
                f"{_strip_ansi(result.stdout[:500])}"
            )
    finally:
        os.chdir(original_cwd)

    return collection_name


@v2_skip
@pytest.mark.benchmark(min_rounds=2, max_time=60.0)
def test_e2e_create_collection_v2(benchmark, benchmark_docs, benchmark_workspace):
    """Benchmark: full `indexed --engine v2 index create files`.

    Measures the complete v2 pipeline:
    - CLI startup and config loading
    - File reading and LlamaIndex chunking
    - Embedding model loading (cached after first round)
    - Embedding generation for all chunks
    - FAISS index construction and persistence
    """
    original_cwd = os.getcwd()

    def run_create():
        os.chdir(benchmark_workspace)
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
                f"V2 create failed (exit {result.exit_code}): "
                f"{_strip_ansi(result.stdout[:500])}"
            )
        finally:
            os.chdir(original_cwd)

    benchmark(run_create)


@v2_skip
@pytest.mark.benchmark(min_rounds=3, max_time=60.0)
def test_e2e_search_collection_v2(
    benchmark, created_collection_v2, benchmark_workspace
):
    """Benchmark: full `indexed index search --engine v2`.

    Measures the complete v2 search pipeline:
    - CLI startup and config loading
    - Query embedding via LlamaIndex
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
                    "indexed collections engine",
                    "--collection",
                    created_collection_v2,
                    "--engine",
                    "v2",
                    "--local",
                    "--compact",
                ],
            )
            assert result.exit_code == 0, (
                f"V2 search failed (exit {result.exit_code}): "
                f"{_strip_ansi(result.stdout[:500])}"
            )
        finally:
            os.chdir(original_cwd)

    benchmark(run_search)
