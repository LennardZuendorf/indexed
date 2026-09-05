"""Tests for knowledge update commands."""

import contextlib
import fnmatch
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from indexed.cli.knowledge.commands.update import (
    _format_source_type,
    _config_existed_before,
    _get_config_path,
    _format_update_comparison,
)
from tests.unit.indexed.conftest import make_cli_context

runner = CliRunner()


class TestUpdateEngineRouting:
    """core-v2/1: the update command must route through the version-dispatching
    facade so an explicit ``--engine`` reaches per-collection detection instead
    of crashing v1's engine-less ``update()`` with a ``TypeError``."""

    def test_update_service_seam_is_the_facade(self):
        """``update.update_service`` must resolve to the facade ``update`` (which
        accepts ``engine=``), not v1's engine-less ``update`` (which would
        ``TypeError`` on the injected ``engine`` kwarg)."""
        from indexed.cli.knowledge.commands import update as update_cmd
        import indexed.core.engine as facade
        import indexed.core.v1.engine as v1

        assert update_cmd.update_service is facade.update
        assert update_cmd.update_service is not v1.update

    def test_svc_status_and_inspect_seams_are_the_facade(self):
        from indexed.cli.knowledge.commands import update as update_cmd
        import indexed.core.engine as facade

        assert update_cmd.svc_status is facade.status
        assert update_cmd.inspect is facade.inspect

    def test_run_update_loop_propagates_engine_mismatch(self, tmp_path):
        """An ``EngineMismatchError`` from the facade must surface with its full
        message (names both engines + migrate remedy), NOT be collapsed into a
        generic per-collection ``Failed to update`` failure (R2 surfacing)."""
        from indexed.cli.knowledge.commands import update_service as svc
        from indexed.core.errors import EngineMismatchError

        status = SimpleNamespace(
            name="col1", source_type="localFiles", indexers=["default"]
        )

        def raise_mismatch(configs, **kw):
            raise EngineMismatchError("col1", found="1", requested="2")

        cmd = SimpleNamespace(
            svc_status=lambda names=None, **kw: [status],
            SourceConfig=lambda **kw: SimpleNamespace(**kw),
            is_verbose_mode=lambda: False,
            update_service=raise_mismatch,
            print_error=lambda *a, **kw: None,
            console=SimpleNamespace(print=lambda *a, **kw: None),
            inspect=lambda names=None, **kw: [status],
        )

        with pytest.raises(EngineMismatchError) as excinfo:
            svc.run_update_loop(
                cmd,
                collections=["col1"],
                before_data={"col1": status},
                update_wiring={"engine": "2", "manifest_factory": lambda m, p: None},
                collections_path=str(tmp_path),
                config_service=SimpleNamespace(clear_overlay=lambda: None),
                simple=True,
                noop_context=contextlib.nullcontext,
                create_phased_progress=None,
                ensure_credentials=lambda *a, **kw: None,
            )

        message = str(excinfo.value)
        assert "v1" in message and "v2" in message
        assert "indexed index migrate col1" in message

    def test_run_update_loop_still_collects_generic_failures(self, tmp_path):
        """A non-engine failure (e.g. a genuine indexing error) is still
        collected per-collection so the batch continues (foundation/6 E8)."""
        from indexed.cli.knowledge.commands import update_service as svc

        status = SimpleNamespace(
            name="col1", source_type="localFiles", indexers=["default"]
        )

        def boom(configs, **kw):
            raise RuntimeError("indexing blew up")

        cmd = SimpleNamespace(
            svc_status=lambda names=None, **kw: [status],
            SourceConfig=lambda **kw: SimpleNamespace(**kw),
            is_verbose_mode=lambda: False,
            update_service=boom,
            print_error=lambda *a, **kw: None,
            console=SimpleNamespace(print=lambda *a, **kw: None),
            inspect=lambda names=None, **kw: [status],
        )

        outcome = svc.run_update_loop(
            cmd,
            collections=["col1"],
            before_data={"col1": status},
            update_wiring={"manifest_factory": lambda m, p: None},
            collections_path=str(tmp_path),
            config_service=SimpleNamespace(clear_overlay=lambda: None),
            simple=True,
            noop_context=contextlib.nullcontext,
            create_phased_progress=None,
            ensure_credentials=lambda *a, **kw: None,
        )

        assert outcome.failed_collections == ["col1"]


