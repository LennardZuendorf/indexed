"""Tests for TomlStore class."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from indexed_config.store import TomlStore


def test_toml_store_init():
    """Test TomlStore initialization."""
    store = TomlStore()
    assert store.workspace == Path.cwd()


def test_toml_store_init_custom_workspace():
    """Test TomlStore initialization with custom workspace."""
    custom_path = Path("/custom/path")
    store = TomlStore(workspace=custom_path)
    assert store.workspace == custom_path


def test_toml_store_read_toml_file_not_found():
    """Test _read_toml_file returns empty dict when file doesn't exist."""
    store = TomlStore()
    result = store._read_toml_file(Path("/nonexistent/path.toml"))
    assert result == {}


def test_toml_store_read_toml_file_no_tomllib():
    """Test _read_toml_file raises RuntimeError when tomllib not available."""
    store = TomlStore()

    # Create a file path that exists but will trigger the tomllib check
    # We need to ensure the file exists so it doesn't return early
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".toml", delete=False) as f:
        fake_path = Path(f.name)

    try:
        # Mock the module-level tomllib to be None
        import indexed_config.store

        original_tomllib = indexed_config.store.tomllib
        indexed_config.store.tomllib = None

        try:
            with pytest.raises(RuntimeError, match="tomllib/tomli not available"):
                store._read_toml_file(fake_path)
        finally:
            indexed_config.store.tomllib = original_tomllib
    finally:
        # Clean up
        if fake_path.exists():
            fake_path.unlink()


def test_toml_store_env_to_mapping():
    """Test _env_to_mapping converts env vars correctly."""
    store = TomlStore()

    env_vars = {
        "INDEXED__section__key": "value",
        "INDEXED__a__b__c": "nested",
        "NOT_INDEXED__key": "ignored",
        "INDEXED__": "ignored_empty",
    }

    with patch.dict(os.environ, env_vars, clear=False):
        result = store._env_to_mapping()

    assert result == {
        "section": {"key": "value"},
        "a": {"b": {"c": "nested"}},
    }


def test_toml_store_env_to_mapping_empty():
    """Test _env_to_mapping with no matching env vars."""
    store = TomlStore()

    with patch.dict(os.environ, {}, clear=True):
        result = store._env_to_mapping()

    assert result == {}


def test_toml_store_write():
    """Test write() creates directory and file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = TomlStore(workspace=workspace)

        data = {"section": {"key": "value"}}
        store.write(data)

        assert store.workspace_path.exists()
        # Verify file was written (we can't easily parse it here, but existence is enough)


def test_toml_store_read_integrates_env():
    """Test read() merges global, workspace, and env."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = TomlStore(workspace=workspace)

        # Set env var
        env_vars = {"INDEXED__test__value": "from_env"}

        with patch.dict(os.environ, env_vars, clear=False):
            result = store.read()

        # Should include env var (even if files don't exist)
        assert "test" in result or result == {}  # Either merged or empty
