"""Tests for simple_output utility."""

import os
from unittest.mock import MagicMock, patch

import pytest

from indexed.utils.simple_output import (
    is_simple_output,
    print_json,
    reset_simple_output,
    set_simple_output,
)

CONFIG_SERVICE_PATH = "indexed_config.ConfigService"


@pytest.fixture(autouse=True)
def _reset_flag():
    """Reset the module-level flag before and after each test."""
    reset_simple_output()
    yield
    reset_simple_output()


class TestIsSimpleOutput:
    """Tests for is_simple_output function."""

    def test_default_is_false(self):
        """Default should be False with no flag, env, or config."""
        with patch.dict(os.environ, {}, clear=True):
            with patch(CONFIG_SERVICE_PATH) as mock_cs:
                mock_instance = MagicMock()
                mock_instance.load_raw.return_value = {}
                mock_cs.instance.return_value = mock_instance
                assert is_simple_output() is False

    def test_flag_true(self):
        """Setting the flag to True returns True."""
        set_simple_output(True)
        assert is_simple_output() is True

    def test_flag_false(self):
        """Setting the flag to False returns False."""
        set_simple_output(False)
        assert is_simple_output() is False

    def test_flag_overrides_env(self):
        """Flag should take precedence over env var."""
        set_simple_output(False)
        with patch.dict(os.environ, {"INDEXED_SIMPLE_OUTPUT": "true"}):
            assert is_simple_output() is False

    def test_env_var_true(self):
        """Env var 'true' should return True."""
        with patch.dict(os.environ, {"INDEXED_SIMPLE_OUTPUT": "true"}):
            assert is_simple_output() is True

    def test_env_var_1(self):
        """Env var '1' should return True."""
        with patch.dict(os.environ, {"INDEXED_SIMPLE_OUTPUT": "1"}):
            assert is_simple_output() is True

    def test_env_var_yes(self):
        """Env var 'yes' should return True."""
        with patch.dict(os.environ, {"INDEXED_SIMPLE_OUTPUT": "yes"}):
            assert is_simple_output() is True

    def test_env_var_false(self):
        """Env var 'false' should return False."""
        with patch.dict(os.environ, {"INDEXED_SIMPLE_OUTPUT": "false"}):
            assert is_simple_output() is False

    def test_env_var_0(self):
        """Env var '0' should return False."""
        with patch.dict(os.environ, {"INDEXED_SIMPLE_OUTPUT": "0"}):
            assert is_simple_output() is False

    @patch(CONFIG_SERVICE_PATH)
    def test_config_true(self, mock_config_service):
        """Config output.simple_output = True returns True."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {"output": {"simple_output": True}}
        mock_config_service.instance.return_value = mock_instance

        with patch.dict(os.environ, {}, clear=True):
            assert is_simple_output() is True

    @patch(CONFIG_SERVICE_PATH)
    def test_config_false(self, mock_config_service):
        """Config output.simple_output = False returns False."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {"output": {"simple_output": False}}
        mock_config_service.instance.return_value = mock_instance

        with patch.dict(os.environ, {}, clear=True):
            assert is_simple_output() is False

    @patch(CONFIG_SERVICE_PATH)
    def test_config_missing_section(self, mock_config_service):
        """Missing output section defaults to False."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {}
        mock_config_service.instance.return_value = mock_instance

        with patch.dict(os.environ, {}, clear=True):
            assert is_simple_output() is False

    @patch(CONFIG_SERVICE_PATH)
    def test_config_none_section(self, mock_config_service):
        """output section = None defaults to False."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {"output": None}
        mock_config_service.instance.return_value = mock_instance

        with patch.dict(os.environ, {}, clear=True):
            assert is_simple_output() is False

    @patch(CONFIG_SERVICE_PATH)
    def test_config_non_bool_value(self, mock_config_service):
        """Non-boolean config value defaults to False."""
        mock_instance = MagicMock()
        mock_instance.load_raw.return_value = {"output": {"simple_output": "yes"}}
        mock_config_service.instance.return_value = mock_instance

        with patch.dict(os.environ, {}, clear=True):
            assert is_simple_output() is False

    def test_env_overrides_config(self):
        """Env var should take precedence over config."""
        with patch.dict(os.environ, {"INDEXED_SIMPLE_OUTPUT": "true"}):
            # Config would return False, but env wins
            assert is_simple_output() is True

    @patch(CONFIG_SERVICE_PATH)
    def test_config_exception_falls_through(self, mock_config_service):
        """If ConfigService raises, default to False."""
        mock_config_service.instance.side_effect = RuntimeError("not initialized")

        with patch.dict(os.environ, {}, clear=True):
            assert is_simple_output() is False


class TestPrintJson:
    """Tests for print_json helper."""

    def test_prints_json(self, capsys):
        """Should print valid JSON to stdout."""
        import json

        print_json({"key": "value", "number": 42})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == {"key": "value", "number": 42}

    def test_handles_non_serializable(self, capsys):
        """Should use default=str for non-serializable types."""
        import json
        from pathlib import Path

        print_json({"path": Path("/tmp/test")})
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["path"] == "/tmp/test"


class TestResetSimpleOutput:
    """Tests for reset_simple_output."""

    def test_reset_clears_flag(self):
        """After reset, is_simple_output should fall back to env/config."""
        set_simple_output(True)
        assert is_simple_output() is True
        reset_simple_output()
        with patch.dict(os.environ, {}, clear=True):
            with patch(CONFIG_SERVICE_PATH) as mock_cs:
                mock_instance = MagicMock()
                mock_instance.load_raw.return_value = {}
                mock_cs.instance.return_value = mock_instance
                assert is_simple_output() is False
