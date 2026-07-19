"""Tests for config CLI commands."""

from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from indexed.config.cli import (
    _coerce_value,
    _flatten_dict,
    _format_config_value,
    _is_sensitive_key,
    _mask_sensitive_raw,
    _masked_config_value,
    _merge_with_defaults,
)

pytestmark = pytest.mark.unit

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


class TestMaskedConfigValue:
    """Test _masked_config_value function (C1)."""

    def test_masks_sensitive_value(self):
        """A set sensitive value must render as a fixed mask, not plaintext."""
        assert _masked_config_value("sources.jira.api_token", "supersecret123") == (
            "*****"
        )

    def test_does_not_mask_non_sensitive_value(self):
        """Non-sensitive keys must render normally."""
        assert _masked_config_value("sources.jira.url", "https://x.test") == (
            "https://x.test"
        )

    def test_unset_sensitive_value_not_masked_as_secret(self):
        """An unset sensitive key still shows '(not set)', not a mask."""
        assert _masked_config_value("sources.jira.api_token", None) == "(not set)"


class TestMaskSensitiveRaw:
    """Test _mask_sensitive_raw function (C1 — --simple-output JSON path)."""

    def test_masks_nested_sensitive_leaf(self):
        raw = {"sources": {"jira": {"api_token": "supersecret123", "url": "x"}}}
        masked = _mask_sensitive_raw(raw)
        assert masked["sources"]["jira"]["api_token"] == "*****"
        assert masked["sources"]["jira"]["url"] == "x"

    def test_leaves_non_sensitive_data_untouched(self):
        raw = {"core": {"v1": {"indexing": {"chunk_size": 512}}}}
        assert _mask_sensitive_raw(raw) == raw


class TestList:
    """Test list command (folds the former inspect resolved-config view)."""

    @patch("indexed.config.commands.list.get_config")
    def test_list_no_arguments(self, mock_config_service):
        """Should display full config overview without arguments."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {
            "sources": {"jira": {"url": "https://company.atlassian.net"}}
        }
        mock_config.get_workspace_config.return_value = {"mode": "local"}
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert (
            "Configuration Overview" in result.stdout or "jira" in result.stdout.lower()
        )

    @patch("indexed.config.commands.list.get_config")
    def test_list_simple_output(self, mock_config_service):
        """Should output JSON when --simple-output flag is provided."""
        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        mock_config = Mock()
        mock_config.load_raw.return_value = {"sources": {"files": {"path": "/data"}}}
        mock_config.get_workspace_config.return_value = None
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        set_simple_output(True)
        try:
            result = runner.invoke(app, ["config", "list"])
            assert result.exit_code == 0
            assert "{" in result.stdout  # JSON output
        finally:
            reset_simple_output()

    @patch("indexed.config.commands.list.get_config")
    def test_list_shows_manually_set_core_value_without_show_defaults(
        self, mock_config_service
    ):
        """R8: a manually-set core value must render in plain `config list`
        (no --show-defaults) — the Core Settings panel must not be gated on
        show_defaults when should_show_key already says to include the row."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {
            "core": {"v1": {"indexing": {"chunk_size": 256}}}
        }
        mock_config.get_workspace_config.return_value = None
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0, result.stdout
        assert "256" in result.stdout

    @patch("indexed.config.commands.list.get_config")
    def test_list_shows_manually_set_logging_value_without_show_defaults(
        self, mock_config_service
    ):
        """R8: a manually-set logging value must render in plain `config
        list` — the logging/mcp/performance panel must not be gated on
        show_defaults when should_show_key already says to include the row."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {"logging": {"level": "DEBUG"}}
        mock_config.get_workspace_config.return_value = None
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0, result.stdout
        assert "DEBUG" in result.stdout

    @patch("indexed.config.commands.list.get_config")
    def test_list_simple_output_masks_secret(self, mock_config_service):
        """C1: a secret reaching merged config must be masked in JSON output."""
        from indexed.cli.utils.simple_output import (
            reset_simple_output,
            set_simple_output,
        )

        mock_config = Mock()
        mock_config.load_raw.return_value = {
            "sources": {"jira": {"api_token": "supersecret123"}}
        }
        mock_config.get_workspace_config.return_value = None
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        set_simple_output(True)
        try:
            result = runner.invoke(app, ["config", "list"])
            assert result.exit_code == 0
            assert "supersecret123" not in result.stdout
            assert "*****" in result.stdout
        finally:
            reset_simple_output()


class TestListMarkupSafety:
    """R7 — user-controlled/user-settable strings reaching ``config list``'s
    markup-parsed sinks must render literally, never crash or be dropped."""

    @patch("indexed.config.commands.list.get_config")
    def test_section_filter_renders_brackets_literally(self, mock_config_service):
        """The ``section`` CLI argument is user-controlled and is embedded
        raw in the "Configuration: ..." heading.

        Rich's markup tag grammar matches a bracket run starting with a
        lowercase letter/#//@; ``.title()`` (applied to the section name
        before display) capitalizes the letter right after "[", which
        neuters a plain "[section]" fixture — a "/"-led bracket survives
        title-casing (``"weird[/x]".title() == "Weird[/X]"``) and reliably
        reproduces the real failure mode: an unmatched closing tag raises
        ``rich.errors.MarkupError`` today (uncaught → CliRunner sees it via
        ``result.exception``), rather than merely dropping text.
        """
        mock_config = Mock()
        mock_config.load_raw.return_value = {"sources": {"jira": {"url": "https://x"}}}
        mock_config.get_workspace_config.return_value = None
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "list", "weird[/x]"])
        assert result.exit_code == 0, result.stdout
        assert "Weird[/X]" in result.stdout

    @patch("indexed.config.commands.list.get_config")
    def test_summary_section_name_renders_brackets_literally(self, mock_config_service):
        """A top-level config section name is user-settable via
        ``config set <arbitrary.key> <value>`` — it reaches the "Overall: N
        keys set manually for ..." summary line raw."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {"weird[section]": {"key": "v"}}
        mock_config.get_workspace_config.return_value = None
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0, result.stdout
        assert "weird[section]" in result.stdout


