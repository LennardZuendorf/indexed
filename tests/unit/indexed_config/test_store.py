"""Tests for TomlStore class."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from indexed.config.store import TomlStore


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
        import indexed.config.store

        original_tomllib = indexed.config.store.tomllib
        indexed.config.store.tomllib = None

        try:
            with pytest.raises(RuntimeError, match="tomllib/tomli not available"):
                store._read_toml_file(fake_path)
        finally:
            indexed.config.store.tomllib = original_tomllib
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
    """Test write() creates directory and file in local mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = TomlStore(workspace=workspace, mode_override="local")

        data = {"section": {"key": "value"}}
        store.write(data)

        assert store.workspace_path.exists()
        # Verify file was written (we can't easily parse it here, but existence is enough)


def test_toml_store_read_integrates_env():
    """Test read_for_mode() applies INDEXED__* env overrides."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        store = TomlStore(workspace=workspace)

        env_vars = {"INDEXED__test__value": "from_env"}

        with patch.dict(os.environ, env_vars, clear=False):
            result = store.read_for_mode("global")

        assert result.get("test", {}).get("value") == "from_env"


def test_toml_store_read_disk_only_ignores_env(tmp_path: Path):
    """C2: read_disk_only_for_mode() must NOT merge INDEXED__* env vars —
    it's the baseline set()/delete() persist so env-supplied secrets never
    get baked into config.toml."""
    store = TomlStore(workspace=tmp_path, mode_override="local")
    store.write({"test": {"value": "on_disk"}})

    env_vars = {"INDEXED__test__value": "from_env", "INDEXED__test__other": "secret"}
    with patch.dict(os.environ, env_vars, clear=False):
        disk_only = store.read_disk_only_for_mode("local")
        merged = store.read_for_mode("local")

    assert disk_only["test"]["value"] == "on_disk"
    assert "other" not in disk_only["test"]
    # Sanity: the merged (env-overlaid) view DOES pick up the env value —
    # confirms disk_only is genuinely bypassing the overlay, not just broken.
    assert merged["test"]["value"] == "from_env"
    assert merged["test"]["other"] == "secret"
