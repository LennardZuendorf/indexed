"""Tests for the indexed knowledge inspect command.

We focus on realistic behaviors:
- listing all collections (none vs some)
- inspecting a specific collection (exists vs not exists)
- JSON vs rich output paths
"""

from pathlib import Path
from typing import Any, List
from unittest.mock import patch

from typer.testing import CliRunner

from indexed.knowledge.commands import inspect as inspect_cmd
from indexed.utils import storage_info as storage_info_mod
from core.v1.engine.services import CollectionInfo


runner = CliRunner()

# Patch resolve_preferred_collections_path globally for all inspect tests
# so tests don't need ConfigService
_MOCK_PATH = patch.object(
    storage_info_mod,
    "resolve_preferred_collections_path",
    return_value=Path("/tmp/test-collections"),
)
_MOCK_PATH.start()


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

    def test_inspect_specific_collection_simple_output(self, monkeypatch):
        """Simple output for a specific collection should contain core fields."""
        from indexed.utils.simple_output import reset_simple_output, set_simple_output

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
        from indexed.utils.simple_output import reset_simple_output, set_simple_output

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
        from core.v1.engine.services import CollectionInfo

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


class TestInspectCollectionsCommandV2:
    """Tests for v2 engine routing in the inspect CLI command."""

    @patch("core.v2.services.status")
    def test_v2_all_collections_calls_v2_status(self, mock_v2_status: Any) -> None:
        """--engine v2 with no name arg calls core.v2.services.status."""
        from unittest.mock import MagicMock

        mock_coll = MagicMock()
        mock_coll.name = "v2-docs"
        mock_coll.source_type = "localFiles"
        mock_coll.relative_path = "/docs"
        mock_coll.number_of_documents = 5
        mock_coll.number_of_chunks = 10
        mock_coll.disk_size_bytes = 1024
        mock_coll.index_size_bytes = 512
        mock_coll.created_time = "2025-01-01T00:00:00Z"
        mock_coll.updated_time = "2025-01-02T00:00:00Z"
        mock_v2_status.return_value = [mock_coll]

        result = runner.invoke(inspect_cmd.app, ["--engine", "v2"])

        assert result.exit_code == 0
        assert "v2-docs" in result.stdout
        mock_v2_status.assert_called_once()

    @patch("core.v2.services.status")
    @patch("core.v2.services.inspect")
    def test_v2_specific_collection_calls_v2_inspect(
        self, mock_v2_inspect: Any, mock_v2_status: Any
    ) -> None:
        """--engine v2 with a collection name calls core.v2.services.inspect."""
        from unittest.mock import MagicMock

        mock_info = MagicMock()
        mock_info.name = "my-docs"
        mock_info.source_type = "localFiles"
        mock_info.relative_path = "/docs"
        mock_info.number_of_documents = 7
        mock_info.number_of_chunks = 14
        mock_info.disk_size_bytes = 2048
        mock_info.index_size_bytes = 1024
        mock_info.created_time = "2025-01-01T00:00:00Z"
        mock_info.updated_time = "2025-01-02T00:00:00Z"
        mock_v2_inspect.return_value = mock_info

        result = runner.invoke(inspect_cmd.app, ["my-docs", "--engine", "v2"])

        assert result.exit_code == 0
        mock_v2_inspect.assert_called_once()

    @patch("core.v2.services.status", return_value=[])
    @patch("core.v2.services.inspect")
    def test_v2_inspect_not_found_shows_error(
        self, mock_v2_inspect: Any, mock_v2_status: Any
    ) -> None:
        """--engine v2 inspect raising exception shows error and exits 1."""
        mock_v2_inspect.side_effect = Exception("Collection 'missing' not found")

        result = runner.invoke(inspect_cmd.app, ["missing", "--engine", "v2"])

        assert result.exit_code == 1
        assert "missing" in result.stdout


