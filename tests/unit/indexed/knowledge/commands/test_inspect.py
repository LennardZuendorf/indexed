"""Tests for the indexed knowledge inspect command.

We focus on realistic behaviors:
- listing all collections (none vs some)
- inspecting a specific collection (exists vs not exists)
- JSON vs rich output paths
"""

from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from indexed.cli.knowledge.commands import inspect as inspect_cmd
from indexed.core.engine import EngineDescriptor
from indexed.core.v1.engine.services import CollectionInfo


runner = CliRunner()


def _mock_runtime_context():
    mock_config = MagicMock()
    mock_config.resolve_storage_mode.return_value = "global"
    mock_config.get_workspace_preference.return_value = None
    mock_config.store.read.return_value = {}
    return type(
        "MockCtx",
        (),
        {
            "collections_path": Path("/tmp/test-collections"),
            "mode": "global",
            "config_service": mock_config,
        },
    )()


@pytest.fixture(autouse=True)
def _patch_runtime_context():
    with (
        patch(
            "indexed.cli.composition.resolve_collections_context",
            side_effect=lambda *args, **kwargs: _mock_runtime_context(),
        ),
        patch(
            "indexed.cli.utils.storage_info.display_storage_mode_for_command",
            lambda *args, **kwargs: None,
        ),
    ):
        yield


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
        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: [])

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

        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: collections)

        result = runner.invoke(inspect_cmd.app, [])

        assert result.exit_code == 0
        assert "docs" in result.stdout
        assert "jira" in result.stdout
        # Total summary line
        assert "total" in result.stdout.lower()

    def test_inspect_specific_collection_not_found(self, monkeypatch):
        """Inspecting a missing collection should show available ones and exit 1."""

        # First call: inspect([name]) returns empty list
        def fake_inspect(names=None, **kwargs):
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

    def test_inspect_corrupt_collection_reports_unreadable(self, monkeypatch, tmp_path):
        """A collection present on disk with a corrupt/unreadable manifest must
        be reported honestly (and exit non-zero) — ``inspect()`` OMITS it
        (foundation/6 E1), so it must not be misreported as "not found"
        (foundation/6 regression fix)."""
        collections_dir = tmp_path / "collections"
        collections_dir.mkdir()
        corrupt_dir = collections_dir / "corrupt-coll"
        corrupt_dir.mkdir()
        (corrupt_dir / "manifest.json").write_text("{ not valid json")

        ctx = type("Ctx", (), {"collections_path": collections_dir})()
        monkeypatch.setattr(
            "indexed.cli.composition.resolve_collections_context", lambda *a, **kw: ctx
        )

        result = runner.invoke(inspect_cmd.app, ["corrupt-coll"])

        assert result.exit_code != 0
        assert "not found" not in result.stdout.lower()
        assert (
            "corrupt" in result.stdout.lower() or "unreadable" in result.stdout.lower()
        )

    def test_inspect_specific_collection_simple_output(self, monkeypatch):
        """Simple output for a specific collection should contain core fields."""
        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        coll = _make_collection("docs")

        def fake_inspect(names=None, **kwargs):
            if names:
                return [coll]
            return [coll]

        monkeypatch.setattr(inspect_cmd, "inspect", fake_inspect)
        set_simple_output(True)

        try:
            result = runner.invoke(inspect_cmd.app, ["docs"])

            assert result.exit_code == 0
            assert '"name": "docs"' in result.stdout
            assert "number_of_documents" in result.stdout
            assert "number_of_chunks" in result.stdout
        finally:
            reset_simple_output()

    def test_inspect_all_collections_simple_output(self, monkeypatch):
        """Simple output for all collections should be a list of objects."""
        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        colls = [_make_collection("docs"), _make_collection("jira")]

        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: colls)
        set_simple_output(True)

        try:
            result = runner.invoke(inspect_cmd.app, [])

            assert result.exit_code == 0
            # Should show a JSON array with at least one of the names
            assert result.stdout.strip().startswith("[")
            assert '"docs"' in result.stdout or '"jira"' in result.stdout
        finally:
            reset_simple_output()

    def test_inspect_specific_collection_rich_output(self, monkeypatch):
        """Inspecting a specific collection without --json shows rich panel output."""
        coll = _make_collection("docs")

        def fake_inspect(names=None, **kwargs):
            return [coll]

        monkeypatch.setattr(inspect_cmd, "inspect", fake_inspect)

        result = runner.invoke(inspect_cmd.app, ["docs"])

        assert result.exit_code == 0
        assert "docs" in result.stdout

    def test_list_all_collections_verbose(self, monkeypatch):
        """Listing with --verbose shows verbose detail for each collection."""
        collections = [
            _make_collection("docs", docs=3, chunks=5),
            _make_collection("jira", source_type="jira", docs=2, chunks=4),
        ]

        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: collections)

        result = runner.invoke(inspect_cmd.app, ["--verbose"])

        assert result.exit_code == 0
        assert "docs" in result.stdout
        assert "jira" in result.stdout

    def test_verbose_list_single_collection(self, monkeypatch):
        """Verbose list with one collection uses singular 'Collection'."""
        collections = [_make_collection("docs")]

        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: collections)

        result = runner.invoke(inspect_cmd.app, ["--verbose"])

        assert result.exit_code == 0
        assert "docs" in result.stdout

    def test_inspect_specific_collection_found_with_documents(self, monkeypatch):
        """Inspecting a found collection with documents should display it."""
        coll = _make_collection("docs", docs=5, chunks=10)

        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: [coll])

        result = runner.invoke(inspect_cmd.app, ["docs"])

        assert result.exit_code == 0

    def test_verbose_list_with_size_info(self, monkeypatch):
        """Verbose listing should include size information when disk_size_bytes is set."""
        from indexed.core.v1.engine.services import CollectionInfo

        coll = CollectionInfo(
            name="sized-collection",
            source_type="localFiles",
            relative_path="/data",
            number_of_documents=10,
            number_of_chunks=20,
            disk_size_bytes=2048,
            index_size_bytes=1024,
            created_time="2025-01-01T00:00:00Z",
            updated_time="2025-01-02T00:00:00Z",
        )

        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: [coll])

        result = runner.invoke(inspect_cmd.app, ["--verbose"])

        assert result.exit_code == 0
        assert "sized-collection" in result.stdout


