"""Tests for config CLI commands."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typer.testing import CliRunner

from indexed.config.cli import (
    _coerce_value,
    _flatten_dict,
    _format_config_value,
    _group_config_by_section,
    _is_sensitive_key,
    _merge_with_defaults,
    _value_to_default_str,
    _get_sensitive_env_value,
    _load_external_toml,
    _backup_config,
    _group_keys_by_prefix,
)

runner = CliRunner()


class TestCoerceValue:
    """Test _coerce_value function."""

    def test_coerce_true_string(self):
        """Should coerce 'true' to boolean True."""
        assert _coerce_value("true") is True
        assert _coerce_value("True") is True
        assert _coerce_value("TRUE") is True

    def test_coerce_false_string(self):
        """Should coerce 'false' to boolean False."""
        assert _coerce_value("false") is False
        assert _coerce_value("False") is False
        assert _coerce_value("FALSE") is False

    def test_coerce_integer(self):
        """Should coerce numeric strings to integers."""
        assert _coerce_value("42") == 42
        assert _coerce_value("0") == 0
        assert _coerce_value("-10") == -10

    def test_coerce_float(self):
        """Should coerce float strings to floats."""
        assert _coerce_value("3.14") == 3.14
        assert _coerce_value("0.0") == 0.0
        assert _coerce_value("-2.5") == -2.5

    def test_coerce_json_list(self):
        """Should coerce JSON list strings to lists."""
        assert _coerce_value('["a", "b"]') == ["a", "b"]
        assert _coerce_value("[1, 2, 3]") == [1, 2, 3]

    def test_coerce_json_dict(self):
        """Should coerce JSON dict strings to dicts."""
        assert _coerce_value('{"key": "value"}') == {"key": "value"}

    def test_coerce_plain_string(self):
        """Should return plain strings unchanged."""
        assert _coerce_value("hello") == "hello"
        assert _coerce_value("path/to/file") == "path/to/file"


class TestFlattenDict:
    """Test _flatten_dict function."""

    def test_flat_dict(self):
        """Should handle already flat dicts."""
        result = _flatten_dict({"a": 1, "b": 2})
        assert result == {"a": 1, "b": 2}

    def test_nested_dict(self):
        """Should flatten nested dicts with dot notation."""
        result = _flatten_dict({"a": {"b": {"c": 1}}})
        assert result == {"a.b.c": 1}

    def test_mixed_dict(self):
        """Should flatten mixed nested and flat entries."""
        result = _flatten_dict({"a": 1, "b": {"c": 2}, "d": {"e": {"f": 3}}})
        assert result == {"a": 1, "b.c": 2, "d.e.f": 3}

    def test_empty_dict(self):
        """Should handle empty dicts."""
        assert _flatten_dict({}) == {}


class TestFormatConfigValue:
    """Test _format_config_value function."""

    def test_format_boolean(self):
        """Should format booleans as 'true'/'false'."""
        assert _format_config_value(True) == "true"
        assert _format_config_value(False) == "false"

    def test_format_empty_list(self):
        """Should format empty lists as '(empty)'."""
        assert _format_config_value([]) == "(empty)"

    def test_format_nonempty_list(self):
        """Should join list items with ', '."""
        assert _format_config_value(["a", "b"]) == "a, b"

    def test_format_empty_dict(self):
        """Should format empty dicts as '(empty)'."""
        assert _format_config_value({}) == "(empty)"

    def test_format_nonempty_dict(self):
        """Should format dicts as '(N items)'."""
        assert _format_config_value({"a": 1}) == "(1 items)"
        assert _format_config_value({"a": 1, "b": 2}) == "(2 items)"

    def test_format_none(self):
        """Should format None as '(not set)'."""
        assert _format_config_value(None) == "(not set)"

    def test_format_string(self):
        """Should return strings unchanged."""
        assert _format_config_value("hello") == "hello"


class TestIsSensitiveKey:
    """Test _is_sensitive_key function."""

    def test_api_token_key(self):
        """Should detect api_token keys as sensitive."""
        assert _is_sensitive_key("api_token") is True
        assert _is_sensitive_key("jira.api_token") is True

    def test_password_key(self):
        """Should detect password keys as sensitive."""
        assert _is_sensitive_key("password") is True
        assert _is_sensitive_key("jira.password") is True

    def test_token_key(self):
        """Should detect token keys as sensitive."""
        assert _is_sensitive_key("token") is True
        assert _is_sensitive_key("confluence.token") is True

    def test_secret_key(self):
        """Should detect secret keys as sensitive."""
        assert _is_sensitive_key("secret") is True
        assert _is_sensitive_key("app.secret") is True

    def test_non_sensitive_key(self):
        """Should not flag non-sensitive keys."""
        assert _is_sensitive_key("url") is False
        assert _is_sensitive_key("query") is False
        assert _is_sensitive_key("jira.url") is False


class TestInspect:
    """Test inspect command."""

    @patch("indexed.config.cli.ConfigService")
    def test_inspect_no_arguments(self, mock_config_service):
        """Should display full config overview without arguments."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {
            "sources": {"jira": {"url": "https://company.atlassian.net"}}
        }
        mock_config.get_workspace_config.return_value = {"mode": "local"}
        mock_config_service.instance.return_value = mock_config

        from indexed.app import app

        result = runner.invoke(app, ["config", "inspect"])
        assert result.exit_code == 0
        assert (
            "Configuration Overview" in result.stdout or "jira" in result.stdout.lower()
        )

    @patch("indexed.config.cli.ConfigService")
    def test_inspect_simple_output(self, mock_config_service):
        """Should output JSON when --simple-output flag is provided."""
        from indexed.utils.simple_output import reset_simple_output, set_simple_output

        mock_config = Mock()
        mock_config.load_raw.return_value = {"sources": {"files": {"path": "/data"}}}
        mock_config.get_workspace_config.return_value = None
        mock_config_service.instance.return_value = mock_config

        from indexed.app import app

        set_simple_output(True)
        try:
            result = runner.invoke(app, ["config", "inspect"])
            assert result.exit_code == 0
            assert "{" in result.stdout  # JSON output
        finally:
            reset_simple_output()


