"""End-to-end system tests for the --engine v2 flag across all CLI commands.

Tests follow the full workflow: create → search → inspect → remove.
All tests are skipped automatically if the v2 embedding model is not cached locally
to avoid downloading large model files in CI environments that haven't pre-seeded them.
"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Generator

import pytest
from typer.testing import CliRunner

from indexed.app import app


runner = CliRunner()

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _v2_model_available() -> bool:
    """Return True only if the v2 embedding model is already cached locally."""
    try:
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

        # v2 defaults to the same model as v1
        return is_model_cached("all-MiniLM-L6-v2")
    except Exception:
        return False


# Skip all tests in this module when the embedding model is not cached.
pytestmark = pytest.mark.skipif(
    not _v2_model_available(),
    reason="v2 embedding model not cached (requires all-MiniLM-L6-v2)",
)


@pytest.fixture(scope="module")
def v2_docs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a small corpus of markdown files for v2 e2e tests."""
    docs_dir = tmp_path_factory.mktemp("v2_docs")

    # Try to copy real docs from the repo
    real_docs = [
        _REPO_ROOT / "README.md",
        _REPO_ROOT / "docs" / "index.md",
    ]
    copied = 0
    for src in real_docs:
        if src.exists():
            shutil.copy2(src, docs_dir / src.name)
            copied += 1

    # Ensure we always have at least some content
    if copied == 0:
        for i in range(3):
            (docs_dir / f"v2-test-doc-{i}.md").write_text(
                f"# V2 Test Document {i}\n\n"
                f"This document tests the v2 engine indexing pipeline. "
                f"It contains content about semantic search, embeddings, and FAISS. "
                f"Document number {i} in the v2 test corpus.\n" * 5
            )

    return docs_dir


@pytest.fixture(scope="module")
def v2_workspace(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[Path, None, None]:
    """Create an isolated workspace with .indexed/ for local storage."""
    workspace = tmp_path_factory.mktemp("v2_workspace")
    indexed_dir = workspace / ".indexed"
    indexed_dir.mkdir()
    (indexed_dir / "config.toml").touch()
    yield workspace


class TestV2CreateAndSearch:
    """Test the create → search workflow using --engine v2."""

    def test_create_files_with_engine_v2_flag(
        self, v2_docs: Path, v2_workspace: Path
    ) -> None:
        """indexed --engine v2 index create files creates a collection successfully."""
        original_cwd = os.getcwd()
        try:
            os.chdir(v2_workspace)
            result = runner.invoke(
                app,
                [
                    "--engine",
                    "v2",
                    "index",
                    "create",
                    "files",
                    "--collection",
                    "v2-e2e-test",
                    "--path",
                    str(v2_docs),
                    "--force",
                    "--local",
                ],
            )
        finally:
            os.chdir(original_cwd)

        clean = _strip_ansi(result.stdout)
        assert result.exit_code == 0, f"Create failed: {clean}"
        assert "v2-e2e-test" in clean

    def test_search_with_per_command_engine_v2(self, v2_workspace: Path) -> None:
        """indexed index search --engine v2 returns results from the v2 collection."""
        original_cwd = os.getcwd()
        try:
            os.chdir(v2_workspace)
            result = runner.invoke(
                app,
                [
                    "index",
                    "search",
                    "semantic search embeddings",
                    "--collection",
                    "v2-e2e-test",
                    "--engine",
                    "v2",
                    "--local",
                ],
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"Search failed: {_strip_ansi(result.stdout)}"

    def test_search_all_collections_engine_v2(self, v2_workspace: Path) -> None:
        """indexed index search --engine v2 (no --collection) searches all v2 collections."""
        original_cwd = os.getcwd()
        try:
            os.chdir(v2_workspace)
            result = runner.invoke(
                app,
                [
                    "--engine",
                    "v2",
                    "index",
                    "search",
                    "document indexing",
                    "--local",
                ],
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"Search failed: {_strip_ansi(result.stdout)}"

    def test_simple_output_search_engine_v2(self, v2_workspace: Path) -> None:
        """Search with --engine v2 in simple-output mode returns parseable JSON."""
        original_cwd = os.getcwd()
        from indexed.utils.simple_output import set_simple_output, reset_simple_output

        set_simple_output(True)
        try:
            os.chdir(v2_workspace)
            result = runner.invoke(
                app,
                [
                    "--engine",
                    "v2",
                    "index",
                    "search",
                    "indexing pipeline",
                    "--collection",
                    "v2-e2e-test",
                    "--local",
                ],
            )
        finally:
            os.chdir(original_cwd)
            reset_simple_output()

        assert result.exit_code == 0, f"Search failed: {result.stdout}"
        parsed = json.loads(result.stdout)
        assert "query" in parsed
        assert "results" in parsed


class TestV2Inspect:
    """Test the inspect command with --engine v2."""

    def test_inspect_all_collections_engine_v2(self, v2_workspace: Path) -> None:
        """indexed index inspect --engine v2 lists v2 collections."""
        original_cwd = os.getcwd()
        try:
            os.chdir(v2_workspace)
            result = runner.invoke(
                app,
                ["index", "inspect", "--engine", "v2", "--local"],
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"Inspect failed: {_strip_ansi(result.stdout)}"
        assert "v2-e2e-test" in _strip_ansi(result.stdout)

    def test_inspect_specific_collection_engine_v2(self, v2_workspace: Path) -> None:
        """indexed index inspect <name> --engine v2 shows collection details."""
        original_cwd = os.getcwd()
        try:
            os.chdir(v2_workspace)
            result = runner.invoke(
                app,
                ["index", "inspect", "v2-e2e-test", "--engine", "v2", "--local"],
            )
        finally:
            os.chdir(original_cwd)

        clean = _strip_ansi(result.stdout)
        assert result.exit_code == 0, f"Inspect specific failed: {clean}"
        assert "v2-e2e-test" in clean


class TestV2Remove:
    """Test the remove command with --engine v2."""

    def test_remove_with_engine_v2(self, v2_workspace: Path) -> None:
        """indexed index remove --engine v2 --force removes the v2 collection."""
        original_cwd = os.getcwd()
        try:
            os.chdir(v2_workspace)
            result = runner.invoke(
                app,
                [
                    "index",
                    "remove",
                    "v2-e2e-test",
                    "--engine",
                    "v2",
                    "--force",
                    "--local",
                ],
            )
        finally:
            os.chdir(original_cwd)

        clean = _strip_ansi(result.stdout)
        assert result.exit_code == 0, f"Remove failed: {clean}"
        assert "removed" in clean.lower()
