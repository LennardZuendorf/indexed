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


class TestCreateOutline:
    """Test create_outline command."""

    _default_kwargs = dict(
        collection="outline",
        url=None,
        token=None,
        collection_id=None,
        include_attachments=True,
        ocr=True,
        use_cache=True,
        force=False,
        verbose=False,
        json_logs=False,
        log_level=None,
        local=False,
    )

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_outline_with_explicit_url(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should call execute_create_command with outline source type."""
        from indexed.knowledge.commands.create import create_outline

        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        create_outline(**{**self._default_kwargs, "url": "https://app.getoutline.com"})

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["source_type"] == "outline"

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_outline_prompts_for_url_when_missing(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should prompt for URL and default to Cloud if Enter is pressed."""
        from indexed.knowledge.commands.create import create_outline

        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False
        mock_console.input.return_value = (
            ""  # User presses Enter → use default Cloud URL
        )

        create_outline(**self._default_kwargs)

        mock_console.input.assert_called()
        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert (
            call_kwargs["progress_message"]
            == "Connecting to https://app.getoutline.com"
        )

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_outline_uses_provided_url(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should use self-hosted URL without prompting."""
        from indexed.knowledge.commands.create import create_outline

        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        create_outline(
            **{**self._default_kwargs, "url": "https://outline.mycompany.com"}
        )

        mock_console.input.assert_not_called()
        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert (
            call_kwargs["progress_message"]
            == "Connecting to https://outline.mycompany.com"
        )

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_outline_token_added_to_cli_overrides(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should include api_token in cli_overrides when token is provided."""
        from indexed.knowledge.commands.create import create_outline

        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        create_outline(
            **{
                **self._default_kwargs,
                "url": "https://app.getoutline.com",
                "token": "my-token",
            }
        )

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["cli_overrides"]["api_token"] == "my-token"

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_outline_collection_ids_passed(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should convert tuple of collection IDs to list in cli_overrides."""
        from indexed.knowledge.commands.create import create_outline

        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        create_outline(
            **{
                **self._default_kwargs,
                "url": "https://app.getoutline.com",
                "collection_id": ["col-1", "col-2"],
            }
        )

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["cli_overrides"]["collection_ids"] == ["col-1", "col-2"]

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_outline_url_from_config(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should use URL from config when CLI URL not provided."""
        from indexed.knowledge.commands.create import create_outline

        mock_config = Mock()
        mock_config.get.return_value = "https://outline.configured.com"
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        create_outline(**self._default_kwargs)

        mock_console.input.assert_not_called()
        mock_execute.assert_called_once()

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_create_outline_custom_url_prompts(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should use user-entered custom URL when provided at prompt."""
        from indexed.knowledge.commands.create import create_outline

        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False
        mock_console.input.return_value = "https://wiki.myorg.com"

        create_outline(**self._default_kwargs)

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["progress_message"] == "Connecting to https://wiki.myorg.com"


class TestPromptMissingOutlineFields:
    """Test the prompt_missing_outline_fields callback captured from create_outline."""

    _default_kwargs = dict(
        collection="outline",
        url="https://app.getoutline.com",
        token=None,
        collection_id=None,
        include_attachments=True,
        ocr=True,
        use_cache=True,
        force=False,
        verbose=False,
        json_logs=False,
        log_level=None,
        local=False,
    )

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_no_missing_fields_is_noop(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should return immediately when no fields are missing."""
        from types import SimpleNamespace
        from indexed.knowledge.commands.create import create_outline

        prompt_fn, mock_config = _capture_prompt_fn(
            create_outline, self._default_kwargs, mock_config_service, mock_execute
        )
        validation = SimpleNamespace(missing=[], field_info={}, present={})
        prompt_fn(validation, mock_config, "sources.outline")

        mock_console.input.assert_not_called()

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_url_excluded_from_missing_fields(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should skip 'url' even if listed in missing fields."""
        from types import SimpleNamespace
        from indexed.knowledge.commands.create import create_outline

        prompt_fn, mock_config = _capture_prompt_fn(
            create_outline, self._default_kwargs, mock_config_service, mock_execute
        )
        validation = SimpleNamespace(missing=["url"], field_info={}, present={})
        prompt_fn(validation, mock_config, "sources.outline")

        mock_console.input.assert_not_called()

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    @patch("indexed.knowledge.commands.create.prompt_credential_field")
    def test_credential_field_delegates_to_prompt_credential_field(
        self,
        mock_prompt_cred,
        mock_console,
        mock_verbose,
        mock_config_service,
        mock_execute,
    ):
        """Should call prompt_credential_field for credential fields like api_token."""
        from types import SimpleNamespace
        from indexed.knowledge.commands.create import create_outline

        mock_prompt_cred.return_value = "secret-token"
        prompt_fn, mock_config = _capture_prompt_fn(
            create_outline, self._default_kwargs, mock_config_service, mock_execute
        )
        validation = SimpleNamespace(
            missing=["api_token"],
            field_info={"api_token": {"sensitive": True}},
            present={},
        )
        prompt_fn(validation, mock_config, "sources.outline")

        mock_prompt_cred.assert_called_once()
        assert validation.present["api_token"] == "secret-token"

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_non_credential_field_uses_console_input(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should use console.input for non-credential fields."""
        from types import SimpleNamespace
        from indexed.knowledge.commands.create import create_outline

        mock_console.input.return_value = "some-value"
        prompt_fn, mock_config = _capture_prompt_fn(
            create_outline, self._default_kwargs, mock_config_service, mock_execute
        )
        validation = SimpleNamespace(
            missing=["custom_field"],
            field_info={"custom_field": {}},
            present={},
        )
        prompt_fn(validation, mock_config, "sources.outline")

        mock_console.input.assert_called()
        assert validation.present["custom_field"] == "some-value"


class TestBuildOutlineSourceConfig:
    """Test the build_outline_source_config callback captured from create_outline."""

    _default_kwargs = dict(
        collection="outline",
        url="https://app.getoutline.com",
        token=None,
        collection_id=None,
        include_attachments=True,
        ocr=True,
        use_cache=True,
        force=False,
        verbose=False,
        json_logs=False,
        log_level=None,
        local=False,
    )

    @patch("indexed.knowledge.commands.create.execute_create_command")
    @patch("indexed.knowledge.commands.create.ConfigService")
    @patch("indexed.knowledge.commands.create.is_verbose_mode")
    @patch("indexed.knowledge.commands.create.console")
    def test_build_source_config_creates_outline_config(
        self, mock_console, mock_verbose, mock_config_service, mock_execute
    ):
        """Should build SourceConfig with outline type and correct URL."""
        import sys
        from indexed.knowledge.commands.create import create_outline

        captured: dict = {}

        def capture_kwargs(**kwargs: object) -> None:
            captured.update(kwargs)

        mock_execute.side_effect = capture_kwargs
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        MockSourceConfig = Mock(return_value=Mock())
        MockIndexer = "flat"

        with patch.dict(
            sys.modules,
            {
                "core.v1.engine.services": Mock(SourceConfig=MockSourceConfig),
                "core.v1.constants": Mock(DEFAULT_INDEXER=MockIndexer),
            },
        ):
            create_outline(**self._default_kwargs)

        build_fn = captured.get("build_source_config")
        assert build_fn is not None

        present = {"url": "https://app.getoutline.com", "collection_ids": ["col-1"]}
        with patch.dict(
            sys.modules,
            {
                "core.v1.engine.services": Mock(SourceConfig=MockSourceConfig),
                "core.v1.constants": Mock(DEFAULT_INDEXER=MockIndexer),
            },
        ):
            build_fn(present, "my-outline")

        MockSourceConfig.assert_called_once()
        call_kwargs = MockSourceConfig.call_args.kwargs
        assert call_kwargs["name"] == "my-outline"
        assert call_kwargs["base_url_or_path"] == "https://app.getoutline.com"
