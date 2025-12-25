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

    def test_set_workspace_preference_local(self):
        """set_workspace_preference saves 'local' preference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "my_project"
            workspace.mkdir()

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)

                service.set_workspace_preference("local")

                # Read back the preference
                pref = service.get_workspace_preference()
                assert pref == "local"

    def test_set_workspace_preference_global(self):
        """set_workspace_preference saves 'global' preference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "my_project"
            workspace.mkdir()

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)

                service.set_workspace_preference("global")

                pref = service.get_workspace_preference()
                assert pref == "global"

    def test_clear_workspace_preference(self):
        """clear_workspace_preference removes the preference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "my_project"
            workspace.mkdir()

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)

                # Set then clear
                service.set_workspace_preference("local")
                assert service.get_workspace_preference() == "local"

                result = service.clear_workspace_preference()
                assert result is True
                assert service.get_workspace_preference() is None

    def test_clear_workspace_preference_returns_false_when_not_set(self):
        """clear_workspace_preference returns False when no preference exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "my_project"
            workspace.mkdir()

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)

                result = service.clear_workspace_preference()
                assert result is False

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
                service.set_workspace_preference("local")

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
                service.set_workspace_preference("local")

                mode = service.resolve_storage_mode()
                assert mode == "local"


class TestConflictDetection:
    """Test config conflict detection."""

    def test_has_config_conflict_false_when_no_local(self):
        """has_config_conflict returns False when no local config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "value"')

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)
                assert service.has_config_conflict() is False

    def test_has_config_conflict_true_when_different(self):
        """has_config_conflict returns True when configs differ."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create local config
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "local_value"')

            # Create global config with different value
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "global_value"')

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)
                assert service.has_config_conflict() is True


class TestPathAccessors:
    """Test path accessor methods."""

    def test_get_collections_path(self):
        """get_collections_path returns resolved collections path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)

                path = service.get_collections_path()
                # Default is global
                expected = global_home / ".indexed" / "data" / "collections"
                assert path == expected

    def test_get_caches_path(self):
        """get_caches_path returns resolved caches path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)

                path = service.get_caches_path()
                expected = global_home / ".indexed" / "data" / "caches"
                assert path == expected

    def test_ensure_storage_dirs_creates_directories(self):
        """ensure_storage_dirs creates the storage directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                ConfigService.reset()
                service = ConfigService(workspace=workspace)

                service.ensure_storage_dirs()

                # Check directories were created
                collections_path = global_home / ".indexed" / "data" / "collections"
                caches_path = global_home / ".indexed" / "data" / "caches"
                assert collections_path.exists()
                assert caches_path.exists()