class TestGetConfig:
    """Test get command."""

    @patch("indexed.config.commands.get._resolve_config")
    def test_get_existing_key(self, mock_config_service):
        """Should render the value at a dot-path from merged config."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {
            "core": {"v1": {"indexing": {"chunk_size": 1024}}}
        }
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "get", "core.v1.indexing.chunk_size"])
        assert result.exit_code == 0
        assert "1024" in result.stdout

    @patch("indexed.config.commands.get._resolve_config")
    def test_get_masks_secret(self, mock_config_service):
        """C1: a sensitive value must be masked, never echoed in cleartext."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {
            "sources": {"jira": {"api_token": "supersecret123"}}
        }
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "get", "sources.jira.api_token"])
        assert result.exit_code == 0
        assert "supersecret123" not in result.stdout
        assert "*****" in result.stdout

    @patch("indexed.config.commands.get._resolve_config")
    def test_get_masks_nested_secret_in_simple_output(self, mock_config_service):
        """C1: --simple-output on an ancestor/section path must recursively mask
        nested secret leaves, never dumping them in cleartext."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {
            "sources": {
                "jira": {
                    "url": "https://x.atlassian.net",
                    "api_token": "supersecret123",
                }
            }
        }
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(
            app, ["--simple-output", "config", "get", "sources.jira"]
        )
        assert result.exit_code == 0
        assert "supersecret123" not in result.stdout
        assert "*****" in result.stdout
        # non-secret sibling value is preserved for scripting
        assert "atlassian.net" in result.stdout

    @patch("indexed.config.commands.get._resolve_config")
    def test_get_missing_key(self, mock_config_service):
        """Should inform the user when the key is not set."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "get", "nonexistent.key"])
        assert result.exit_code == 0
        assert "not found" in result.stdout.lower()

    @patch("indexed.config.commands.get._resolve_config")
    def test_get_core_engine_unset_shows_effective_default(self, mock_config_service):
        """UX finding L2: with no explicit ``[core] engine``, `config get
        core.engine` must surface the effective default ("1") marked as a
        default, not "Key not found"."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "get", "core.engine"])
        assert result.exit_code == 0
        assert "not found" not in result.stdout.lower()
        assert "1" in result.stdout
        assert "default" in result.stdout.lower()

    @patch("indexed.config.commands.get._resolve_config")
    def test_get_core_engine_explicit_value_not_marked_default(
        self, mock_config_service
    ):
        """When ``core.engine`` IS explicitly set, show the set value as-is
        with no "(default)" marker."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {"core": {"engine": "2"}}
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "get", "core.engine"])
        assert result.exit_code == 0
        assert "2" in result.stdout
        assert "default" not in result.stdout.lower()

    @patch("indexed.config.commands.get._resolve_config")
    def test_get_missing_key_still_not_found(self, mock_config_service):
        """A genuinely unknown key (not ``core.engine``) still says "Key not
        found" — only ``core.engine`` gets the default-resolution treatment."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "get", "core.v1.embedding.bogus"])
        assert result.exit_code == 0
        assert "not found" in result.stdout.lower()


class TestSetConfig:
    """Test set command."""

    @patch("indexed.config.commands.set.get_config")
    def test_set_config_value(self, mock_config_service):
        """Should set a config value."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config.validate.return_value = []
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(
            app, ["config", "set", "core.v1.indexing.chunk_size", "1024"]
        )
        assert result.exit_code == 0
        # Non-sensitive keys route through set_value() (which itself calls
        # set() on a real ConfigService); field_info marks it not-sensitive.
        mock_config.set_value.assert_called_once_with(
            "core.v1.indexing.chunk_size", 1024, field_info={"sensitive": False}
        )

    @patch("indexed.config.commands.set.get_config")
    def test_set_config_secret_routes_to_env_and_masks_output(
        self, mock_config_service
    ):
        """C1: a sensitive key must route to .env (sensitive=True) and never
        echo the plaintext value to stdout. It must also resolve the
        connector-declared env var name (via resolve_sensitive_env_var) and
        pass it through as field_info["env_var"], so the secret lands where
        the connector actually reads it (foundation/4 review finding 1)."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config.validate.return_value = []
        mock_config.resolve_sensitive_env_var.return_value = "ATLASSIAN_TOKEN"
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(
            app, ["config", "set", "sources.jira.api_token", "supersecret123"]
        )
        assert result.exit_code == 0
        assert "supersecret123" not in result.stdout
        mock_config.resolve_sensitive_env_var.assert_called_once_with(
            "sources.jira.api_token"
        )
        mock_config.set_value.assert_called_once_with(
            "sources.jira.api_token",
            "supersecret123",
            field_info={"sensitive": True, "env_var": "ATLASSIAN_TOKEN"},
        )
        # set() (the plaintext-TOML path) must never be called directly.
        mock_config.set.assert_not_called()

    @patch("indexed.config.commands.set.get_config")
    def test_set_config_secret_unmapped_key_warns_and_falls_back(
        self, mock_config_service
    ):
        """A sensitive key with no registered connector mapping must still be
        saved (best-effort fallback to the last dot-path segment, uppercased)
        but must surface a warning rather than claim unconditional success."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config.validate.return_value = []
        mock_config.resolve_sensitive_env_var.return_value = None
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(
            app, ["config", "set", "sources.unknown.api_token", "supersecret123"]
        )
        assert result.exit_code == 0
        assert "supersecret123" not in result.stdout
        mock_config.set_value.assert_called_once_with(
            "sources.unknown.api_token",
            "supersecret123",
            field_info={"sensitive": True},
        )
        assert "no connector mapping" in result.stdout.lower()

    def test_set_config_secret_lands_at_connector_readable_env_key(
        self, local_workspace
    ):
        """Regression (foundation/4 review finding 1): the secret written by
        ``config set sources.jira.api_token <value>`` must land at the .env
        key the jira connector actually reads (JiraCloudConfig.api_token's
        ``env: ATLASSIAN_TOKEN`` hint) — not the naive last-segment fallback
        ``API_TOKEN``, which no connector reads. Drives the real CLI + a real
        (unmocked) ConfigService so the connector registry is populated the
        way production populates it."""
        from indexed.connectors.jira.schema import JiraCloudConfig
        from indexed.cli.app import app
        from indexed.config.env_writer import EnvFileWriter

        expected_var = EnvFileWriter.get_env_var_name(
            "api_token", JiraCloudConfig.model_fields["api_token"]
        )
        assert expected_var == "ATLASSIAN_TOKEN"

        result = runner.invoke(
            app,
            [
                "--local",
                "--log-level",
                "ERROR",
                "config",
                "set",
                "sources.jira.api_token",
                "supersecret123",
            ],
        )
        assert result.exit_code == 0, result.stdout

        env_path = local_workspace.local_root / ".env"
        assert env_path.exists(), ".env must be created"
        env_text = env_path.read_text()

        assert f"{expected_var}=" in env_text, (
            f"secret must be written under the connector-readable key "
            f"{expected_var!r}, got: {env_text!r}"
        )
        assert "API_TOKEN=" not in env_text, (
            "secret must not land under the naive fallback key API_TOKEN "
            f"(got: {env_text!r})"
        )

        from dotenv import dotenv_values

        assert dotenv_values(str(env_path)).get(expected_var) == "supersecret123"

    @patch("indexed.config.commands.set.get_config")
    def test_set_config_validation_warning_renders_brackets_literally(
        self, mock_config_service
    ):
        """R7: a Pydantic ValidationError message can echo the rejected
        input value verbatim — it must render literally in the
        validation-warnings loop, never be parsed as markup (which would
        drop it or raise MarkupError).

        Uses a bracket run starting with a letter ("[value]") rather than a
        digit, matching Rich's markup tag grammar (``[a-z#/@]`` as the first
        character) — a digit-led bracket like "[1]" is never parsed as a tag
        at all, so it wouldn't actually exercise the sink.
        """
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config.validate.return_value = [
            ("sources.jira.url", "URL format invalid: bad[value]"),
        ]
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(
            app, ["config", "set", "sources.jira.url", "http://example.com"]
        )
        assert result.exit_code == 0, result.stdout
        assert "URL format invalid: bad[value]" in result.stdout

    @patch("indexed.config.commands.set.get_config")
    def test_set_config_location_with_brackets_renders_literally(
        self, mock_config_service
    ):
        """R7: ``config.store.resolved_config_path()`` is a filesystem path
        that may contain the user's workspace/home directory name — must
        render literally in the "Location: ..." line. (Letter-led bracket —
        see the validation-warning test above for why a digit-led one like
        "[1]" would not exercise Rich's markup parser at all.)"""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config.validate.return_value = []
        mock_config.store.resolved_config_path.return_value = (
            "/tmp/proj[x]/.indexed/config.toml"
        )
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(
            app, ["config", "set", "core.v1.indexing.chunk_size", "1024"]
        )
        assert result.exit_code == 0, result.stdout
        assert "proj[x]" in result.stdout

    @patch("indexed.config.commands.set.get_config")
    def test_set_config_dry_run(self, mock_config_service):
        """Should preview change without saving in dry-run mode."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

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

    @patch("indexed.config.commands.set.get_config")
    def test_set_config_engine_normalizes_friendly_alias(self, mock_config_service):
        """C2 regression: ``config set core.engine v2`` must persist the
        canonical "2", not the raw "v2" (which the engine-selector resolution
        path — and a later ``index create`` — would reject)."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config.validate.return_value = []
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "set", "core.engine", "v2"])
        assert result.exit_code == 0, result.stdout
        mock_config.set_value.assert_called_once_with(
            "core.engine", "2", field_info={"sensitive": False}
        )

    @patch("indexed.config.commands.set.get_config")
    def test_set_config_engine_rejects_bad_value(self, mock_config_service):
        """C2 regression: ``config set core.engine v3`` must be rejected at
        write time (naming the accepted forms) instead of being persisted and
        crashing a later ``index create``."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "set", "core.engine", "v3"])
        assert result.exit_code == 1
        assert "v1" in result.stdout.lower()
        mock_config.set_value.assert_not_called()


class TestValidate:
    """Test validate command."""

    @patch("indexed.config.commands.validate.get_config")
    def test_validate_success(self, mock_config_service):
        """Should report success when config is valid."""
        mock_config = Mock()
        mock_config.validate.return_value = []
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()

    @patch("indexed.config.commands.validate.get_config")
    def test_validate_failure(self, mock_config_service):
        """Should report errors when config is invalid."""
        mock_config = Mock()
        mock_config.validate.return_value = [
            ("sources.jira.url", "URL format is invalid"),
        ]
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 1
        assert "error" in result.stdout.lower() or "invalid" in result.stdout.lower()


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
