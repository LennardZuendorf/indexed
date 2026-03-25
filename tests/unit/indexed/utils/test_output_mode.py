"""Tests for output_mode utility."""

from unittest.mock import MagicMock, patch

from indexed.utils.output_mode import should_output_json


class TestShouldOutputJson:
    """Tests for should_output_json function."""

    def test_flag_true_returns_true(self):
        """Explicit True flag always returns True regardless of context."""
        assert should_output_json("cli", flag_value=True) is True
        assert should_output_json("mcp", flag_value=True) is True

    def test_flag_false_returns_false(self):
        """Explicit False flag always returns False regardless of context."""
        assert should_output_json("cli", flag_value=False) is False
        assert should_output_json("mcp", flag_value=False) is False

    @patch("indexed.utils.output_mode.ConfigService")
    def test_cli_context_config_true(self, mock_config_service):
        """CLI context returns True when config flags.cli_json_output is True."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {"flags": {"cli_json_output": True}}
        mock_config_service.instance.return_value = mock_instance

        assert should_output_json("cli") is True

    @patch("indexed.utils.output_mode.ConfigService")
    def test_cli_context_config_false(self, mock_config_service):
        """CLI context returns False when config flags.cli_json_output is False."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {"flags": {"cli_json_output": False}}
        mock_config_service.instance.return_value = mock_instance

        assert should_output_json("cli") is False

    @patch("indexed.utils.output_mode.ConfigService")
    def test_cli_context_missing_config(self, mock_config_service):
        """CLI context defaults to False when config key is missing."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {}
        mock_config_service.instance.return_value = mock_instance

        assert should_output_json("cli") is False

    @patch("indexed.utils.output_mode.ConfigService")
    def test_cli_context_non_bool_config(self, mock_config_service):
        """CLI context defaults to False when config value is not boolean."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {"flags": {"cli_json_output": "yes"}}
        mock_config_service.instance.return_value = mock_instance

        assert should_output_json("cli") is False

    @patch("indexed.utils.output_mode.ConfigService")
    def test_mcp_context_config_true(self, mock_config_service):
        """MCP context returns True when config mcp.mcp_json_output is True."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {"mcp": {"mcp_json_output": True}}
        mock_config_service.instance.return_value = mock_instance

        assert should_output_json("mcp") is True

    @patch("indexed.utils.output_mode.ConfigService")
    def test_mcp_context_config_false(self, mock_config_service):
        """MCP context returns False when config mcp.mcp_json_output is False."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {"mcp": {"mcp_json_output": False}}
        mock_config_service.instance.return_value = mock_instance

        assert should_output_json("mcp") is False

    @patch("indexed.utils.output_mode.ConfigService")
    def test_mcp_context_missing_config_defaults_true(self, mock_config_service):
        """MCP context defaults to True when config key is missing."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {}
        mock_config_service.instance.return_value = mock_instance

        assert should_output_json("mcp") is True

    @patch("indexed.utils.output_mode.ConfigService")
    def test_mcp_context_non_bool_config_defaults_true(self, mock_config_service):
        """MCP context defaults to True when config value is not boolean."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {"mcp": {"mcp_json_output": "yes"}}
        mock_config_service.instance.return_value = mock_instance

        assert should_output_json("mcp") is True

    @patch("indexed.utils.output_mode.ConfigService")
    def test_cli_no_flags_section(self, mock_config_service):
        """CLI context returns False when flags section is None."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {"flags": None}
        mock_config_service.instance.return_value = mock_instance

        assert should_output_json("cli") is False