class TestInspectEngineDiagnostics:
    """R13 — inspect shows each collection's engine version, and a v2 row shows
    its embedding model/provider and store type. Additive: v1 rows keep their
    existing lines (R6)."""

    def test_v2_rich_shows_engine_model_and_store(self, monkeypatch):
        coll = _make_collection("v2c")
        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: [coll])
        monkeypatch.setattr(
            inspect_cmd,
            "engine_descriptors",
            lambda *a, **kw: [
                EngineDescriptor(
                    name="v2c",
                    engine_version="2",
                    embedding_model="all-MiniLM-L6-v2",
                    embedding_provider="local",
                    vector_store="simple",
                )
            ],
        )

        result = runner.invoke(inspect_cmd.app, ["v2c"])

        assert result.exit_code == 0, result.stdout
        assert "Engine" in result.stdout
        assert "v2" in result.stdout
        assert "simple" in result.stdout

    def test_v1_rich_shows_engine_v1(self, monkeypatch):
        coll = _make_collection("v1c")
        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: [coll])
        monkeypatch.setattr(
            inspect_cmd,
            "engine_descriptors",
            lambda *a, **kw: [
                EngineDescriptor(name="v1c", engine_version="1", vector_store="faiss")
            ],
        )

        result = runner.invoke(inspect_cmd.app, ["v1c"])

        assert result.exit_code == 0, result.stdout
        assert "v1" in result.stdout

    def test_simple_output_carries_engine_fields(self, monkeypatch):
        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        coll = _make_collection("v2c")
        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: [coll])
        monkeypatch.setattr(
            inspect_cmd,
            "engine_descriptors",
            lambda *a, **kw: [
                EngineDescriptor(
                    name="v2c",
                    engine_version="2",
                    embedding_model="all-MiniLM-L6-v2",
                    embedding_provider="local",
                    vector_store="simple",
                )
            ],
        )
        set_simple_output(True)
        try:
            result = runner.invoke(inspect_cmd.app, ["v2c"])
            assert result.exit_code == 0
            assert '"engine": "2"' in result.stdout
            assert '"vector_store": "simple"' in result.stdout
            assert '"embedding_provider": "local"' in result.stdout
        finally:
            reset_simple_output()

    def test_list_mixed_engines_shows_both(self, monkeypatch):
        colls = [_make_collection("v1c"), _make_collection("v2c")]
        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: colls)
        monkeypatch.setattr(
            inspect_cmd,
            "engine_descriptors",
            lambda *a, **kw: [
                EngineDescriptor(name="v1c", engine_version="1", vector_store="faiss"),
                EngineDescriptor(
                    name="v2c",
                    engine_version="2",
                    embedding_model="all-MiniLM-L6-v2",
                    embedding_provider="local",
                    vector_store="simple",
                ),
            ],
        )

        result = runner.invoke(inspect_cmd.app, [])

        assert result.exit_code == 0, result.stdout
        assert "v1c" in result.stdout and "v2c" in result.stdout
        assert "simple" in result.stdout