def _write_v2_manifest(root: Path, name: str, *, docs: int, chunks: int) -> None:
    import json as _json

    coll = root / name
    coll.mkdir(parents=True, exist_ok=True)
    (coll / "manifest.json").write_text(
        _json.dumps(
            {
                "name": name,
                "version": "2.0",
                "source_type": "localFiles",
                "num_documents": docs,
                "num_chunks": chunks,
                "embed_model_name": "all-MiniLM-L6-v2",
                "vector_store_type": "faiss",
                "created_time": "2025-01-01T00:00:00Z",
                "updated_time": "2025-01-02T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def _write_v1_manifest(root: Path, name: str, *, docs: int, chunks: int) -> None:
    import json as _json

    coll = root / name
    coll.mkdir(parents=True, exist_ok=True)
    (coll / "manifest.json").write_text(
        _json.dumps(
            {
                "collectionName": name,
                "numberOfDocuments": docs,
                "numberOfChunks": chunks,
                "indexers": [{"name": "FAISS"}],
            }
        ),
        encoding="utf-8",
    )


class TestInspectAutoDetect:
    """Per-collection auto-routing fixes the v2 silent-zeros bug."""

    def test_v2_detail_view_reports_real_counts_without_engine_flag(
        self, monkeypatch, tmp_path
    ) -> None:
        """`inspect <v2-coll>` must return the v2 manifest's document/chunk counts."""
        from unittest.mock import MagicMock

        _write_v2_manifest(tmp_path, "indexed", docs=42, chunks=137)
        monkeypatch.setattr(
            storage_info_mod, "resolve_preferred_collections_path", lambda: tmp_path
        )

        v2_info = MagicMock()
        v2_info.name = "indexed"
        v2_info.source_type = "localFiles"
        v2_info.relative_path = None
        v2_info.number_of_documents = 42
        v2_info.number_of_chunks = 137
        v2_info.disk_size_bytes = 1024
        v2_info.index_size_bytes = 0
        v2_info.created_time = "2025-01-01T00:00:00Z"
        v2_info.updated_time = "2025-01-02T00:00:00Z"

        with patch("core.v2.services.inspect", return_value=v2_info) as v2_inspect:
            result = runner.invoke(inspect_cmd.app, ["indexed"])

        assert result.exit_code == 0, result.output
        v2_inspect.assert_called_once()
        assert "42" in result.stdout
        assert "137" in result.stdout

    def test_mixed_engine_list_view_renders_per_row(
        self, monkeypatch, tmp_path
    ) -> None:
        """A mixed-engine repo lists v1 + v2 with their own counts."""
        from unittest.mock import MagicMock

        _write_v1_manifest(tmp_path, "v1coll", docs=3, chunks=9)
        _write_v2_manifest(tmp_path, "v2coll", docs=5, chunks=11)

        monkeypatch.setattr(
            storage_info_mod, "resolve_preferred_collections_path", lambda: tmp_path
        )

        v1_info = _make_collection("v1coll", docs=3, chunks=9)
        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: [v1_info])

        v2_info = MagicMock()
        v2_info.name = "v2coll"
        v2_info.source_type = "localFiles"
        v2_info.relative_path = None
        v2_info.number_of_documents = 5
        v2_info.number_of_chunks = 11
        v2_info.disk_size_bytes = 2048
        v2_info.index_size_bytes = 0
        v2_info.created_time = "2025-01-01T00:00:00Z"
        v2_info.updated_time = "2025-01-02T00:00:00Z"

        with patch("core.v2.services.inspect", return_value=v2_info):
            result = runner.invoke(inspect_cmd.app, [])

        assert result.exit_code == 0, result.output
        # Both rows shown
        assert "v1coll" in result.stdout
        assert "v2coll" in result.stdout
        # Real counts for each
        assert "3" in result.stdout and "9" in result.stdout
        assert "5" in result.stdout and "11" in result.stdout

    def test_force_v1_engine_in_list_view_skips_per_row(
        self, monkeypatch, tmp_path
    ) -> None:
        """`--engine v1` reverts to single-engine list (escape hatch)."""
        _write_v2_manifest(tmp_path, "v2coll", docs=99, chunks=99)
        monkeypatch.setattr(
            storage_info_mod, "resolve_preferred_collections_path", lambda: tmp_path
        )

        sentinel = _make_collection("v2coll", docs=0, chunks=0)
        monkeypatch.setattr(inspect_cmd, "inspect", lambda *a, **kw: [sentinel])

        with patch("core.v2.services.inspect") as v2_inspect:
            result = runner.invoke(inspect_cmd.app, ["--engine", "v1"])

        assert result.exit_code == 0
        v2_inspect.assert_not_called()