class TestSetConfig:
    """Test set command."""

    @patch("indexed.config.cli.ConfigService")
    def test_set_config_value(self, mock_config_service):
        """Should set a config value."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config.validate.return_value = []
        mock_config_service.instance.return_value = mock_config

        from indexed.app import app

        result = runner.invoke(
            app, ["config", "set", "core.v1.indexing.chunk_size", "1024"]
        )
        assert result.exit_code == 0
        mock_config.set.assert_called_once()

    @patch("indexed.config.cli.ConfigService")
    def test_set_config_dry_run(self, mock_config_service):
        """Should preview change without saving in dry-run mode."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config_service.instance.return_value = mock_config

        from indexed.app import app

        result = runner.invoke(
            app,
            ["config", "set", "core.v1.indexing.chunk_size", "1024", "--dry-run"],
        )
        assert result.exit_code == 0
        assert (
            "Preview" in result.stdout
            or "Dry-run" in result.stdout
            or "not saved" in result.stdout
        )


class TestDeleteConfig:
    """Test delete command."""

    @patch("indexed.config.cli.ConfigService")
    def test_delete_nonexistent_key(self, mock_config_service):
        """Should inform user when key does not exist."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config_service.instance.return_value = mock_config

        from indexed.app import app

        result = runner.invoke(
            app,
            ["config", "delete", "nonexistent.key"],
            input="n\n",  # Confirm deletion
        )
        # May exit with 0 and print info message
        assert result.exit_code in [0, 1]

    @patch("indexed.config.cli.ConfigService")
    def test_delete_existing_key_with_force(self, mock_config_service):
        """Should delete key with --force flag."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {
            "sources": {"jira": {"url": "https://test.com"}}
        }
        mock_config.delete.return_value = True
        mock_config_service.instance.return_value = mock_config

        from indexed.app import app

        result = runner.invoke(app, ["config", "delete", "sources.jira.url", "--force"])
        assert result.exit_code == 0
        mock_config.delete.assert_called_once_with("sources.jira.url")


class TestValidate:
    """Test validate command."""

    @patch("indexed.config.cli.ConfigService")
    def test_validate_success(self, mock_config_service):
        """Should report success when config is valid."""
        mock_config = Mock()
        mock_config.validate.return_value = []
        mock_config_service.instance.return_value = mock_config

        from indexed.app import app

        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()

    @patch("indexed.config.cli.ConfigService")
    def test_validate_failure(self, mock_config_service):
        """Should report errors when config is invalid."""
        mock_config = Mock()
        mock_config.validate.return_value = [
            ("sources.jira.url", "URL format is invalid"),
        ]
        mock_config_service.instance.return_value = mock_config

        from indexed.app import app

        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 1
        assert "error" in result.stdout.lower() or "invalid" in result.stdout.lower()