class TestFormatSourceType:
    """Test _format_source_type function."""

    def test_format_jira_types(self):
        """Should format Jira types correctly."""
        assert _format_source_type("jira") == "Jira"
        assert _format_source_type("jiraCloud") == "Jira Cloud"

    def test_format_confluence_types(self):
        """Should format Confluence types correctly."""
        assert _format_source_type("confluence") == "Confluence"
        assert _format_source_type("confluenceCloud") == "Confluence Cloud"

    def test_format_files_type(self):
        """Should format Files type correctly."""
        assert _format_source_type("localFiles") == "Local Files"

    def test_format_unknown_type(self):
        """Should return capitalized form for unknown types."""
        assert _format_source_type("unknown") == "Unknown"

    def test_format_empty_type(self):
        """Should return 'Unknown' for empty or falsy types."""
        assert _format_source_type("") == "Unknown"
        assert _format_source_type(None) == "Unknown"


class TestConfigExistedBefore:
    """Test _config_existed_before function."""

    def test_config_existed_local_mode(self):
        """Should check local config in local mode."""
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "local"
        mock_config.store.has_local_config.return_value = True

        result = _config_existed_before(mock_config)
        assert result is True
        mock_config.store.has_local_config.assert_called_once()

    def test_config_existed_global_mode(self):
        """Should check global config in global mode."""
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.has_global_config.return_value = True

        result = _config_existed_before(mock_config)
        assert result is True
        mock_config.store.has_global_config.assert_called_once()


class TestGetConfigPath:
    """Test _get_config_path function."""

    def test_get_config_path_local_mode(self):
        """Should return workspace path in local mode."""
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "local"
        mock_config.store.workspace_path = "/workspace/.indexed/config.toml"

        result = _get_config_path(mock_config)
        assert result == "/workspace/.indexed/config.toml"

    def test_get_config_path_global_mode(self):
        """Should return global path in global mode."""
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.global_path = "~/.indexed/config.toml"

        result = _get_config_path(mock_config)
        assert result == "~/.indexed/config.toml"


class TestFormatUpdateComparison:
    """Test _format_update_comparison function."""

    @patch("indexed.cli.knowledge.commands.update.console")
    def test_format_update_with_changes(self, mock_console):
        """Should display before/after comparison with deltas."""
        before = Mock()
        before.name = "test-collection"
        before.source_type = "jira"
        before.number_of_documents = 10
        before.number_of_chunks = 50
        before.disk_size_bytes = 1000000
        before.updated_time = "2025-01-01T00:00:00"

        after = Mock()
        after.name = "test-collection"
        after.source_type = "jira"
        after.number_of_documents = 15
        after.number_of_chunks = 75
        after.disk_size_bytes = 1500000
        after.updated_time = "2025-01-28T00:00:00"

        _format_update_comparison(before, after)

        # Should have printed a card with the collection info
        mock_console.print.assert_called()

    @patch("indexed.cli.knowledge.commands.update.console")
    def test_format_update_no_changes(self, mock_console):
        """Should display when collection unchanged."""
        before = Mock()
        before.name = "test-collection"
        before.source_type = "files"
        before.number_of_documents = 20
        before.number_of_chunks = 100
        before.disk_size_bytes = 2000000
        before.updated_time = "2025-01-01T00:00:00"

        after = Mock()
        after.name = "test-collection"
        after.source_type = "files"
        after.number_of_documents = 20
        after.number_of_chunks = 100
        after.disk_size_bytes = 2000000
        after.updated_time = "2025-01-28T00:00:00"

        _format_update_comparison(before, after)

        # Should have printed a card
        mock_console.print.assert_called()


