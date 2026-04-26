"""Tests for ConfigService storage and workspace preferences.

Tests the workspace preference management and storage mode resolution.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch


from indexed_config import ConfigService


class TestConfigServiceInit:
    """Test ConfigService initialization with storage options."""

    def test_init_with_default_workspace(self):
        """ConfigService initializes with cwd as workspace."""
        ConfigService.reset()
        service = ConfigService()
        assert service.workspace == Path.cwd()

    def test_init_with_custom_workspace(self):
        """ConfigService accepts custom workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            ConfigService.reset()
            service = ConfigService(workspace=workspace)
            assert service.workspace == workspace

    def test_init_with_mode_override(self):
        """ConfigService accepts mode_override."""
        ConfigService.reset()
        service = ConfigService(mode_override="local")
        # Mode is stored internally and affects path resolution
        assert service._mode_override == "local"

    def test_singleton_pattern(self):
        """ConfigService.instance() returns singleton."""
        ConfigService.reset()
        service1 = ConfigService.instance()
        service2 = ConfigService.instance()
        assert service1 is service2

    def test_singleton_with_reset(self):
        """ConfigService.instance(reset=True) creates new instance."""
        ConfigService.reset()
        service1 = ConfigService.instance()
        service2 = ConfigService.instance(reset=True)
        assert service1 is not service2


class TestConfigServiceProperties:
    """Test ConfigService property accessors."""

    def test_store_property(self):
        """ConfigService exposes TomlStore."""
        ConfigService.reset()
        service = ConfigService()
        assert service.store is not None

    def test_resolver_property(self):
        """ConfigService exposes StorageResolver."""
        ConfigService.reset()
        service = ConfigService()
        assert service.resolver is not None


class TestWorkspacePreferences:
    """Test workspace preference management."""

    def test_get_workspace_preference_returns_none_when_not_set(self):
        """get_workspace_preference returns None when no preference exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Mock home to avoid writing to real global config
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)
                pref = service.get_workspace_preference()
                assert pref is None

    def test_get_workspace_config(self):
        """get_workspace_config returns workspace configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "project"
            workspace.mkdir()

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()

                service = ConfigService(workspace=workspace)
                service.workspace_manager.set_preference("local")

                # Get workspace config
                config = service.get_workspace_config()

                assert config["mode"] == "local"
                assert config["local_path"] == str(workspace)
                assert config["global_path"] == "~/.indexed"

    def test_get_workspace_config_returns_empty_when_not_set(self):
        """get_workspace_config returns empty dict when no config exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "project"
            workspace.mkdir()

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()

                service = ConfigService(workspace=workspace)
                config = service.get_workspace_config()

                assert config == {}


class TestStorageModeResolution:
    """Test storage mode resolution logic."""

    def test_resolve_storage_mode_defaults_to_global(self):
        """resolve_storage_mode returns 'global' by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)
                mode = service.resolve_storage_mode()
                assert mode == "global"

    def test_resolve_storage_mode_respects_mode_override(self):
        """resolve_storage_mode returns mode_override when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace, mode_override="local")
                mode = service.resolve_storage_mode()
                assert mode == "local"

    def test_resolve_storage_mode_respects_workspace_preference(self):
        """resolve_storage_mode returns workspace preference when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)
                service.workspace_manager.set_preference("local")

                mode = service.resolve_storage_mode()
                assert mode == "local"
