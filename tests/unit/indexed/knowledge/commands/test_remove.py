"""Tests for the indexed knowledge remove command.

We focus on realistic behaviors:
- removing from an empty index
- trying to remove a missing collection
- confirmation flow with and without --force
- simple output JSON mode
- verbose mode removal path
- removal failure handling
"""

from typing import Any

from typer.testing import CliRunner

from indexed.knowledge.commands import remove as remove_cmd
from core.v1.engine.services import CollectionInfo
from indexed.utils.simple_output import set_simple_output, reset_simple_output


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
        assert "Get started" in result.stdout

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

    def test_simple_output_removal_returns_json(self, monkeypatch):
        """In simple output mode, removal should return JSON status."""
        import json

        monkeypatch.setattr(remove_cmd, "inspect", lambda: [_make_collection("docs")])

        class FakeIndex:
            def remove(self, name: str) -> None:
                pass

        monkeypatch.setattr(remove_cmd, "Index", lambda: FakeIndex())

        set_simple_output(True)
        try:
            result = runner.invoke(remove_cmd.app, ["docs"])
            assert result.exit_code == 0
            parsed = json.loads(result.stdout)
            assert parsed["status"] == "removed"
            assert parsed["collection"] == "docs"
        finally:
            reset_simple_output()

    def test_simple_output_removal_error_returns_json(self, monkeypatch):
        """In simple output mode, removal error should return JSON error."""
        import json

        monkeypatch.setattr(remove_cmd, "inspect", lambda: [_make_collection("docs")])

        class FakeIndex:
            def remove(self, name: str) -> None:
                raise RuntimeError("disk full")

        monkeypatch.setattr(remove_cmd, "Index", lambda: FakeIndex())

        set_simple_output(True)
        try:
            result = runner.invoke(remove_cmd.app, ["docs"])
            assert result.exit_code == 1
            parsed = json.loads(result.stdout)
            assert parsed["status"] == "error"
            assert "disk full" in parsed["error"]
        finally:
            reset_simple_output()

    def test_verbose_mode_removal(self, monkeypatch):
        """In verbose mode, removal should use NoOpContext path."""
        monkeypatch.setattr(remove_cmd, "inspect", lambda: [_make_collection("docs")])
        monkeypatch.setattr(remove_cmd, "is_verbose_mode", lambda: True)

        class FakeIndex:
            def __init__(self):
                self.removed = []

            def remove(self, name: str) -> None:
                self.removed.append(name)

        fake_index = FakeIndex()
        monkeypatch.setattr(remove_cmd, "Index", lambda: fake_index)

        result = runner.invoke(remove_cmd.app, ["docs", "--force"])

        assert result.exit_code == 0
        assert fake_index.removed == ["docs"]

    def test_removal_exception_shows_error(self, monkeypatch):
        """When index.remove raises, error should be displayed and exit 1."""
        monkeypatch.setattr(remove_cmd, "inspect", lambda: [_make_collection("docs")])

        class FakeIndex:
            def remove(self, name: str) -> None:
                raise RuntimeError("permission denied")

        monkeypatch.setattr(remove_cmd, "Index", lambda: FakeIndex())

        result = runner.invoke(remove_cmd.app, ["docs", "--force"])

        assert result.exit_code == 1
        assert "Failed to remove" in result.stdout
        assert "permission denied" in result.stdout


class TestRemoveCommandV2:
    """Tests for v2 engine routing in the remove CLI command."""

    def _make_v2_collection(self, name: str = "docs") -> "CollectionInfo":
        """Build a CollectionInfo compatible with both v1 and v2 display logic."""
        return _make_collection(name)

    def test_v2_no_collections_exits_cleanly(self, monkeypatch: "Any") -> None:
        """--engine v2 with no collections shows friendly message."""
        from unittest.mock import patch

        with patch("core.v2.services.status", return_value=[]):
            monkeypatch.setattr(remove_cmd, "Index", lambda: None)
            result = runner.invoke(remove_cmd.app, ["docs", "--engine", "v2"])

        assert result.exit_code == 0
        assert "No collections found" in result.stdout

    def test_v2_force_calls_v2_clear(self, monkeypatch: "Any") -> None:
        """--engine v2 --force calls core.v2.services.clear with collection name."""
        from unittest.mock import patch, MagicMock

        mock_coll = _make_collection("docs")

        v2_clear_calls = []

        def fake_v2_clear(names, collections_dir=None):  # type: ignore[no-untyped-def]
            v2_clear_calls.extend(names)

        with patch("core.v2.services.status", return_value=[mock_coll]):
            with patch("core.v2.services.clear", side_effect=fake_v2_clear):
                monkeypatch.setattr(remove_cmd, "Index", lambda: MagicMock())
                result = runner.invoke(
                    remove_cmd.app, ["docs", "--engine", "v2", "--force"]
                )

        assert result.exit_code == 0
        assert "docs" in v2_clear_calls

    def test_v2_simple_output_calls_v2_clear_and_returns_json(
        self, monkeypatch: "Any"
    ) -> None:
        """--engine v2 in simple-output mode calls v2_clear and returns JSON."""
        from unittest.mock import patch, MagicMock

        mock_coll = _make_collection("docs")

        set_simple_output(True)
        try:
            with patch("core.v2.services.status", return_value=[mock_coll]):
                with patch("core.v2.services.clear", return_value=None):
                    monkeypatch.setattr(remove_cmd, "Index", lambda: MagicMock())
                    result = runner.invoke(remove_cmd.app, ["docs", "--engine", "v2"])
        finally:
            reset_simple_output()

        import json

        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["status"] == "removed"
        assert parsed["collection"] == "docs"
