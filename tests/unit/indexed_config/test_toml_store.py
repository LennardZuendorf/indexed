"""Tests for the TomlStore module.

Tests the config file reading, writing, and conflict detection.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch


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
        assert store._global_root == expected

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
            assert store._local_root == expected


class TestTomlStoreEnvPaths:
    """Test TomlStore .env file path properties."""

    def test_env_path_defaults_to_global_when_no_local_config(self):
        """Default _env_path is the global .env when no local config exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace)
            expected = Path.home() / ".indexed" / ".env"
            assert store._env_path == expected

    def test_env_path_defaults_to_local_when_local_config_exists(self):
        """Default _env_path is the local .env when local config exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[existing]\nkey = "val"\n')
            store = TomlStore(workspace=workspace)
            expected = workspace / ".indexed" / ".env"
            assert store._env_path == expected

    def test_env_path_with_global_mode(self):
        """_env_path with global mode_override points to global .env."""
        store = TomlStore(mode_override="global")
        expected = Path.home() / ".indexed" / ".env"
        assert store._env_path == expected

    def test_env_path_with_local_mode(self):
        """_env_path with local mode_override points to local .env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace, mode_override="local")
            expected = workspace / ".indexed" / ".env"
            assert store._env_path == expected

    def test_global_env_path(self):
        """_global_env_path always returns global .env."""
        store = TomlStore()
        expected = Path.home() / ".indexed" / ".env"
        assert store._global_env_path == expected

    def test_local_env_path(self):
        """_local_env_path always returns local .env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace)
            expected = workspace / ".indexed" / ".env"
            assert store._local_env_path == expected


class TestTomlStoreRead:
    """Test TomlStore read functionality."""

    def test_read_empty_when_no_files(self):
        """read() returns empty dict when no local config files exist (local mode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            # Use mode_override="local" to avoid reading global config
            store = TomlStore(workspace=workspace, mode_override="local")
            result = store.read()
            # _schema_version is always injected by read()
            assert result == {"_schema_version": "1"}

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

    def test_write_defaults_to_global_when_no_local_config(self):
        """write() without mode_override writes to global when no local config exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_home = Path(tmpdir) / "home"
            fake_home.mkdir()
            workspace = Path(tmpdir) / "project"
            workspace.mkdir()
            with patch.object(Path, "home", return_value=fake_home):
                store = TomlStore(workspace=workspace)
                store.write({"test": {"key": "value"}})

                global_path = fake_home / ".indexed" / "config.toml"
                local_path = workspace / ".indexed" / "config.toml"
                assert global_path.exists()
                assert not local_path.exists()
                content = global_path.read_text()
                assert "key" in content
                assert "value" in content

    def test_write_defaults_to_local_when_local_config_exists(self):
        """write() without mode_override writes to local when local config already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[existing]\nkey = "val"\n')

            store = TomlStore(workspace=workspace)
            store.write({"test": {"key": "value"}})

            local_path = workspace / ".indexed" / "config.toml"
            assert local_path.exists()
            content = local_path.read_text()
            assert "key" in content

    def test_write_to_global(self):
        """write() with to_global=True writes to global config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock home directory
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                store = TomlStore()
                store.write({"test": {"key": "global_value"}}, to_global=True)

                global_path = Path(tmpdir) / ".indexed" / "config.toml"
                assert global_path.exists()

    def test_write_with_global_mode_override(self):
        """write() with mode_override='global' writes to global config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
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
            fake_home = Path(tmpdir) / "home"
            fake_home.mkdir()
            workspace = Path(tmpdir) / "project"
            workspace.mkdir()
            # Create only local config (no global config in fake_home)
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "value"')

            with patch.object(Path, "home", return_value=fake_home):
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

            with patch.object(Path, "home", return_value=global_home):
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

            with patch.object(Path, "home", return_value=global_home):
                store = TomlStore(workspace=workspace)
                assert store.configs_differ() is False

    def test_get_config_differences_returns_diff_dict(self):
        """get_config_differences returns dict of differing values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create local config
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text(
                '[test]\nkey = "local_value"\nother = "same"'
            )

            # Mock home for global config
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text(
                '[test]\nkey = "global_value"\nother = "same"'
            )

            with patch.object(Path, "home", return_value=global_home):
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

            with patch.object(Path, "home", return_value=global_home):
                store = TomlStore(workspace=workspace)
                differences = store.get_config_differences()
                assert differences == {}


class TestReadForMode:
    """Test TomlStore.read_for_mode()."""

    def test_read_for_mode_global_reads_only_global(self):
        """read_for_mode('global') reads only global config, not local."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            global_home = Path(tmpdir) / "home"

            # Create both configs with different values
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "local_value"')

            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "global_value"')

            with patch.object(Path, "home", return_value=global_home):
                store = TomlStore(workspace=workspace)
                result = store.read_for_mode("global")
                assert result["test"]["key"] == "global_value"

    def test_read_for_mode_local_reads_only_local(self):
        """read_for_mode('local') reads only local config, not global."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            global_home = Path(tmpdir) / "home"

            # Create both configs with different values
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "local_value"')

            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "global_value"')

            with patch.object(Path, "home", return_value=global_home):
                store = TomlStore(workspace=workspace)
                result = store.read_for_mode("local")
                assert result["test"]["key"] == "local_value"

    def test_read_for_mode_loads_cwd_dotenv(self):
        """read_for_mode() loads CWD/.env to fill gaps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("[test]")

            # Create CWD/.env with a value
            (workspace / ".env").write_text("MY_CWD_VAR=from_cwd\n")

            with patch.object(Path, "home", return_value=global_home):
                store = TomlStore(workspace=workspace)
                store.read_for_mode("global")
                assert os.environ.get("MY_CWD_VAR") == "from_cwd"

            # Cleanup
            os.environ.pop("MY_CWD_VAR", None)

    def test_read_for_mode_indexed_env_overrides_cwd_env(self):
        """.indexed/.env values take priority over CWD/.env values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("[test]")

            # .indexed/.env sets a value
            (global_dir / ".env").write_text("SHARED_VAR=from_indexed\n")
            # CWD/.env sets the same value differently
            (workspace / ".env").write_text("SHARED_VAR=from_cwd\n")

            # Remove from env to ensure clean test
            os.environ.pop("SHARED_VAR", None)

            with patch.object(Path, "home", return_value=global_home):
                store = TomlStore(workspace=workspace)
                store.read_for_mode("global")
                # .indexed/.env is loaded first, so its value wins
                assert os.environ.get("SHARED_VAR") == "from_indexed"

            # Cleanup
            os.environ.pop("SHARED_VAR", None)

    def test_read_for_mode_real_env_overrides_both_dotenvs(self):
        """Real env vars already set override both .env files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("[test]")

            (global_dir / ".env").write_text("REAL_ENV_TEST=from_indexed\n")
            (workspace / ".env").write_text("REAL_ENV_TEST=from_cwd\n")

            # Set real env var before loading
            os.environ["REAL_ENV_TEST"] = "from_real_env"

            with patch.object(Path, "home", return_value=global_home):
                store = TomlStore(workspace=workspace)
                store.read_for_mode("global")
                # Real env var wins (override=False in load_dotenv)
                assert os.environ["REAL_ENV_TEST"] == "from_real_env"

            # Cleanup
            os.environ.pop("REAL_ENV_TEST", None)

    def test_read_for_mode_includes_schema_version(self):
        """read_for_mode() injects _schema_version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace, mode_override="local")
            result = store.read_for_mode("local")
            assert "_schema_version" in result

    def test_read_for_mode_env_vars_override_toml(self):
        """INDEXED__* env vars override TOML values in read_for_mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "toml_value"')

            os.environ["INDEXED__test__key"] = "env_value"
            try:
                store = TomlStore(workspace=workspace)
                result = store.read_for_mode("local")
                assert result["test"]["key"] == "env_value"
            finally:
                del os.environ["INDEXED__test__key"]


class TestGetResolvedEnvPath:
    """Test TomlStore.get_resolved_env_path()."""

    def test_global_mode_returns_global_env_path(self):
        """get_resolved_env_path('global') returns global .env path."""
        store = TomlStore()
        result = store.get_resolved_env_path("global")
        expected = str(Path.home() / ".indexed" / ".env")
        assert result == expected

    def test_local_mode_returns_local_env_path(self):
        """get_resolved_env_path('local') returns local .env path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            store = TomlStore(workspace=workspace)
            result = store.get_resolved_env_path("local")
            expected = str(workspace / ".indexed" / ".env")
            assert result == expected
