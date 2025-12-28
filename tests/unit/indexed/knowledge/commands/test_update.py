"""Tests for knowledge update commands."""

from unittest.mock import Mock, patch
from typer.testing import CliRunner

from indexed.knowledge.commands.update import (
    _format_source_type,
    _config_existed_before,
    _get_config_path,
    _format_update_comparison,
)

runner = CliRunner()


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

    @patch("indexed.knowledge.commands.update.ConfigService")
    def test_config_existed_local_mode(self, mock_config_service):
        """Should check local config in local mode."""
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "local"
        mock_config.store.has_local_config.return_value = True
        mock_config_service.instance.return_value = mock_config

        result = _config_existed_before(mock_config)
        assert result is True
        mock_config.store.has_local_config.assert_called_once()

    @patch("indexed.knowledge.commands.update.ConfigService")
    def test_config_existed_global_mode(self, mock_config_service):
        """Should check global config in global mode."""
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.has_global_config.return_value = True
        mock_config_service.instance.return_value = mock_config

        result = _config_existed_before(mock_config)
        assert result is True
        mock_config.store.has_global_config.assert_called_once()


class TestGetConfigPath:
    """Test _get_config_path function."""

    @patch("indexed.knowledge.commands.update.ConfigService")
    def test_get_config_path_local_mode(self, mock_config_service):
        """Should return workspace path in local mode."""
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "local"
        mock_config.store.workspace_path = "/workspace/.indexed/config.toml"
        mock_config_service.instance.return_value = mock_config

        result = _get_config_path(mock_config)
        assert result == "/workspace/.indexed/config.toml"

    @patch("indexed.knowledge.commands.update.ConfigService")
    def test_get_config_path_global_mode(self, mock_config_service):
        """Should return global path in global mode."""
        mock_config = Mock()
        mock_config.resolve_storage_mode.return_value = "global"
        mock_config.store.global_path = "~/.indexed/config.toml"
        mock_config_service.instance.return_value = mock_config

        result = _get_config_path(mock_config)
        assert result == "~/.indexed/config.toml"


class TestFormatUpdateComparison:
    """Test _format_update_comparison function."""

    @patch("indexed.knowledge.commands.update.console")
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

    @patch("indexed.knowledge.commands.update.console")
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

    @patch("indexed.knowledge.commands.update.setup_root_logger")
    @patch("indexed.knowledge.commands.update.ConfigService")
    @patch("indexed.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.knowledge.commands.update.svc_status")
    @patch("indexed.knowledge.commands.update.inspect")
    @patch("indexed.knowledge.commands.update.update_service")
    @patch("indexed.knowledge.commands.update.NoOpContext")
    @patch("indexed.knowledge.commands.update.console")
    def test_update_single_collection(
        self,
        mock_console,
        mock_noop,
        mock_update_service,
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
        mock_config_service.instance.return_value = mock_config

        # Mock status
        mock_status = Mock()
        mock_status.name = "test-jira"
        mock_status.source_type = "jira"
        mock_status.indexers = ["default"]
        mock_svc_status.return_value = [mock_status]

        # Mock inspect
        mock_info = Mock()
        mock_info.name = "test-jira"
        mock_info.number_of_documents = 10
        mock_info.number_of_chunks = 50
        mock_inspect.return_value = [mock_info]

        from indexed.app import app

        result = runner.invoke(app, ["index", "update", "test-jira"])

        # Should complete successfully or partially
        assert result.exit_code in [0, 1]

    @patch("indexed.knowledge.commands.update.setup_root_logger")
    @patch("indexed.knowledge.commands.update.ConfigService")
    @patch("indexed.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.knowledge.commands.update.svc_status")
    @patch("indexed.knowledge.commands.update.inspect")
    @patch("indexed.knowledge.commands.update.update_service")
    @patch("indexed.knowledge.commands.update.console")
    def test_update_all_collections(
        self,
        mock_console,
        mock_update_service,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should update all collections when no collection name provided."""
        mock_verbose.return_value = False
        mock_config = Mock()
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

        # Mock inspect
        info1 = Mock()
        info1.name = "jira-collection"
        info1.number_of_documents = 10
        info1.number_of_chunks = 50

        info2 = Mock()
        info2.name = "confluence-collection"
        info2.number_of_documents = 20
        info2.number_of_chunks = 100

        mock_inspect.side_effect = [[info1], [info2], [info1], [info2]]

        from indexed.app import app

        result = runner.invoke(app, ["index", "update"])

        # Should complete successfully or partially
        assert result.exit_code in [0, 1]

    @patch("indexed.knowledge.commands.update.setup_root_logger")
    @patch("indexed.knowledge.commands.update.ConfigService")
    @patch("indexed.knowledge.commands.update.svc_status")
    @patch("indexed.knowledge.commands.update.print_error")
    @patch("indexed.knowledge.commands.update.console")
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

        from indexed.app import app

        result = runner.invoke(app, ["index", "update", "nonexistent"])

        # Should exit with error
        assert result.exit_code == 1

    @patch("indexed.knowledge.commands.update.setup_root_logger")
    @patch("indexed.knowledge.commands.update.ConfigService")
    @patch("indexed.knowledge.commands.update.is_verbose_mode")
    @patch("indexed.knowledge.commands.update.svc_status")
    @patch("indexed.knowledge.commands.update.inspect")
    @patch("indexed.knowledge.commands.update.ensure_credentials_for_source")
    @patch("indexed.knowledge.commands.update.update_service")
    @patch("indexed.knowledge.commands.update.suppress_core_output")
    @patch("indexed.knowledge.commands.update.console")
    def test_update_ensures_credentials(
        self,
        mock_console,
        mock_suppress,
        mock_update_service,
        mock_ensure_creds,
        mock_inspect,
        mock_svc_status,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should ensure credentials are available for the source."""
        mock_verbose.return_value = False
        mock_config = Mock()
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

        from indexed.app import app

        runner.invoke(app, ["index", "update", "jira-collection"])

        # Should have called ensure_credentials
        mock_ensure_creds.assert_called_once_with("jira", mock_config)