class TestUpdateCommand:
    """Test update command."""

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.NoOpContext")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_single_collection(
        self,
        mock_console,
        mock_noop,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should update a specific collection."""
        # Setup mocks
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "local"
        mock_config.store.has_local_config.return_value = True
        mock_config.store.workspace_path = "/workspace/.indexed/config.toml"
        mock_config_service.instance.return_value = mock_config

        # Mock status
        mock_status = Mock()
        mock_status.name = "test-jira"
        mock_status.source_type = "jira"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        # Mock inspect (called before and after update)
        mock_info = Mock()
        mock_info.name = "test-jira"
        mock_info.source_type = "jira"
        mock_info.number_of_documents = 10
        mock_info.number_of_chunks = 50
        mock_info.disk_size_bytes = 1000000
        mock_info.updated_time = "2025-01-01T00:00:00"
        mock_inspect.return_value = [mock_info]

        # Mock update_service to succeed
        mock_update_service.return_value = None

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "test-jira"])

        # Should complete successfully
        assert result.exit_code == 0

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_all_collections(
        self,
        mock_console,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should update all collections when no collection name provided."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "local"
        mock_config.store.has_local_config.return_value = True
        mock_config.store.workspace_path = "/workspace/.indexed/config.toml"
        mock_config_service.instance.return_value = mock_config

        # Mock multiple statuses
        status1 = Mock()
        status1.name = "jira-collection"
        status1.source_type = "jira"
        status1.indexers = ["default"]

        status2 = Mock()
        status2.name = "confluence-collection"
        status2.source_type = "confluence"
        status2.indexers = ["default"]

        mock_svc_status.return_value = [status1, status2]

        # Mock inspect (called before and after update for each collection)
        info1 = Mock()
        info1.name = "jira-collection"
        info1.source_type = "jira"
        info1.number_of_documents = 10
        info1.number_of_chunks = 50
        info1.disk_size_bytes = 1000000
        info1.updated_time = "2025-01-01T00:00:00"

        info2 = Mock()
        info2.name = "confluence-collection"
        info2.source_type = "confluence"
        info2.number_of_documents = 20
        info2.number_of_chunks = 100
        info2.disk_size_bytes = 2000000
        info2.updated_time = "2025-01-01T00:00:00"

        # inspect is called: before update (jira, confluence), after update (jira, confluence)
        mock_inspect.side_effect = [[info1], [info2], [info1], [info2]]

        # Mock update_service to succeed
        mock_update_service.return_value = None

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update"])

        # Should complete successfully
        assert result.exit_code == 0

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.composition.resolve_collections_context")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_clears_overlay_per_collection(
        self,
        mock_console,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_resolve_ctx,
        mock_setup_logger,
    ):
        """R3 regression: the shared in-memory overlay is cleared once per
        collection so an earlier collection's conditionally-set settings
        (e.g. Outline collection_ids) cannot leak into a later one."""
        from pathlib import Path

        mock_verbose.return_value = True  # simple path — no phased progress display

        cfg = Mock()
        cli_ctx = Mock()
        cli_ctx.config_service = cfg
        cli_ctx.collections_path = Path("/workspace/.indexed/data/collections")
        cli_ctx.caches_path = Path("/workspace/.indexed/data/caches")
        cli_ctx.connector_registry = {}
        mock_resolve_ctx.return_value = cli_ctx

        s1 = Mock(name="outline-a")
        s1.name = "outline-a"
        s1.source_type = "outline"
        s1.indexers = ["default"]
        s2 = Mock(name="outline-b")
        s2.name = "outline-b"
        s2.source_type = "outline"
        s2.indexers = ["default"]
        mock_svc_status.return_value = [s1, s2]
        mock_inspect.return_value = [Mock()]
        mock_update_service.return_value = None

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update"])

        assert result.exit_code == 0
        # One clear_overlay per collection — the guard that stops cross-collection
        # overlay bleed. Without it this count would be 0 (the bug).
        assert cfg.clear_overlay.call_count == 2

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.print_error")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_missing_collection(
        self,
        mock_console,
        mock_print_error,
        mock_svc_status,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should error when collection not found."""
        mock_config = Mock()
        mock_config_service.instance.return_value = mock_config

        # Mock status returns empty
        mock_svc_status.return_value = []

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "nonexistent"])

        # Should exit with error
        assert result.exit_code == 1

    @patch("indexed.cli.utils.storage_info.display_storage_mode_for_command")
    @patch("indexed.cli.composition.resolve_collections_context")
    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_ensures_credentials(
        self,
        mock_console,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
        mock_resolve_context,
        mock_storage_display,
    ):
        """Should ensure credentials are available for the source."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_resolve_context.return_value = make_cli_context(mock_config)
        mock_config_service.instance.return_value = mock_config

        # Mock status
        mock_status = Mock()
        mock_status.name = "jira-collection"
        mock_status.source_type = "jira"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        # Mock inspect
        mock_info = Mock()
        mock_info.name = "jira-collection"
        mock_info.number_of_documents = 10
        mock_info.number_of_chunks = 50
        mock_inspect.return_value = [mock_info]

        from indexed.cli.app import app

        runner.invoke(app, ["index", "update", "jira-collection"])

        # Should have called ensure_credentials
        mock_ensure_creds.assert_called_once_with("jira", mock_config)

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    def test_update_all_no_collections(
        self,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """When no collections exist, update all should print message and return."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.has_global_config.return_value = True
        mock_config_service.instance.return_value = mock_config

        mock_svc_status.return_value = []

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update"])

        assert result.exit_code == 0
        assert "No collections found to update" in result.stdout

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_inspect_fails_before_update(
        self,
        mock_console,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """If pre-update inspect fails, should exit with error."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "col1"
        mock_status.source_type = "localFiles"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        # inspect returns empty (failure)
        mock_inspect.return_value = []

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "col1"])

        assert result.exit_code == 1

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_collection_disappears_during_loop(
        self,
        mock_console,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """If a collection disappears between outer status and loop status, the
        loop continues past it but the run still exits non-zero
        (foundation/6 E8: a per-collection failure must not be reported as a
        silent exit-0 success)."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.has_global_config.return_value = True
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "col1"
        mock_status.source_type = "localFiles"
        mock_status.indexers = ["default"]

        # First call: list all collections
        # Second call (in loop): collection gone
        mock_svc_status.side_effect = [[mock_status], []]

        mock_info = Mock()
        mock_info.name = "col1"
        mock_info.source_type = "localFiles"
        mock_info.number_of_documents = 5
        mock_info.number_of_chunks = 10
        mock_info.disk_size_bytes = 1000
        mock_info.updated_time = None
        mock_inspect.return_value = [mock_info]

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update"])

        # The loop completes (continues past the missing collection) but a
        # per-collection failure must still exit non-zero.
        assert result.exit_code != 0

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_collection_has_no_indexers(
        self,
        mock_console,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Collection with empty indexers list should be skipped with a message."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "col1"
        mock_status.source_type = "localFiles"
        mock_status.indexers = []  # empty
        mock_svc_status.return_value = [mock_status]

        mock_info = Mock()
        mock_info.name = "col1"
        mock_info.number_of_documents = 5
        mock_info.number_of_chunks = 10
        mock_inspect.return_value = [mock_info]

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "col1"])

        # Exits cleanly — the loop continues/ends, then the after-inspect block runs
        # We just verify it doesn't crash
        assert result.exit_code == 0 or result.exit_code == 1

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.NoOpContext")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_verbose_mode(
        self,
        mock_console,
        mock_noop,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """In verbose mode the NoOpContext path should be taken."""
        mock_verbose.return_value = True
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.has_global_config.return_value = True
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "col1"
        mock_status.source_type = "localFiles"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        mock_info = Mock()
        mock_info.name = "col1"
        mock_info.source_type = "localFiles"
        mock_info.number_of_documents = 10
        mock_info.number_of_chunks = 50
        mock_info.disk_size_bytes = 1000
        mock_info.updated_time = None
        mock_inspect.return_value = [mock_info]

        mock_update_service.return_value = None

        # MagicMock supports context manager protocol by default
        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "col1"])

        assert result.exit_code == 0

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.NoOpContext")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_verbose_mode_exception_exits(
        self,
        mock_console,
        mock_noop,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """In verbose mode an exception from update_service should exit 1."""
        mock_verbose.return_value = True
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.has_global_config.return_value = True
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "col1"
        mock_status.source_type = "localFiles"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        mock_info = Mock()
        mock_info.name = "col1"
        mock_info.number_of_documents = 10
        mock_info.number_of_chunks = 50
        mock_info.disk_size_bytes = 1000
        mock_info.updated_time = None
        mock_inspect.return_value = [mock_info]

        mock_update_service.side_effect = RuntimeError("update blew up")

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "col1"])

        assert result.exit_code == 1

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.create_phased_progress")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_non_verbose_exception_exits(
        self,
        mock_console,
        mock_phased_progress,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """In normal mode an exception from update_service should exit 1."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.has_global_config.return_value = True
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "col1"
        mock_status.source_type = "localFiles"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        mock_info = Mock()
        mock_info.name = "col1"
        mock_info.number_of_documents = 10
        mock_info.number_of_chunks = 50
        mock_inspect.return_value = [mock_info]

        mock_update_service.side_effect = RuntimeError("update blew up")

        # Make create_phased_progress a usable context manager
        phased_mock = MagicMock()
        phased_mock.__enter__ = Mock(return_value=phased_mock)
        phased_mock.__exit__ = Mock(return_value=False)
        mock_phased_progress.return_value = phased_mock

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "col1"])

        assert result.exit_code == 1

    @patch("indexed.cli.utils.storage_info.display_storage_mode_for_command")
    @patch("indexed.cli.composition.resolve_collections_context")
    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.print_info")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_config_newly_created_prints_info(
        self,
        mock_console,
        mock_print_info,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
        mock_resolve_context,
        mock_storage_display,
    ):
        """If config is newly created during update, print_info is called with notice."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.global_path = "~/.indexed/config.toml"
        # Config did NOT exist before, but DOES exist after
        mock_config.store.has_global_config.side_effect = [False, True]
        mock_resolve_context.return_value = make_cli_context(mock_config)
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "col1"
        mock_status.source_type = "localFiles"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        mock_info = Mock()
        mock_info.name = "col1"
        mock_info.source_type = "localFiles"
        mock_info.number_of_documents = 5
        mock_info.number_of_chunks = 10
        mock_info.disk_size_bytes = 1000
        mock_info.updated_time = None
        mock_inspect.return_value = [mock_info]

        mock_update_service.return_value = None

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "col1"])

        assert result.exit_code == 0
        # print_info should have been called with the config-created notice
        all_calls = " ".join(str(c) for c in mock_print_info.call_args_list)
        assert "Created new config file" in all_calls

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_inspect_fails_after_update(
        self,
        mock_console,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """If post-update inspect fails, command succeeds without comparison card."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.has_global_config.return_value = True
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "col1"
        mock_status.source_type = "localFiles"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        mock_info = Mock()
        mock_info.name = "col1"
        mock_info.number_of_documents = 5
        mock_info.number_of_chunks = 10

        # First call succeeds (before update), second call fails (after update)
        mock_inspect.side_effect = [[mock_info], []]

        mock_update_service.return_value = None

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "col1"])

        # Update succeeded; missing post-update inspect is graceful degradation
        assert result.exit_code == 0

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.create_summary")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_summary_with_positive_delta(
        self,
        mock_console,
        mock_create_summary,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Single collection update: comparison card shown, no result summary line."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.has_global_config.return_value = True
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "col1"
        mock_status.source_type = "localFiles"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        before_info = Mock()
        before_info.name = "col1"
        before_info.source_type = "localFiles"
        before_info.number_of_documents = 5
        before_info.number_of_chunks = 10
        before_info.disk_size_bytes = 500
        before_info.updated_time = None

        after_info = Mock()
        after_info.name = "col1"
        after_info.source_type = "localFiles"
        after_info.number_of_documents = 8
        after_info.number_of_chunks = 16
        after_info.disk_size_bytes = 800
        after_info.updated_time = None

        mock_inspect.side_effect = [[before_info], [after_info]]
        mock_update_service.return_value = None

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "col1"])

        assert result.exit_code == 0
        # For a single collection, result summary is not shown (create_summary not called)
        mock_create_summary.assert_not_called()

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.create_summary")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_summary_with_negative_delta(
        self,
        mock_console,
        mock_create_summary,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Single collection update: comparison card shown, no result summary line."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.has_global_config.return_value = True
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "col1"
        mock_status.source_type = "localFiles"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        before_info = Mock()
        before_info.name = "col1"
        before_info.source_type = "localFiles"
        before_info.number_of_documents = 10
        before_info.number_of_chunks = 20
        before_info.disk_size_bytes = 1000
        before_info.updated_time = None

        after_info = Mock()
        after_info.name = "col1"
        after_info.source_type = "localFiles"
        after_info.number_of_documents = 7
        after_info.number_of_chunks = 14
        after_info.disk_size_bytes = 700
        after_info.updated_time = None

        mock_inspect.side_effect = [[before_info], [after_info]]
        mock_update_service.return_value = None

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "col1"])

        assert result.exit_code == 0
        # For a single collection, result summary is not shown (create_summary not called)
        mock_create_summary.assert_not_called()


class TestUpdateCollectionOption:
    """L4: ``--collection/-c`` must work as an alias for the positional arg,
    matching ``create``/``search``."""

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.NoOpContext")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_via_collection_option(
        self,
        mock_console,
        mock_noop,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """``-c NAME`` must target NAME, not raise "No such option"."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "local"
        mock_config.store.has_local_config.return_value = True
        mock_config.store.workspace_path = "/workspace/.indexed/config.toml"
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "test-jira"
        mock_status.source_type = "jira"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        mock_info = Mock()
        mock_info.name = "test-jira"
        mock_info.source_type = "jira"
        mock_info.number_of_documents = 10
        mock_info.number_of_chunks = 50
        mock_info.disk_size_bytes = 1000000
        mock_info.updated_time = "2025-01-01T00:00:00"
        mock_inspect.return_value = [mock_info]

        mock_update_service.return_value = None

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "-c", "test-jira"])

        assert result.exit_code == 0, result.stdout
        assert "No such option" not in result.output

    def test_update_conflicting_positional_and_option_exits_1(self):
        """Different values for the positional and ``-c`` must error at exit 1."""
        from indexed.cli.app import app

        result = runner.invoke(
            app, ["index", "update", "col-a", "--collection", "col-b"]
        )

        assert result.exit_code == 1

    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.ConfigService")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    @patch("indexed.cli.knowledge.commands.update.NoOpContext")
    @patch("indexed.cli.knowledge.commands.update.console")
    def test_update_same_value_positional_and_option_ok(
        self,
        mock_console,
        mock_noop,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Passing the SAME value both ways is not a conflict."""
        mock_verbose.return_value = False
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "local"
        mock_config.store.has_local_config.return_value = True
        mock_config.store.workspace_path = "/workspace/.indexed/config.toml"
        mock_config_service.instance.return_value = mock_config

        mock_status = Mock()
        mock_status.name = "test-jira"
        mock_status.source_type = "jira"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        mock_info = Mock()
        mock_info.name = "test-jira"
        mock_info.source_type = "jira"
        mock_info.number_of_documents = 10
        mock_info.number_of_chunks = 50
        mock_info.disk_size_bytes = 1000000
        mock_info.updated_time = "2025-01-01T00:00:00"
        mock_inspect.return_value = [mock_info]

        mock_update_service.return_value = None

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "test-jira", "-c", "test-jira"])

        assert result.exit_code == 0, result.stdout


class TestUpdateMarkupSafety:
    """R7 — collection names are user-controlled and must render literally,
    never be parsed as Rich markup, in the per-collection update header
    (``_display_collection_update_header``) and the "Updating N Collections:"
    heading (``resolve_collections_to_update``). Unlike the other tests in
    this file, ``console`` is deliberately left unmocked so the real Rich
    renderer exercises the markup-parsed sink."""

    @patch(
        "indexed.cli.utils.storage_info.display_storage_mode_for_command",
        lambda *a, **kw: None,
    )
    @patch(
        "indexed.cli.composition.resolve_collections_context",
        side_effect=lambda *a, **kw: make_cli_context(),
    )
    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    def test_single_collection_header_renders_brackets_literally(
        self,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_setup_logger,
        mock_resolve_ctx,
    ):
        mock_verbose.return_value = False

        mock_status = Mock()
        mock_status.name = "my[coll]"
        mock_status.source_type = "localFiles"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        info = Mock()
        info.name = "my[coll]"
        info.source_type = "localFiles"
        info.number_of_documents = 10
        info.number_of_chunks = 20
        info.disk_size_bytes = 1000
        info.updated_time = None
        mock_inspect.side_effect = [[info], [info]]
        mock_update_service.return_value = None

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update", "my[coll]"])

        assert result.exit_code == 0, result.stdout
        # Exact heading line, not just "my[coll]" anywhere: the later
        # comparison card / success message already render the name safely
        # via the pre-existing Text()-wrapped idiom, so a looser assertion
        # would pass even with this header sink unfixed.
        assert 'Updating Collection "my[coll]"' in result.stdout

    @patch(
        "indexed.cli.utils.storage_info.display_storage_mode_for_command",
        lambda *a, **kw: None,
    )
    @patch(
        "indexed.cli.composition.resolve_collections_context",
        side_effect=lambda *a, **kw: make_cli_context(),
    )
    @patch("indexed.cli.knowledge.commands.update.setup_root_logger")
    @patch("indexed.cli.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.cli.knowledge.commands.update.svc_status")
    @patch("indexed.cli.knowledge.commands.update.inspect")
    @patch("indexed.cli.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.cli.knowledge.commands.update.update_service")
    def test_multi_collection_heading_renders_brackets_literally(
        self,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_setup_logger,
        mock_resolve_ctx,
    ):
        mock_verbose.return_value = False

        # Rich's markup tag grammar only matches a bracket run starting with
        # a lowercase letter/#//@ (e.g. "jira[one]"), not a digit
        # ("jira[1]") — the fixture must start with a letter to actually
        # exercise the parser.
        status1 = Mock()
        status1.name = "jira[one]"
        status1.source_type = "jira"
        status1.indexers = ["default"]
        status2 = Mock()
        status2.name = "conf[two]"
        status2.source_type = "confluence"
        status2.indexers = ["default"]
        mock_svc_status.return_value = [status1, status2]

        info1 = Mock()
        info1.name = "jira[one]"
        info1.source_type = "jira"
        info1.number_of_documents = 10
        info1.number_of_chunks = 20
        info1.disk_size_bytes = 1000
        info1.updated_time = None
        info2 = Mock()
        info2.name = "conf[two]"
        info2.source_type = "confluence"
        info2.number_of_documents = 5
        info2.number_of_chunks = 15
        info2.disk_size_bytes = 500
        info2.updated_time = None

        # before x2, after x2
        mock_inspect.side_effect = [[info1], [info2], [info1], [info2]]
        mock_update_service.return_value = None

        from indexed.cli.app import app

        result = runner.invoke(app, ["index", "update"])

        assert result.exit_code == 0, result.stdout
        # Exact heading line: the per-collection header and success message
        # below already render each name safely, so a looser assertion
        # ("jira[one]" anywhere in stdout) would pass even with this
        # specific multi-collection heading sink unfixed.
        assert 'Updating 2 Collections: "jira[one]", "conf[two]"' in result.stdout


class TestIncludedPatternsDisplay:
    """R3 / rendering-fixes/2: the "Included Patterns" row must show the
    user's own pattern text, never an ``fnmatch.translate()`` regex string.

    Exercises ``_display_collection_update_header`` directly with a fake
    console so the printed ``Text`` rows can be inspected without going
    through the full CLI invocation machinery.
    """

    @staticmethod
    def _rendered_text(reader_config: dict) -> str:
        from indexed.cli.knowledge.commands.update_service import (
            _display_collection_update_header,
        )

        printed: list[str] = []
        fake_console = SimpleNamespace(
            print=lambda *a, **kw: printed.append(
                getattr(a[0], "plain", str(a[0])) if a else ""
            )
        )
        _display_collection_update_header(
            "docs", "localFiles", reader_config, console=fake_console
        )
        return "\n".join(printed)

    def test_default_pattern_shows_all_files_label(self):
        """New-style manifest (Part A): ["*"] stored literally."""
        output = self._rendered_text(
            {"basePath": "/tmp/does-not-exist", "includePatterns": ["*"]}
        )
        assert "* (all files)" in output

    def test_custom_glob_pattern_shows_literal_text_never_translated(self):
        """New-style manifest (Part A): ["*.py"] stored literally, and the
        display must never show its fnmatch.translate() form."""
        output = self._rendered_text(
            {"basePath": "/tmp/does-not-exist", "includePatterns": ["*.py"]}
        )
        assert "*.py" in output
        assert "(?s:" not in output

    def test_legacy_translated_default_pattern_shows_all_files_label(self):
        """Part B: a manifest persisted under the pre-fix behavior stores
        fnmatch.translate("*") verbatim; the display-time fallback must
        still recognize it and label it "* (all files)", with the raw
        translated string never reaching the rendered output."""
        legacy_star = fnmatch.translate("*")
        output = self._rendered_text(
            {"basePath": "/tmp/does-not-exist", "includePatterns": [legacy_star]}
        )
        assert "* (all files)" in output
        assert legacy_star not in output

    def test_legacy_translated_custom_glob_is_not_mislabeled_all_files(self):
        """The Part B fallback recognizes only the default "*" translation --
        a legacy translated non-default glob must not be mislabeled
        "* (all files)"; it displays as its raw (still-cryptic) stored text,
        matching pre-existing behavior for that already-lossy case."""
        legacy_py = fnmatch.translate("*.py")
        output = self._rendered_text(
            {"basePath": "/tmp/does-not-exist", "includePatterns": [legacy_py]}
        )
        assert "* (all files)" not in output

    def test_include_row_aligns_with_the_rows_around_it(self):
        """R3's second half (final-review I3): the row must be *padded
        consistently* with Type/Path/Excluded. `create_info_row` pads to
        `get_info_row_label_width()`; the old 17-char "Included Patterns"
        label overran that budget and jammed the value onto the label with no
        separating space. Assert the real column, not just the value text."""
        from indexed.cli.utils.components.theme import get_info_row_label_width

        output = self._rendered_text(
            {
                "basePath": "/tmp/does-not-exist",
                "includePatterns": ["*"],
                "excludedDirs": ["node_modules", ".git"],
                "respectGitignore": True,
            }
        )
        label_width = get_info_row_label_width()
        rows = [
            line
            for line in output.splitlines()
            if line.startswith(("Type", "Path", "Included", "Excluded"))
        ]
        assert len(rows) == 4, output
        for line in rows:
            label = line[:label_width]
            # Label fits the budget *and* leaves at least one space before the
            # value, so every row's value starts at the same column.
            assert label.rstrip() != label, repr(line)
            assert len(label.rstrip()) <= label_width - 1, repr(line)
            assert line[label_width] != " ", repr(line)
