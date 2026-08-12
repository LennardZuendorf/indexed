"""Tests for the indexed knowledge remove command.

We focus on realistic behaviors:
- removing from an empty index
- trying to remove a missing collection
- confirmation flow with and without --force
- simple output JSON mode
- verbose mode removal path
- removal failure handling
"""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from indexed.cli.knowledge.commands import remove as remove_cmd
from indexed.core.v1.engine.services import CollectionInfo
from indexed.cli.utils.simple_output import set_simple_output, reset_simple_output
from tests.unit.indexed.conftest import make_cli_context


runner = CliRunner()


@pytest.fixture(autouse=True)
def _patch_runtime_context():
    with (
        patch(
            "indexed.cli.composition.resolve_collections_context",
            side_effect=lambda *args, **kwargs: make_cli_context(),
        ),
    ):
        yield


def _make_corrupt_test_ctx(collections_dir):
    """Build a CliContext stand-in pointed at a real tmp collections dir.

    ``display_storage_mode_for_command`` re-imports and calls
    ``resolve_collections_context`` fresh at call time (lazy import), so
    overriding the module-level function also affects that second call — the
    stand-in needs the same shape (``config_service.load_raw``) it expects.
    """
    from unittest.mock import MagicMock

    mock_config = MagicMock()
    mock_config.load_raw.return_value = {}
    return type(
        "Ctx",
        (),
        {
            "collections_path": collections_dir,
            "mode": "local",
            "config_service": mock_config,
        },
    )()


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
        monkeypatch.setattr(remove_cmd, "inspect", lambda **kwargs: [])

        result = runner.invoke(remove_cmd.app, ["docs"])

        assert result.exit_code == 0
        assert "No collections found" in result.stdout
        assert "Get started" in result.stdout

    def test_missing_collection_shows_available_and_exits_1(self, monkeypatch):
        """Trying to remove a missing collection should list available ones and exit 1."""
        monkeypatch.setattr(
            remove_cmd,
            "inspect",
            lambda **kwargs: [_make_collection("docs"), _make_collection("jira")],
        )

        result = runner.invoke(remove_cmd.app, ["missing"])

        assert result.exit_code == 1
        assert "Collection 'missing' not found" in result.stdout
        assert "Available collections" in result.stdout
        assert "docs" in result.stdout
        assert "jira" in result.stdout

    def test_force_removal_skips_confirmation_and_calls_index_remove(self, monkeypatch):
        """--force should not ask for confirmation and should call clear once."""
        # One existing collection
        monkeypatch.setattr(
            remove_cmd, "inspect", lambda **kwargs: [_make_collection("docs")]
        )

        cleared = []

        def fake_clear(collections, **kwargs):
            cleared.extend(collections)

        monkeypatch.setattr(remove_cmd, "clear", fake_clear)

        # Avoid interactive confirmation by forcing
        result = runner.invoke(remove_cmd.app, ["docs", "--force"])

        assert result.exit_code == 0
        assert cleared == ["docs"]

    def test_cancelled_removal_does_not_call_index_remove(self, monkeypatch):
        """If user declines confirmation, collection should not be removed."""
        monkeypatch.setattr(
            remove_cmd, "inspect", lambda **kwargs: [_make_collection("docs")]
        )

        cleared = []

        def fake_clear(collections, **kwargs):
            cleared.extend(collections)

        monkeypatch.setattr(remove_cmd, "clear", fake_clear)

        # Patch Confirm.ask to simulate user saying "no"
        monkeypatch.setattr(remove_cmd.Confirm, "ask", lambda *a, **k: False)

        result = runner.invoke(remove_cmd.app, ["docs"])

        # Typer.Exit(0) on cancel
        assert result.exit_code == 0
        assert cleared == []
        assert "Cancelled" in result.stdout

    def test_confirmed_removal_calls_index_remove(self, monkeypatch):
        """If user confirms, collection should be removed exactly once."""
        monkeypatch.setattr(
            remove_cmd, "inspect", lambda **kwargs: [_make_collection("docs")]
        )

        cleared = []

        def fake_clear(collections, **kwargs):
            cleared.extend(collections)

        monkeypatch.setattr(remove_cmd, "clear", fake_clear)

        # Simulate user accepting confirmation
        monkeypatch.setattr(remove_cmd.Confirm, "ask", lambda *a, **k: True)

        result = runner.invoke(remove_cmd.app, ["docs"])

        assert result.exit_code == 0
        assert cleared == ["docs"]
        assert "Removed" in result.stdout or "removed" in result.stdout

    def test_simple_output_removal_returns_json(self, monkeypatch):
        """In simple output mode, removal should return JSON status."""
        import json

        monkeypatch.setattr(
            remove_cmd, "inspect", lambda **kwargs: [_make_collection("docs")]
        )

        def fake_clear(collections, **kwargs):
            pass

        monkeypatch.setattr(remove_cmd, "clear", fake_clear)

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

        monkeypatch.setattr(
            remove_cmd, "inspect", lambda **kwargs: [_make_collection("docs")]
        )

        def fake_clear(collections, **kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(remove_cmd, "clear", fake_clear)

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
        monkeypatch.setattr(
            remove_cmd, "inspect", lambda **kwargs: [_make_collection("docs")]
        )
        monkeypatch.setattr(remove_cmd, "is_verbose_mode", lambda: True)

        cleared = []

        def fake_clear(collections, **kwargs):
            cleared.extend(collections)

        monkeypatch.setattr(remove_cmd, "clear", fake_clear)

        result = runner.invoke(remove_cmd.app, ["docs", "--force"])

        assert result.exit_code == 0
        assert cleared == ["docs"]

    def test_removal_exception_shows_error(self, monkeypatch):
        """When clear raises, error should be displayed and exit 1."""
        monkeypatch.setattr(
            remove_cmd, "inspect", lambda **kwargs: [_make_collection("docs")]
        )

        def fake_clear(collections, **kwargs):
            raise RuntimeError("permission denied")

        monkeypatch.setattr(remove_cmd, "clear", fake_clear)

        result = runner.invoke(remove_cmd.app, ["docs", "--force"])

        assert result.exit_code == 1
        assert "Failed to remove" in result.stdout
        assert "permission denied" in result.stdout

    def test_remove_corrupt_collection_deletes_directory(self, monkeypatch, tmp_path):
        """A collection present on disk with a corrupt/unreadable manifest must
        still be removable — ``inspect()`` OMITS it (foundation/6 E1), so the
        normal name lookup can't find it, but the on-disk fallback must let
        ``remove`` delete the directory instead of reporting "not found"
        (foundation/6 regression fix)."""
        collections_dir = tmp_path / "collections"
        collections_dir.mkdir()
        corrupt_dir = collections_dir / "corrupt-coll"
        corrupt_dir.mkdir()
        (corrupt_dir / "manifest.json").write_text("{ not valid json")

        ctx = _make_corrupt_test_ctx(collections_dir)
        monkeypatch.setattr(
            "indexed.cli.composition.resolve_collections_context", lambda *a, **kw: ctx
        )

        result = runner.invoke(remove_cmd.app, ["corrupt-coll", "--force"])

        assert result.exit_code == 0, result.stdout
        assert not corrupt_dir.exists(), (
            "the corrupt collection directory must actually be deleted"
        )

    def test_remove_corrupt_collection_simple_output(self, monkeypatch, tmp_path):
        """Simple output mode must also delete a corrupt collection and report
        it via JSON rather than a plain-text "not found"."""
        import json

        collections_dir = tmp_path / "collections"
        collections_dir.mkdir()
        corrupt_dir = collections_dir / "corrupt-coll"
        corrupt_dir.mkdir()
        (corrupt_dir / "manifest.json").write_text("{ not valid json")

        ctx = _make_corrupt_test_ctx(collections_dir)
        monkeypatch.setattr(
            "indexed.cli.composition.resolve_collections_context", lambda *a, **kw: ctx
        )

        set_simple_output(True)
        try:
            result = runner.invoke(remove_cmd.app, ["corrupt-coll"])
        finally:
            reset_simple_output()

        assert result.exit_code == 0, result.stdout
        assert not corrupt_dir.exists()
        parsed = json.loads(result.stdout)
        assert parsed["status"] == "removed"
        assert parsed["collection"] == "corrupt-coll"


class TestRemoveMarkupSafety:
    """R7 — collection names are user-controlled and must render literally,
    never be parsed as Rich markup, in the "Removing ... Collection:" heading
    and the "Available collections" listing."""

    def test_available_collections_listing_renders_brackets_literally(
        self, monkeypatch
    ):
        """Trying to remove a missing collection lists existing ones —
        ``console.print(f"  • {coll.name}")`` — a bracketed collection name
        must not be dropped/crash. (Rich's markup tag grammar only matches
        a bracket run starting with a lowercase letter/#//@ — "docs[x]", not
        a digit like "docs[1]" — so the fixture must start with a letter to
        actually exercise the parser.)"""
        monkeypatch.setattr(
            remove_cmd, "inspect", lambda **kwargs: [_make_collection("docs[x]")]
        )

        result = runner.invoke(remove_cmd.app, ["missing"])

        assert result.exit_code == 1
        assert "docs[x]" in result.stdout

    def test_removing_heading_renders_brackets_literally(self, monkeypatch):
        """The "Removing X Collection:" heading embeds the raw collection
        name inside the app's own markup tags — a bracketed name must render
        literally rather than being parsed as (or breaking) those tags.

        Asserts the exact heading line (not just "my[coll]" anywhere in
        stdout): the later detail card / success message already render the
        name safely via the pre-existing ``Text()``-wrapped idiom, so a
        looser assertion would pass even with the heading sink unfixed.
        """
        monkeypatch.setattr(
            remove_cmd, "inspect", lambda **kwargs: [_make_collection("my[coll]")]
        )
        monkeypatch.setattr(remove_cmd, "clear", lambda *a, **kw: None)

        result = runner.invoke(remove_cmd.app, ["my[coll]", "--force"])

        assert result.exit_code == 0, result.stdout
        assert "Removing my[coll] Collection:" in result.stdout
