"""Tests for the TomlStore module.

Tests the config file reading, writing, and conflict detection.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from indexed_config.store import TomlStore


class TestTomlStorePaths:
    """Test TomlStore path properties."""

    def test_global_path_is_home_indexed(self):
        """Global path should be ~/.indexed/config.toml."""
        store = TomlStore()
        expected = Path.home() / ".indexed" / "config.toml"
        assert store.global_path == expected

    def test_global_root_is_home_indexed(self):
        """Global root should be ~/.indexed."""
        store = TomlStore()
        expected = Path.home() / ".indexed"
        assert store.global_root == expected

    def test_workspace_path_is_cwd_indexed(self):
        """Workspace path should be ./.indexed/config.toml."""
        store = TomlStore()
        expected = Path.cwd() / ".indexed" / "config.toml"
        assert store.workspace_path == expected

    def test_workspace_path_with_custom_workspace(self):
        """Workspace path respects custom workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace)
            expected = workspace / ".indexed" / "config.toml"
            assert store.workspace_path == expected

    def test_local_root(self):
        """Local root should be workspace/.indexed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace)
            expected = workspace / ".indexed"
            assert store.local_root == expected


class TestTomlStoreEnvPaths:
    """Test TomlStore .env file path properties."""

    def test_env_path_defaults_to_local(self):
        """Default env_path is the local .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace)
            expected = workspace / ".indexed" / ".env"
            assert store.env_path == expected

    def test_env_path_with_global_mode(self):
        """env_path with global mode_override points to global .env."""
        store = TomlStore(mode_override="global")
        expected = Path.home() / ".indexed" / ".env"
        assert store.env_path == expected

    def test_env_path_with_local_mode(self):
        """env_path with local mode_override points to local .env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace, mode_override="local")
            expected = workspace / ".indexed" / ".env"
            assert store.env_path == expected

    def test_global_env_path(self):
        """global_env_path always returns global .env."""
        store = TomlStore()
        expected = Path.home() / ".indexed" / ".env"
        assert store.global_env_path == expected

    def test_local_env_path(self):
        """local_env_path always returns local .env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace)
            expected = workspace / ".indexed" / ".env"
            assert store.local_env_path == expected


class TestTomlStoreRead:
    """Test TomlStore read functionality."""

    def test_read_empty_when_no_files(self):
        """read() returns empty dict when no local config files exist (local mode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            # Use mode_override="local" to avoid reading global config
            store = TomlStore(workspace=workspace, mode_override="local")
            result = store.read()
            assert result == {}

    def test_read_local_only(self):
        """read() returns local config when only local exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            # Create local config
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "local_value"')
            
            store = TomlStore(workspace=workspace)
            result = store.read()
            assert result.get("test", {}).get("key") == "local_value"

    def test_read_with_mode_override_local(self):
        """read() with mode_override='local' only reads local config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            # Create local config
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "local_value"')
            
            store = TomlStore(workspace=workspace, mode_override="local")
            result = store.read()
            assert result.get("test", {}).get("key") == "local_value"


class TestTomlStoreWrite:
    """Test TomlStore write functionality."""

    def test_write_creates_workspace_config(self):
        """write() creates config in workspace by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace)
            
            store.write({"test": {"key": "value"}})
            
            config_path = workspace / ".indexed" / "config.toml"
            assert config_path.exists()
            content = config_path.read_text()
            assert "key" in content
            assert "value" in content

    def test_write_to_global(self):
        """write() with to_global=True writes to global config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock home directory
            with patch.object(Path, 'home', return_value=Path(tmpdir)):
                store = TomlStore()
                store.write({"test": {"key": "global_value"}}, to_global=True)
                
                global_path = Path(tmpdir) / ".indexed" / "config.toml"
                assert global_path.exists()

    def test_write_with_global_mode_override(self):
        """write() with mode_override='global' writes to global config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, 'home', return_value=Path(tmpdir)):
                store = TomlStore(mode_override="global")
                store.write({"test": {"key": "value"}})
                
                global_path = Path(tmpdir) / ".indexed" / "config.toml"
                assert global_path.exists()


class TestTomlStoreConflictDetection:
    """Test TomlStore conflict detection methods."""

    def test_has_local_config_false_when_not_exists(self):
        """has_local_config returns False when config doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace)
            assert store.has_local_config() is False

    def test_has_local_config_true_when_exists(self):
        """has_local_config returns True when config exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "value"')
            
            store = TomlStore(workspace=workspace)
            assert store.has_local_config() is True

    def test_configs_differ_false_when_only_one_exists(self):
        """configs_differ returns False when only one config exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            # Create only local config
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "value"')
            
            store = TomlStore(workspace=workspace)
            assert store.configs_differ() is False

    def test_configs_differ_true_when_different(self):
        """configs_differ returns True when configs have different values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create local config
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "local_value"')
            
            # Mock home for global config
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "global_value"')
            
            with patch.object(Path, 'home', return_value=global_home):
                store = TomlStore(workspace=workspace)
                assert store.configs_differ() is True

    def test_configs_differ_false_when_identical(self):
        """configs_differ returns False when configs are identical."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create local config
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "same_value"')
            
            # Mock home for global config with same content
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "same_value"')
            
            with patch.object(Path, 'home', return_value=global_home):
                store = TomlStore(workspace=workspace)
                assert store.configs_differ() is False

    def test_get_config_differences_returns_diff_dict(self):
        """get_config_differences returns dict of differing values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create local config
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "local_value"\nother = "same"')
            
            # Mock home for global config
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "global_value"\nother = "same"')
            
            with patch.object(Path, 'home', return_value=global_home):
                store = TomlStore(workspace=workspace)
                differences = store.get_config_differences()
                
                # Should only contain the differing key
                assert "test.key" in differences
                assert differences["test.key"] == ("local_value", "global_value")
                # "other" should not be in differences since it's the same
                assert "test.other" not in differences

    def test_get_config_differences_empty_when_no_differences(self):
        """get_config_differences returns empty dict when configs match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create identical configs
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "same"')
            
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "same"')
            
            with patch.object(Path, 'home', return_value=global_home):
                store = TomlStore(workspace=workspace)
                differences = store.get_config_differences()
                assert differences == {}

