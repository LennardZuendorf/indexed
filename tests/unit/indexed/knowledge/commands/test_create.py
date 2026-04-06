"""Tests for knowledge create commands."""

from unittest.mock import Mock, patch
import pytest
import typer

from indexed.knowledge.commands.create import (
    _is_cloud,
    create_files,
    create_jira,
    create_confluence,
)


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
        call_kwargs = mock_execute.call_args.kwargs

        assert call_kwargs["collection"] == "test-files"
        assert call_kwargs["source_type"] == "localFiles"
        assert call_kwargs["use_cache"] is False
        assert call_kwargs["force"] is True

        # Verify CLI overrides were passed correctly
        cli_overrides = call_kwargs["cli_overrides"]
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
        call_kwargs = mock_execute.call_args.kwargs
        cli_overrides = call_kwargs.get("cli_overrides", {})
        # Should only have empty dict or minimal overrides
        assert "path" not in cli_overrides or cli_overrides["path"] is None


class TestCreateJira:
    """Test create_jira command."""

    @pytest.mark.parametrize(
        "url,expected_source_type",
        [
            ("https://company.atlassian.net", "jiraCloud"),
            ("https://jira.company.com", "jira"),
        ],
        ids=["cloud_detection", "server_detection"],
    )
    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_jira_detects_cloud_vs_server(
        self,
        mock_console,
        mock_verbose,
        mock_config_service,
        mock_execute,
        url,
        expected_source_type,
    ):
        """Should detect cloud vs server based on URL."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        create_jira(
            collection="test-jira",
            url=url,
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
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["source_type"] == expected_source_type

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
        self,
        mock_print_error,
        mock_console,
        mock_verbose,
        mock_config_service,
        mock_execute,
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

    @pytest.mark.parametrize(
        "url,expected_source_type",
        [
            ("https://company.atlassian.net", "confluenceCloud"),
            ("https://confluence.company.com", "confluence"),
        ],
        ids=["cloud_detection", "server_detection"],
    )
    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_confluence_detects_cloud_vs_server(
        self,
        mock_console,
        mock_verbose,
        mock_config_service,
        mock_execute,
        url,
        expected_source_type,
    ):
        """Should detect cloud vs server based on URL."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        create_confluence(
            collection="test-confluence",
            url=url,
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
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["source_type"] == expected_source_type

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    @patch("indexed.knowledge.commands.create.print_error")
    def test_create_confluence_exits_on_empty_url(
        self,
        mock_print_error,
        mock_console,
        mock_verbose,
        mock_config_service,
        mock_execute,
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


def _capture_prompt_fn(create_fn, create_kwargs, mock_config_service, mock_execute):
    """Helper: call a create command, capture the prompt_missing_fields callback."""
    captured = {}

    def capture_kwargs(**kwargs):
        captured.update(kwargs)

    mock_execute.side_effect = capture_kwargs
    mock_config = Mock()
    mock_config_service.instance.return_value = mock_config
    create_fn(**create_kwargs)
    return captured.get("prompt_missing_fields"), mock_config


class TestPromptMissingFilesFields:
    """Test the prompt_missing_files_fields callback's output behaviour.

    The function receives a validation object with .missing fields and
    populates validation.present with user-supplied values. We test what
    ends up in validation.present for various field types — that is the
    observable contract: given the user types X, the result is Y.
    """

    _default_kwargs = dict(
        collection="test",
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

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    def test_no_missing_fields_leaves_present_unchanged(
        self, mock_console, mock_config_service, mock_execute
    ):
        """When validation.missing is empty, present stays empty."""
        from types import SimpleNamespace

        prompt_fn, mock_config = _capture_prompt_fn(
            create_files, self._default_kwargs, mock_config_service, mock_execute
        )
        validation = SimpleNamespace(missing=[], field_info={}, present={})
        prompt_fn(validation, mock_config, "sources.files")
        assert validation.present == {}

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    def test_user_input_for_path_stored_in_present(
        self, mock_console, mock_config_service, mock_execute
    ):
        from types import SimpleNamespace

        prompt_fn, mock_config = _capture_prompt_fn(
            create_files, self._default_kwargs, mock_config_service, mock_execute
        )
        mock_console.input.return_value = "/my/path"
        validation = SimpleNamespace(
            missing=["path"], field_info={"path": {}}, present={}
        )
        prompt_fn(validation, mock_config, "sources.files")
        assert validation.present["path"] == "/my/path"

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    def test_include_patterns_split_by_comma(
        self, mock_console, mock_config_service, mock_execute
    ):
        from types import SimpleNamespace

        prompt_fn, mock_config = _capture_prompt_fn(
            create_files, self._default_kwargs, mock_config_service, mock_execute
        )
        mock_console.input.return_value = "*.md, *.py"
        validation = SimpleNamespace(
            missing=["include_patterns"],
            field_info={"include_patterns": {}},
            present={},
        )
        prompt_fn(validation, mock_config, "sources.files")
        assert validation.present["include_patterns"] == ["*.md", "*.py"]

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    def test_empty_include_patterns_defaults_to_match_all(
        self, mock_console, mock_config_service, mock_execute
    ):
        from types import SimpleNamespace

        prompt_fn, mock_config = _capture_prompt_fn(
            create_files, self._default_kwargs, mock_config_service, mock_execute
        )
        mock_console.input.return_value = ""
        validation = SimpleNamespace(
            missing=["include_patterns"],
            field_info={"include_patterns": {}},
            present={},
        )
        prompt_fn(validation, mock_config, "sources.files")
        assert validation.present["include_patterns"] == ["*"]

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    def test_exclude_patterns_split_by_comma(
        self, mock_console, mock_config_service, mock_execute
    ):
        from types import SimpleNamespace

        prompt_fn, mock_config = _capture_prompt_fn(
            create_files, self._default_kwargs, mock_config_service, mock_execute
        )
        mock_console.input.return_value = "*.log, *.tmp"
        validation = SimpleNamespace(
            missing=["exclude_patterns"],
            field_info={"exclude_patterns": {}},
            present={},
        )
        prompt_fn(validation, mock_config, "sources.files")
        assert validation.present["exclude_patterns"] == ["*.log", "*.tmp"]

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    def test_empty_exclude_patterns_defaults_to_empty_list(
        self, mock_console, mock_config_service, mock_execute
    ):
        from types import SimpleNamespace

        prompt_fn, mock_config = _capture_prompt_fn(
            create_files, self._default_kwargs, mock_config_service, mock_execute
        )
        mock_console.input.return_value = ""
        validation = SimpleNamespace(
            missing=["exclude_patterns"],
            field_info={"exclude_patterns": {}},
            present={},
        )
        prompt_fn(validation, mock_config, "sources.files")
        assert validation.present["exclude_patterns"] == []

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    def test_yes_input_for_fail_fast_sets_true(
        self, mock_console, mock_config_service, mock_execute
    ):
        from types import SimpleNamespace

        prompt_fn, mock_config = _capture_prompt_fn(
            create_files, self._default_kwargs, mock_config_service, mock_execute
        )
        mock_console.input.return_value = "yes"
        validation = SimpleNamespace(
            missing=["fail_fast"], field_info={"fail_fast": {}}, present={}
        )
        prompt_fn(validation, mock_config, "sources.files")
        assert validation.present["fail_fast"] is True

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    def test_no_input_for_fail_fast_sets_false(
        self, mock_console, mock_config_service, mock_execute
    ):
        from types import SimpleNamespace

        prompt_fn, mock_config = _capture_prompt_fn(
            create_files, self._default_kwargs, mock_config_service, mock_execute
        )
        mock_console.input.return_value = "no"
        validation = SimpleNamespace(
            missing=["fail_fast"], field_info={"fail_fast": {}}, present={}
        )
        prompt_fn(validation, mock_config, "sources.files")
        assert validation.present["fail_fast"] is False

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    def test_unknown_field_uses_generic_prompt(
        self, mock_console, mock_config_service, mock_execute
    ):
        from types import SimpleNamespace

        prompt_fn, mock_config = _capture_prompt_fn(
            create_files, self._default_kwargs, mock_config_service, mock_execute
        )
        mock_console.input.return_value = "custom_value"
        validation = SimpleNamespace(
            missing=["some_field"], field_info={"some_field": {}}, present={}
        )
        prompt_fn(validation, mock_config, "sources.files")
        assert validation.present["some_field"] == "custom_value"

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    def test_verbose_mode_still_populates_present(
        self, mock_verbose, mock_console, mock_config_service, mock_execute
    ):
        from types import SimpleNamespace

        mock_verbose.return_value = True
        prompt_fn, mock_config = _capture_prompt_fn(
            create_files, self._default_kwargs, mock_config_service, mock_execute
        )
        mock_console.input.return_value = "/verbose/path"
        validation = SimpleNamespace(
            missing=["path"], field_info={"path": {}}, present={}
        )
        prompt_fn(validation, mock_config, "sources.files")
        assert validation.present["path"] == "/verbose/path"


class TestPromptMissingJiraFields:
    """Test prompt_missing_jira_fields callback: given user input, result is stored correctly."""

    _jira_kwargs = dict(
        collection="test-jira",
        url="https://company.atlassian.net",
        jql=None,
        email=None,
        token=None,
        use_cache=True,
        force=False,
        verbose=False,
        json_logs=False,
        log_level=None,
    )

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    def test_only_url_missing_leaves_present_empty(
        self, mock_console, mock_config_service, mock_execute
    ):
        """url is handled separately; if it's the only missing field, nothing is prompted."""
        from types import SimpleNamespace

        prompt_fn, mock_config = _capture_prompt_fn(
            create_jira, self._jira_kwargs, mock_config_service, mock_execute
        )
        validation = SimpleNamespace(missing=["url"], field_info={}, present={})
        prompt_fn(validation, mock_config, "sources.jira")
        assert validation.present == {}

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    @patch("indexed.knowledge.commands.create.is_credential_field")
    def test_jql_query_input_stored_in_present(
        self, mock_is_credential, mock_console, mock_config_service, mock_execute
    ):
        from types import SimpleNamespace

        mock_is_credential.return_value = False
        prompt_fn, mock_config = _capture_prompt_fn(
            create_jira, self._jira_kwargs, mock_config_service, mock_execute
        )
        mock_console.input.return_value = "project = PROJ"
        validation = SimpleNamespace(
            missing=["query"], field_info={"query": {}}, present={}
        )
        prompt_fn(validation, mock_config, "sources.jira")
        assert validation.present["query"] == "project = PROJ"

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    @patch("indexed.knowledge.commands.create.is_credential_field")
    def test_unknown_field_uses_generic_prompt(
        self, mock_is_credential, mock_console, mock_config_service, mock_execute
    ):
        from types import SimpleNamespace

        mock_is_credential.return_value = False
        prompt_fn, mock_config = _capture_prompt_fn(
            create_jira, self._jira_kwargs, mock_config_service, mock_execute
        )
        mock_console.input.return_value = "some_value"
        validation = SimpleNamespace(
            missing=["custom_field"], field_info={"custom_field": {}}, present={}
        )
        prompt_fn(validation, mock_config, "sources.jira")
        assert validation.present["custom_field"] == "some_value"

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.console")
    @patch("indexed.knowledge.commands.create.is_credential_field")
    @patch("indexed.knowledge.commands.create.prompt_credential_field")
    def test_credential_field_value_stored_in_present(
        self,
        mock_prompt_cred,
        mock_is_credential,
        mock_console,
        mock_config_service,
        mock_execute,
    ):
        from types import SimpleNamespace

        mock_is_credential.return_value = True
        mock_prompt_cred.return_value = "secret-token"
        prompt_fn, mock_config = _capture_prompt_fn(
            create_jira, self._jira_kwargs, mock_config_service, mock_execute
        )
        validation = SimpleNamespace(
            missing=["api_token"],
            field_info={"api_token": {"sensitive": True}},
            present={},
        )
        prompt_fn(validation, mock_config, "sources.jira")
        assert validation.present["api_token"] == "secret-token"


class TestCreateModuleGetattr:
    """Lazy __getattr__ in create module returns the correctly loaded object."""

    def test_default_indexer_lazy_load_returns_value(self):
        import sys
        import indexed.knowledge.commands.create as create_mod

        mock_constants = Mock()
        mock_constants.DEFAULT_INDEXER = "flat"
        with patch.dict(sys.modules, {"core.v1.constants": mock_constants}):
            result = create_mod.__getattr__("DEFAULT_INDEXER")
        assert result == "flat"

    def test_source_config_lazy_load_returns_class(self):
        import sys
        import indexed.knowledge.commands.create as create_mod

        MockSourceConfig = Mock()
        mock_services = Mock()
        mock_services.SourceConfig = MockSourceConfig
        with patch.dict(sys.modules, {"core.v1.engine.services": mock_services}):
            result = create_mod.__getattr__("SourceConfig")
        assert result is MockSourceConfig
