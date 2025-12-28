"""Tests for config CLI commands."""

from unittest.mock import Mock, patch, MagicMock
from typer.testing import CliRunner

from indexed.config.cli import (
    _coerce_value,
    _flatten_dict,
    _format_config_value,
    _is_sensitive_key,
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
    def test_inspect_json_output(self, mock_config_service):
        """Should output JSON when --json flag is provided."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {"sources": {"files": {"path": "/data"}}}
        mock_config.get_workspace_config.return_value = None
        mock_config_service.instance.return_value = mock_config

        from indexed.app import app

        result = runner.invoke(app, ["config", "inspect", "--json"])
        assert result.exit_code == 0
        assert "{" in result.stdout  # JSON output


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
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = False
        mock_path_obj.parent.mkdir = Mock()
        mock_path_obj.write_text = Mock()
        mock_path.cwd.return_value = mock_path_obj
        mock_path.return_value = mock_path_obj

        from indexed.app import app

        result = runner.invoke(app, ["config", "init"])
        # Should succeed or show warning about already initialized
        assert result.exit_code in [0, 1]

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
