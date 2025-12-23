"""Tests for the indexed knowledge inspect command.

We focus on realistic behaviors:
- listing all collections (none vs some)
- inspecting a specific collection (exists vs not exists)
- JSON vs rich output paths
"""

from typing import List

from typer.testing import CliRunner

from indexed.knowledge.commands import inspect as inspect_cmd
from core.v1.engine.services import CollectionInfo


runner = CliRunner()


def _make_collection(
    name: str = "docs",
    source_type: str = "localFiles",
    docs: int = 10,
    chunks: int = 20,
) -> CollectionInfo:
    """Helper to build a simple CollectionInfo instance for tests."""
    # CollectionInfo expects timestamps as strings, not datetime objects.
    # We use simple ISO-like strings so JSON output works naturally.
    return CollectionInfo(
        name=name,
        source_type=source_type,
        relative_path="/path/to/docs",
        number_of_documents=docs,
        number_of_chunks=chunks,
        disk_size_bytes=1024,
        index_size_bytes=512,
        created_time="2025-01-01T00:00:00Z",
        updated_time="2025-01-02T00:00:00Z",
    )


class TestInspectCollectionsCommand:
    """End-to-end-ish tests for inspect_collections via Typer app."""

    def test_no_collections_shows_hint(self, monkeypatch):
        """When there are no collections, show a helpful message."""
        monkeypatch.setattr(inspect_cmd, "inspect", lambda names=None: [])

        # No subcommand name required – this app exposes a single inspect command
        result = runner.invoke(inspect_cmd.app, [])

        assert result.exit_code == 0
        assert "No collections found" in result.stdout
        assert "Get started" in result.stdout

    def test_list_all_collections_brief(self, monkeypatch):
        """Listing all collections should show names and totals."""
        collections: List[CollectionInfo] = [
            _make_collection("docs", docs=3, chunks=5),
            _make_collection("jira", source_type="jira", docs=2, chunks=4),
        ]

        monkeypatch.setattr(inspect_cmd, "inspect", lambda names=None: collections)

        result = runner.invoke(inspect_cmd.app, [])

        assert result.exit_code == 0
        assert "docs" in result.stdout
        assert "jira" in result.stdout
        # Total summary line
        assert "total" in result.stdout.lower()

    def test_inspect_specific_collection_not_found(self, monkeypatch):
        """Inspecting a missing collection should show available ones and exit 1."""

        # First call: inspect([name]) returns empty list
        def fake_inspect(names=None):
            if names:
                return []
            # Second call: list of available collections
            return [_make_collection("docs"), _make_collection("jira")]

        monkeypatch.setattr(inspect_cmd, "inspect", fake_inspect)

        result = runner.invoke(inspect_cmd.app, ["missing"])

        assert result.exit_code == 1
        assert "Collection 'missing' not found" in result.stdout
        assert "Available collections" in result.stdout
        assert "docs" in result.stdout
        assert "jira" in result.stdout

    def test_inspect_specific_collection_json_output(self, monkeypatch):
        """JSON output for a specific collection should contain core fields."""
        coll = _make_collection("docs")

        def fake_inspect(names=None):
            if names:
                return [coll]
            return [coll]

        monkeypatch.setattr(inspect_cmd, "inspect", fake_inspect)

        result = runner.invoke(inspect_cmd.app, ["docs", "--json"])

        assert result.exit_code == 0
        assert '"name": "docs"' in result.stdout
        assert "number_of_documents" in result.stdout
        assert "number_of_chunks" in result.stdout

    def test_inspect_all_collections_json_output(self, monkeypatch):
        """JSON output for all collections should be a list of objects."""
        colls = [_make_collection("docs"), _make_collection("jira")]

        monkeypatch.setattr(inspect_cmd, "inspect", lambda names=None: colls)

        result = runner.invoke(inspect_cmd.app, ["--json"])

        assert result.exit_code == 0
        # Should show a JSON array with at least one of the names
        assert result.stdout.strip().startswith("[")
        assert '"docs"' in result.stdout or '"jira"' in result.stdout
