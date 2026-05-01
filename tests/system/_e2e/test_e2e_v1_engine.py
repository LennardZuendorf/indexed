"""End-to-end system tests for the default v1 engine across all CLI commands.

Mirrors the v2 e2e suite to give the v1 path equivalent end-to-end coverage:
create → search → inspect → remove with the real HuggingFace embedder and FAISS.
"""

import json
import os
import re
from pathlib import Path

from typer.testing import CliRunner

from indexed.app import app


runner = CliRunner()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestV1CreateAndSearch:
    """Test the create → search workflow using the default v1 engine."""

    def test_create_files_default_engine(
        self, e2e_docs: Path, e2e_workspace: Path
    ) -> None:
        """indexed index create files (default engine) creates a v1 collection."""
        original_cwd = os.getcwd()
        try:
            os.chdir(e2e_workspace)
            result = runner.invoke(
                app,
                [
                    "index",
                    "create",
                    "files",
                    "--collection",
                    "v1-e2e-test",
                    "--path",
                    str(e2e_docs),
                    "--force",
                    "--local",
                ],
            )
        finally:
            os.chdir(original_cwd)

        clean = _strip_ansi(result.stdout)
        assert result.exit_code == 0, f"Create failed: {clean}"
        assert "v1-e2e-test" in clean

    def test_search_specific_collection(self, e2e_workspace: Path) -> None:
        """indexed index search returns results from the v1 collection."""
        original_cwd = os.getcwd()
        try:
            os.chdir(e2e_workspace)
            result = runner.invoke(
                app,
                [
                    "index",
                    "search",
                    "semantic search embeddings",
                    "--collection",
                    "v1-e2e-test",
                    "--local",
                ],
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"Search failed: {_strip_ansi(result.stdout)}"

    def test_search_all_collections(self, e2e_workspace: Path) -> None:
        """indexed index search (no --collection) searches all v1 collections."""
        original_cwd = os.getcwd()
        try:
            os.chdir(e2e_workspace)
            result = runner.invoke(
                app,
                [
                    "index",
                    "search",
                    "document indexing",
                    "--local",
                ],
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"Search failed: {_strip_ansi(result.stdout)}"

    def test_simple_output_search(self, e2e_workspace: Path) -> None:
        """Search in simple-output mode returns parseable JSON."""
        original_cwd = os.getcwd()
        from indexed.utils.simple_output import set_simple_output, reset_simple_output

        set_simple_output(True)
        try:
            os.chdir(e2e_workspace)
            result = runner.invoke(
                app,
                [
                    "index",
                    "search",
                    "indexing pipeline",
                    "--collection",
                    "v1-e2e-test",
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


class TestV1Inspect:
    """Test the inspect command with the default v1 engine."""

    def test_inspect_all_collections(self, e2e_workspace: Path) -> None:
        """indexed index inspect lists v1 collections."""
        original_cwd = os.getcwd()
        try:
            os.chdir(e2e_workspace)
            result = runner.invoke(
                app,
                ["index", "inspect", "--local"],
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"Inspect failed: {_strip_ansi(result.stdout)}"
        assert "v1-e2e-test" in _strip_ansi(result.stdout)

    def test_inspect_specific_collection(self, e2e_workspace: Path) -> None:
        """indexed index inspect <name> shows v1 collection details."""
        original_cwd = os.getcwd()
        try:
            os.chdir(e2e_workspace)
            result = runner.invoke(
                app,
                ["index", "inspect", "v1-e2e-test", "--local"],
            )
        finally:
            os.chdir(original_cwd)

        clean = _strip_ansi(result.stdout)
        assert result.exit_code == 0, f"Inspect specific failed: {clean}"
        assert "v1-e2e-test" in clean


class TestV1Remove:
    """Test the remove command with the default v1 engine."""

    def test_remove_default_engine(self, e2e_workspace: Path) -> None:
        """indexed index remove --force removes the v1 collection."""
        original_cwd = os.getcwd()
        try:
            os.chdir(e2e_workspace)
            result = runner.invoke(
                app,
                [
                    "index",
                    "remove",
                    "v1-e2e-test",
                    "--force",
                    "--local",
                ],
            )
        finally:
            os.chdir(original_cwd)

        clean = _strip_ansi(result.stdout)
        assert result.exit_code == 0, f"Remove failed: {clean}"
        assert "removed" in clean.lower()
