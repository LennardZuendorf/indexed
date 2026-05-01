"""End-to-end system tests for the --engine v2 flag across all CLI commands.

Tests follow the full workflow: create → search → inspect → remove.
The session fixture in `conftest.py` ensures the embedding model is cached
before any test runs.
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


class TestV2CreateAndSearch:
    """Test the create → search workflow using --engine v2."""

    def test_create_files_with_engine_v2_flag(
        self, e2e_docs: Path, e2e_workspace: Path
    ) -> None:
        """indexed --engine v2 index create files creates a collection successfully."""
        original_cwd = os.getcwd()
        try:
            os.chdir(e2e_workspace)
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
                    str(e2e_docs),
                    "--force",
                    "--local",
                ],
            )
        finally:
            os.chdir(original_cwd)

        clean = _strip_ansi(result.stdout)
        assert result.exit_code == 0, f"Create failed: {clean}"
        assert "v2-e2e-test" in clean

    def test_search_with_per_command_engine_v2(self, e2e_workspace: Path) -> None:
        """indexed index search --engine v2 returns results from the v2 collection."""
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
                    "v2-e2e-test",
                    "--engine",
                    "v2",
                    "--local",
                ],
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"Search failed: {_strip_ansi(result.stdout)}"

    def test_search_all_collections_engine_v2(self, e2e_workspace: Path) -> None:
        """indexed index search --engine v2 (no --collection) searches all v2 collections."""
        original_cwd = os.getcwd()
        try:
            os.chdir(e2e_workspace)
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

    def test_simple_output_search_engine_v2(self, e2e_workspace: Path) -> None:
        """Search with --engine v2 in simple-output mode returns parseable JSON."""
        original_cwd = os.getcwd()
        from indexed.utils.simple_output import set_simple_output, reset_simple_output

        set_simple_output(True)
        try:
            os.chdir(e2e_workspace)
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

    def test_inspect_all_collections_engine_v2(self, e2e_workspace: Path) -> None:
        """indexed index inspect --engine v2 lists v2 collections."""
        original_cwd = os.getcwd()
        try:
            os.chdir(e2e_workspace)
            result = runner.invoke(
                app,
                ["index", "inspect", "--engine", "v2", "--local"],
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"Inspect failed: {_strip_ansi(result.stdout)}"
        assert "v2-e2e-test" in _strip_ansi(result.stdout)

    def test_inspect_specific_collection_engine_v2(self, e2e_workspace: Path) -> None:
        """indexed index inspect <name> --engine v2 shows collection details."""
        original_cwd = os.getcwd()
        try:
            os.chdir(e2e_workspace)
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

    def test_remove_with_engine_v2(self, e2e_workspace: Path) -> None:
        """indexed index remove --engine v2 --force removes the v2 collection."""
        original_cwd = os.getcwd()
        try:
            os.chdir(e2e_workspace)
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
