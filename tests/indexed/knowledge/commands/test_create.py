"""Tests for knowledge create commands."""

from unittest.mock import Mock, patch, MagicMock
import pytest
import typer

from indexed.knowledge.commands.create import _is_cloud, create_files, create_jira, create_confluence


class TestIsCloud:
    """Test _is_cloud function."""

    def test_cloud_url_returns_true(self):
        """Should return True for cloud URLs ending with .atlassian.net."""
        assert _is_cloud("https://company.atlassian.net") is True
        assert _is_cloud("https://mycompany.atlassian.net") is True
        assert _is_cloud("http://test.atlassian.net") is True

    def test_server_url_returns_false(self):
        """Should return False for server URLs."""
        assert _is_cloud("https://jira.company.com") is False
        assert _is_cloud("http://localhost:8080") is False
        assert _is_cloud("https://confluence.example.org") is False

    def test_empty_url_returns_false(self):
        """Should return False for empty string."""
        assert _is_cloud("") is False

    def test_partial_match_returns_false(self):
        """Should return False if .atlassian.net is not at the end."""
        assert _is_cloud("https://atlassian.net.example.com") is False
        assert _is_cloud("atlassian.net") is False


class TestCreateFiles:
    """Test create_files command."""

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    def test_create_files_calls_execute_with_correct_params(
        self, mock_config_service, mock_execute
    ):
        """Should call execute_create_command with Files-specific parameters."""
        mock_config = Mock()
        mock_config_service.instance.return_value = mock_config

        # Call the command function directly (bypassing typer)
        create_files(
            collection="test-files",
            path="/test/path",
            include=["*.md"],
            exclude=["*.tmp"],
            fail_fast=True,
            use_cache=False,
            force=True,
            verbose=False,
            json_logs=False,
            log_level=None,
        )

        # Verify execute_create_command was called
        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args[1]

        assert call_kwargs["collection"] == "test-files"
        assert call_kwargs["source_type"] == "localFiles"
        assert call_kwargs["use_cache"] is False
        assert call_kwargs["force"] is True

        # Verify CLI overrides were passed correctly
        cli_overrides = mock_execute.call_args[0][4]  # 5th positional arg
        assert cli_overrides["path"] == "/test/path"
        assert cli_overrides["include_patterns"] == ["*.md"]
        assert cli_overrides["exclude_patterns"] == ["*.tmp"]
        assert cli_overrides["fail_fast"] is True

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    def test_create_files_with_defaults(self, mock_config_service, mock_execute):
        """Should work with default parameters."""
        mock_config = Mock()
        mock_config_service.instance.return_value = mock_config

        create_files(
            collection="files",
            path=None,
            include=None,
            exclude=None,
            fail_fast=False,
            use_cache=True,
            force=False,
            verbose=False,
            json_logs=False,
            log_level=None,
        )

        mock_execute.assert_called_once()
        cli_overrides = mock_execute.call_args[0][4]
        # Should only have empty dict or minimal overrides
        assert "path" not in cli_overrides or cli_overrides["path"] is None


class TestCreateJira:
    """Test create_jira command."""

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_jira_cloud_detection(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should detect cloud vs server based on URL."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        create_jira(
            collection="test-jira",
            url="https://company.atlassian.net",
            jql="project = TEST",
            email=None,
            token=None,
            use_cache=True,
            force=False,
            verbose=False,
            json_logs=False,
            log_level=None,
        )

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args[1]
        # Should use jiraCloud for .atlassian.net URLs
        assert call_kwargs["source_type"] == "jiraCloud"

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_jira_server_detection(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should detect server deployment for non-cloud URLs."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        create_jira(
            collection="test-jira",
            url="https://jira.company.com",
            jql="project = TEST",
            email=None,
            token=None,
            use_cache=True,
            force=False,
            verbose=False,
            json_logs=False,
            log_level=None,
        )

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args[1]
        # Should use jira (server) for non-cloud URLs
        assert call_kwargs["source_type"] == "jira"

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_jira_prompts_for_url_when_missing(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should prompt for URL when not provided."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False
        mock_console.input.return_value = "https://company.atlassian.net"

        create_jira(
            collection="test-jira",
            url=None,
            jql=None,
            email=None,
            token=None,
            use_cache=True,
            force=False,
            verbose=False,
            json_logs=False,
            log_level=None,
        )

        # Should have prompted for URL
        mock_console.input.assert_called()
        mock_execute.assert_called_once()

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    @patch("indexed.knowledge.commands.create.print_error")
    def test_create_jira_exits_on_empty_url(
        self, mock_print_error, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should exit with error when URL is empty after prompt."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False
        mock_console.input.return_value = ""  # Empty URL

        with pytest.raises(typer.Exit):
            create_jira(
                collection="test-jira",
                url=None,
                jql=None,
                email=None,
                token=None,
                use_cache=True,
                force=False,
                verbose=False,
                json_logs=False,
                log_level=None,
            )

        mock_print_error.assert_called()
        mock_execute.assert_not_called()


class TestCreateConfluence:
    """Test create_confluence command."""

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_confluence_cloud_detection(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should detect cloud vs server based on URL."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        create_confluence(
            collection="test-confluence",
            url="https://company.atlassian.net",
            cql="type=page",
            email=None,
            token=None,
            read_all_comments=True,
            use_cache=True,
            force=False,
            verbose=False,
            json_logs=False,
            log_level=None,
        )

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs["source_type"] == "confluenceCloud"

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_confluence_server_detection(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should detect server deployment for non-cloud URLs."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        create_confluence(
            collection="test-confluence",
            url="https://confluence.company.com",
            cql="type=page",
            email=None,
            token=None,
            read_all_comments=False,
            use_cache=True,
            force=False,
            verbose=False,
            json_logs=False,
            log_level=None,
        )

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs["source_type"] == "confluence"

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    @patch("indexed.knowledge.commands.create.print_error")
    def test_create_confluence_exits_on_empty_url(
        self, mock_print_error, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should exit with error when URL is empty after prompt."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False
        mock_console.input.return_value = ""

        with pytest.raises(typer.Exit):
            create_confluence(
                collection="test-confluence",
                url=None,
                cql=None,
                email=None,
                token=None,
                read_all_comments=True,
                use_cache=True,
                force=False,
                verbose=False,
                json_logs=False,
                log_level=None,
            )

        mock_print_error.assert_called()
        mock_execute.assert_not_called()