class TestInspectMarkupSafety:
    """R7 — collection names are user-controlled and must render literally,
    never be parsed as Rich markup, in the "X Collection Details:" heading
    and the "Available collections" listing."""

    def test_available_collections_listing_renders_brackets_literally(
        self, monkeypatch
    ):
        """A missing named collection lists existing ones —
        ``console.print(f"  • {coll.name}")`` — a bracketed collection name
        must not be dropped/crash. (Rich's markup tag grammar only matches
        a bracket run starting with a lowercase letter/#//@ — "docs[x]", not
        a digit like "docs[1]" — so the fixture must start with a letter to
        actually exercise the parser.)"""

        def fake_inspect(names=None, **kwargs):
            if names:
                return []
            return [_make_collection("docs[x]")]

        monkeypatch.setattr(inspect_cmd, "inspect", fake_inspect)

        result = runner.invoke(inspect_cmd.app, ["missing"])

        assert result.exit_code == 1
        assert "docs[x]" in result.stdout

    def test_collection_details_heading_renders_brackets_literally(self, monkeypatch):
        """``format_collection_detail`` embeds the raw collection name
        inside the app's own markup tags — a bracketed name must render
        literally rather than being parsed as (or breaking) those tags.

        Asserts the exact heading line (not just "my[coll]" anywhere in
        stdout): the detail card below it already renders the name safely
        via the pre-existing ``Text()``-wrapped title idiom, so a looser
        assertion would pass even with the heading sink unfixed.
        """
        coll = _make_collection("my[coll]")

        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: [coll])

        result = runner.invoke(inspect_cmd.app, ["my[coll]"])

        assert result.exit_code == 0, result.stdout
        assert "my[coll] Collection Details:" in result.stdout


class TestInspectListViewPathRendering:
    """rendering-fixes/5 R7 — the list view's Path row must not
    ellipsis-truncate a value the detail view renders in full. Columns
    squeezes each card to roughly terminal_width / N, and the ratio=2 value
    column used to fall back to Rich's default single-line ellipsis overflow
    (``create_info_rows_with_spacing`` in cards.py)."""

    # A path long enough to overflow the squeezed value column of a 3-card
    # row at a realistic terminal width. The exact fold point shifts a
    # character or two between the list view's per-panel width and the
    # detail view's card width, so assertions key off a short marker at the
    # very end of the path (never itself split further) rather than the
    # full string.
    _LONG_PATH = (
        "/home/user/projects/some-org/some-really-long-repository-name/"
        "docs/subfolder-xyz789"
    )
    _TAIL_MARKER = "xyz789"

    @staticmethod
    def _collection(name: str, relative_path: str) -> CollectionInfo:
        return CollectionInfo(
            name=name,
            source_type="localFiles",
            relative_path=relative_path,
            number_of_documents=3,
            number_of_chunks=5,
            disk_size_bytes=1024,
            index_size_bytes=512,
            created_time="2025-01-01T00:00:00Z",
            updated_time="2025-01-02T00:00:00Z",
        )

    def test_list_view_long_path_not_truncated(self, monkeypatch):
        """Three collections listed together (no name arg): the long path
        must render in full (wrapped, never mid-word-ellipsis-truncated)
        even though ``Columns(equal=True)`` squeezes each card to roughly a
        third of the terminal width."""
        collections = [
            self._collection("alpha", self._LONG_PATH),
            self._collection("beta", "/short/path"),
            self._collection("gamma", "/another/short/path"),
        ]
        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: collections)

        wide_runner = CliRunner(env={"COLUMNS": "100"})
        result = wide_runner.invoke(inspect_cmd.app, [])

        assert result.exit_code == 0, result.stdout
        assert "…" not in result.stdout
        assert self._TAIL_MARKER in result.stdout

    def test_detail_view_long_path_not_truncated(self, monkeypatch):
        """Same long path via ``index inspect <name>`` (detail view, single
        card, never ``Columns``-wrapped) — the shared row renderer must not
        ellipsis-truncate it there either."""
        coll = self._collection("alpha", self._LONG_PATH)
        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: [coll])

        wide_runner = CliRunner(env={"COLUMNS": "100"})
        result = wide_runner.invoke(inspect_cmd.app, ["alpha"])

        assert result.exit_code == 0, result.stdout
        assert "…" not in result.stdout
        assert self._TAIL_MARKER in result.stdout

    def test_list_view_short_path_layout_unaffected(self, monkeypatch):
        """Short values keep the existing single-line, side-by-side card
        layout — the fold override must be a no-op when nothing overflows.
        Three collections (not two) to match the width the long-path case
        above already proved clean — a 2-card row at this width squeezes the
        unrelated *label* column enough to ellipsis "Documents" on its own,
        a pre-existing characteristic of that column this task doesn't
        touch."""
        collections = [
            self._collection("alpha", "/short/path"),
            self._collection("beta", "/short/path2"),
            self._collection("gamma", "/another/short/path"),
        ]
        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: collections)

        wide_runner = CliRunner(env={"COLUMNS": "100"})
        result = wide_runner.invoke(inspect_cmd.app, [])

        assert result.exit_code == 0, result.stdout
        assert "…" not in result.stdout
        assert "/short/path" in result.stdout
        assert "/short/path2" in result.stdout
        assert "/another/short/path" in result.stdout