class TestInitConfig:
    """Test init command."""

    @patch("indexed.config.cli.Path")
    @patch("indexed.config.cli.print_success")
    @patch("indexed.config.cli.print_warning")
    def test_init_creates_files(self, mock_warning, mock_success, mock_path):
        """Should create config.toml and .env.example."""
        from pathlib import Path as RealPath

        # Mock current working directory
        mock_cwd = MagicMock(spec=RealPath)

        # Mock workspace directory (.indexed)
        mock_workspace_dir = MagicMock(spec=RealPath)
        mock_workspace_dir.exists.return_value = False
        mock_workspace_dir.mkdir = Mock()

        # Mock config.toml file
        mock_config_file = MagicMock(spec=RealPath)
        mock_config_file.exists.return_value = False
        mock_config_file.write_text = Mock()
        mock_config_file.name = "config.toml"

        # Mock .env.example file
        mock_env_example = MagicMock(spec=RealPath)
        mock_env_example.exists.return_value = False
        mock_env_example.write_text = Mock()
        mock_env_example.name = ".env.example"

        # Set up Path.cwd() to return mock_cwd
        mock_path.cwd.return_value = mock_cwd

        # Set up the / operator: cwd / ".indexed" -> workspace_dir
        # workspace_dir / "config.toml" -> config_file
        # workspace_dir / ".env.example" -> env_example
        def truediv_side_effect(self, other):
            if self == mock_cwd and other == ".indexed":
                return mock_workspace_dir
            elif self == mock_workspace_dir and other == "config.toml":
                return mock_config_file
            elif self == mock_workspace_dir and other == ".env.example":
                return mock_env_example
            return MagicMock(spec=RealPath)

        # Make the / operator work by setting __truediv__ on the class
        type(mock_cwd).__truediv__ = truediv_side_effect
        type(mock_workspace_dir).__truediv__ = truediv_side_effect

        from indexed.app import app

        result = runner.invoke(app, ["config", "init"])

        # Verify the command succeeded
        assert result.exit_code == 0

        # Verify workspace directory was created with correct arguments
        mock_workspace_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

        # Verify both files were written
        assert mock_config_file.write_text.called, "config.toml should be written"
        assert mock_env_example.write_text.called, ".env.example should be written"

        # Verify write_text was called with expected content
        config_call_args = mock_config_file.write_text.call_args
        assert config_call_args is not None, (
            "write_text should be called on config.toml"
        )
        config_content = config_call_args[0][0] if config_call_args[0] else ""
        assert "# Indexed Configuration" in config_content, (
            "config.toml should contain expected header"
        )
        assert "[core.v1.indexing]" in config_content, (
            "config.toml should contain indexing config"
        )

        env_call_args = mock_env_example.write_text.call_args
        assert env_call_args is not None, "write_text should be called on .env.example"
        env_content = env_call_args[0][0] if env_call_args[0] else ""
        assert "# Indexed Environment Variables" in env_content, (
            ".env.example should contain expected header"
        )
        assert "ATLASSIAN_EMAIL" in env_content, (
            ".env.example should contain environment variable examples"
        )

    @patch("indexed.config.cli.Path")
    @patch("indexed.config.cli.print_warning")
    def test_init_already_initialized(self, mock_warning, mock_path):
        """Should warn when workspace already initialized."""
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = True
        mock_path.cwd.return_value = mock_path_obj
        mock_path.return_value = mock_path_obj

        from indexed.app import app

        result = runner.invoke(app, ["config", "init"])
        # Should exit with warning about already initialized
        assert result.exit_code == 1


class TestValueToDefaultStr:
    """Test _value_to_default_str function."""

    def test_bool_true(self):
        """Should convert True to 'true'."""
        assert _value_to_default_str(True) == "true"

    def test_bool_false(self):
        """Should convert False to 'false'."""
        assert _value_to_default_str(False) == "false"

    def test_none(self):
        """Should convert None to empty string."""
        assert _value_to_default_str(None) == ""

    def test_list(self):
        """Should convert lists to JSON string."""
        assert _value_to_default_str([1, 2]) == "[1, 2]"

    def test_dict(self):
        """Should convert dicts to JSON string."""
        assert _value_to_default_str({"a": 1}) == '{"a": 1}'

    def test_integer(self):
        """Should convert integers to string."""
        assert _value_to_default_str(42) == "42"

    def test_string(self):
        """Should return strings unchanged."""
        assert _value_to_default_str("hello") == "hello"


class TestGroupConfigBySection:
    """Test _group_config_by_section function."""

    def test_flat_config(self):
        """Should group flat keys by first segment."""
        result = _group_config_by_section({"sources": {"jira": {"url": "x"}}})
        assert "sources" in result
        assert "jira.url" in result["sources"]

    def test_nested_config(self):
        """Should flatten nested config into dot-paths grouped by section."""
        config = {"core": {"v1": {"search": {"max_docs": 10}}}}
        result = _group_config_by_section(config)
        assert "core" in result
        assert "v1.search.max_docs" in result["core"]

    def test_empty_config(self):
        """Should return empty dict for empty config."""
        assert _group_config_by_section({}) == {}

    def test_multiple_sections(self):
        """Should separate keys into their respective sections."""
        config = {
            "sources": {"files": {"path": "/data"}},
            "logging": {"level": "INFO"},
        }
        result = _group_config_by_section(config)
        assert set(result.keys()) == {"sources", "logging"}


