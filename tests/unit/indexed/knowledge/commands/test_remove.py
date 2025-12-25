"""Tests for the indexed knowledge remove command.

We focus on realistic behaviors:
- removing from an empty index
- trying to remove a missing collection
- confirmation flow with and without --force
"""

from typer.testing import CliRunner

from indexed.knowledge.commands import remove as remove_cmd
from core.v1.engine.services import CollectionInfo


runner = CliRunner()


def _make_collection(name: str = "docs") -> CollectionInfo:
    return CollectionInfo(
        name=name,
        source_type="localFiles",
        relative_path="/path/to/docs",
        number_of_documents=5,
        number_of_chunks=10,
        disk_size_bytes=1024,
        index_size_bytes=512,
        created_time="2025-01-01T00:00:00Z",
        updated_time="2025-01-02T00:00:00Z",
    )


class TestRemoveCommand:
    """End-to-end-ish tests for the remove CLI behavior."""

    def test_no_collections_prints_message_and_returns(self, monkeypatch):
        """Removing when there are no collections should just show a hint."""
        monkeypatch.setattr(remove_cmd, "inspect", lambda: [])

        result = runner.invoke(remove_cmd.app, ["docs"])

        assert result.exit_code == 0
        assert "No collections found" in result.stdout
        assert "Create collections" in result.stdout

    def test_missing_collection_shows_available_and_exits_1(self, monkeypatch):
        """Trying to remove a missing collection should list available ones and exit 1."""
        monkeypatch.setattr(
            remove_cmd,
            "inspect",
            lambda: [_make_collection("docs"), _make_collection("jira")],
        )

        result = runner.invoke(remove_cmd.app, ["missing"])

        assert result.exit_code == 1
        assert "Collection 'missing' not found" in result.stdout
        assert "Available collections" in result.stdout
        assert "docs" in result.stdout
        assert "jira" in result.stdout

    def test_force_removal_skips_confirmation_and_calls_index_remove(self, monkeypatch):
        """--force should not ask for confirmation and should call Index.remove once."""
        # One existing collection
        monkeypatch.setattr(remove_cmd, "inspect", lambda: [_make_collection("docs")])

        # Fake Index with remove tracking
        class FakeIndex:
            def __init__(self):
                self.removed = []

            def remove(self, name: str) -> None:
                self.removed.append(name)

        fake_index = FakeIndex()
        monkeypatch.setattr(remove_cmd, "Index", lambda: fake_index)

        # Avoid interactive confirmation by forcing
        result = runner.invoke(remove_cmd.app, ["docs", "--force"])

        assert result.exit_code == 0
        assert fake_index.removed == ["docs"]

    def test_cancelled_removal_does_not_call_index_remove(self, monkeypatch):
        """If user declines confirmation, collection should not be removed."""
        monkeypatch.setattr(remove_cmd, "inspect", lambda: [_make_collection("docs")])

        class FakeIndex:
            def __init__(self):
                self.removed = []

            def remove(self, name: str) -> None:
                self.removed.append(name)

        fake_index = FakeIndex()
        monkeypatch.setattr(remove_cmd, "Index", lambda: fake_index)

        # Patch Confirm.ask to simulate user saying "no"
        monkeypatch.setattr(remove_cmd.Confirm, "ask", lambda *a, **k: False)

        result = runner.invoke(remove_cmd.app, ["docs"])

        # Typer.Exit(0) on cancel
        assert result.exit_code == 0
        assert fake_index.removed == []
        assert "Cancelled" in result.stdout

    def test_confirmed_removal_calls_index_remove(self, monkeypatch):
        """If user confirms, collection should be removed exactly once."""
        monkeypatch.setattr(remove_cmd, "inspect", lambda: [_make_collection("docs")])

        class FakeIndex:
            def __init__(self):
                self.removed = []

            def remove(self, name: str) -> None:
                self.removed.append(name)

        fake_index = FakeIndex()
        monkeypatch.setattr(remove_cmd, "Index", lambda: fake_index)

        # Simulate user accepting confirmation
        monkeypatch.setattr(remove_cmd.Confirm, "ask", lambda *a, **k: True)

        result = runner.invoke(remove_cmd.app, ["docs"])

        assert result.exit_code == 0
        assert fake_index.removed == ["docs"]
        assert "Removed" in result.stdout or "removed" in result.stdout