class TestMergeWithDefaults:
    """Test _merge_with_defaults function."""

    def test_manual_values_marked_correctly(self):
        """Manual values should have is_default=False."""
        raw = {"core": {"v1": {"search": {"max_docs": 20}}}}
        defaults = {"core": {"v1": {"search": {"max_docs": 10}}}}
        result = _merge_with_defaults(raw, defaults)
        assert result["core"]["v1.search.max_docs"]["is_default"] is False
        assert result["core"]["v1.search.max_docs"]["value"] == 20

    def test_default_values_marked_correctly(self):
        """Default-only values should have is_default=True."""
        raw = {}
        defaults = {"core": {"v1": {"search": {"max_docs": 10}}}}
        result = _merge_with_defaults(raw, defaults)
        assert result["core"]["v1.search.max_docs"]["is_default"] is True
        assert result["core"]["v1.search.max_docs"]["value"] == 10

    def test_empty_inputs(self):
        """Should handle empty raw and defaults."""
        assert _merge_with_defaults({}, {}) == {}

    def test_workspace_section_skipped(self):
        """Workspace section should be excluded from output."""
        raw = {"workspace": {"mode": "local"}, "logging": {"level": "INFO"}}
        defaults = {}
        result = _merge_with_defaults(raw, defaults)
        assert "workspace" not in result
        assert "logging" in result


class TestGetSensitiveEnvValue:
    """Test _get_sensitive_env_value function."""

    def test_returns_masked_when_env_set(self):
        """Should return masked value when corresponding env var is set."""
        os.environ["ATLASSIAN_TOKEN"] = "secret"
        try:
            result = _get_sensitive_env_value("api_token")
            assert result == "*****"
        finally:
            del os.environ["ATLASSIAN_TOKEN"]

    def test_returns_none_when_env_not_set(self):
        """Should return None when no corresponding env var is set."""
        # Ensure env vars are not set
        for var in ["ATLASSIAN_TOKEN", "JIRA_TOKEN", "CONF_TOKEN"]:
            os.environ.pop(var, None)
        result = _get_sensitive_env_value("api_token")
        assert result is None

    def test_non_sensitive_key_returns_none(self):
        """Should return None for non-sensitive keys."""
        assert _get_sensitive_env_value("url") is None

    def test_dotpath_key_extracts_last_segment(self):
        """Should use last segment of dot-path for lookup."""
        os.environ["ATLASSIAN_EMAIL"] = "test@example.com"
        try:
            result = _get_sensitive_env_value("sources.jira.email")
            assert result == "*****"
        finally:
            del os.environ["ATLASSIAN_EMAIL"]


class TestGroupKeysByPrefix:
    """Test _group_keys_by_prefix function."""

    def test_groups_dotted_keys(self):
        """Should group keys by first part before dot."""
        keys = ["files.path", "files.include_patterns", "jira.url"]
        result = _group_keys_by_prefix(keys)
        assert set(result.keys()) == {"files", "jira"}
        assert len(result["files"]) == 2
        assert len(result["jira"]) == 1

    def test_simple_keys_go_to_general(self):
        """Keys without dots should go to 'general' group."""
        keys = ["level", "mode"]
        result = _group_keys_by_prefix(keys)
        assert "general" in result
        assert len(result["general"]) == 2

    def test_empty_list(self):
        """Should return empty dict for empty input."""
        assert _group_keys_by_prefix([]) == {}


class TestLoadExternalToml:
    """Test _load_external_toml function."""

    def test_loads_valid_toml(self):
        """Should parse valid TOML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[test]\nkey = "value"\n')
            f.flush()
            result = _load_external_toml(f.name)
            assert result == {"test": {"key": "value"}}
        os.unlink(f.name)

    def test_returns_none_for_missing_file(self):
        """Should return None when file does not exist."""
        result = _load_external_toml("/nonexistent/path/config.toml")
        assert result is None

    def test_returns_none_for_invalid_toml(self):
        """Should return None for malformed TOML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("this is not valid toml [[[")
            f.flush()
            result = _load_external_toml(f.name)
            assert result is None
        os.unlink(f.name)

    def test_returns_none_for_directory(self):
        """Should return None when path is a directory, not a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _load_external_toml(tmpdir)
            assert result is None


class TestBackupConfig:
    """Test _backup_config function."""

    def test_creates_backup_file(self):
        """Should create a timestamped backup of existing config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text('[test]\nkey = "value"\n')

            result = _backup_config(config_path)
            assert result is True

            # Should have created a backup file
            backups = list(Path(tmpdir).glob("config.toml.backup.*"))
            assert len(backups) == 1
            assert backups[0].read_text() == '[test]\nkey = "value"\n'

    def test_returns_true_when_no_file(self):
        """Should return True (nothing to backup) when file doesn't exist."""
        result = _backup_config(Path("/nonexistent/config.toml"))
        assert result is True
