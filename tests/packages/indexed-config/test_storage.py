"""Tests for the storage module.

Tests the centralized path resolution for indexed's storage locations.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch


from indexed_config.storage import (
    StorageResolver,
    get_global_root,
    get_local_root,
    get_config_path,
    get_env_path,
    get_data_root,
    get_collections_path,
    get_caches_path,
    has_local_storage,
    has_local_config,
    ensure_storage_dirs,
    get_resolver,
    reset_resolver,
)


class TestPathFunctions:
    """Test the basic path resolution functions."""

    def test_get_global_root_returns_home_indexed(self):
        """Global root should be ~/.indexed."""
        result = get_global_root()
        expected = Path.home() / ".indexed"
        assert result == expected

    def test_get_local_root_returns_cwd_indexed(self):
        """Local root should be ./.indexed relative to cwd."""
        result = get_local_root()
        expected = Path.cwd() / ".indexed"
        assert result == expected

    def test_get_local_root_with_custom_workspace(self):
        """Local root can use a custom workspace path."""
        custom_path = Path("/custom/workspace")
        result = get_local_root(workspace=custom_path)
        expected = custom_path / ".indexed"
        assert result == expected

    def test_get_config_path(self):
        """Config path should be root/config.toml."""
        root = Path("/test/root")
        result = get_config_path(root)
        assert result == root / "config.toml"

    def test_get_env_path(self):
        """Env path should be root/.env."""
        root = Path("/test/root")
        result = get_env_path(root)
        assert result == root / ".env"

    def test_get_data_root(self):
        """Data root should be root/data."""
        root = Path("/test/root")
        result = get_data_root(root)
        assert result == root / "data"

    def test_get_collections_path(self):
        """Collections path should be root/data/collections."""
        root = Path("/test/root")
        result = get_collections_path(root)
        assert result == root / "data" / "collections"

    def test_get_caches_path(self):
        """Caches path should be root/data/caches."""
        root = Path("/test/root")
        result = get_caches_path(root)
        assert result == root / "data" / "caches"


class TestStorageExistence:
    """Test storage existence detection functions."""

    def test_has_local_storage_false_when_not_exists(self):
        """has_local_storage returns False when .indexed doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = has_local_storage(workspace=Path(tmpdir))
            assert result is False

    def test_has_local_storage_true_when_exists(self):
        """has_local_storage returns True when .indexed exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            indexed_dir = Path(tmpdir) / ".indexed"
            indexed_dir.mkdir()
            result = has_local_storage(workspace=Path(tmpdir))
            assert result is True

    def test_has_local_config_false_when_not_exists(self):
        """has_local_config returns False when config.toml doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = has_local_config(workspace=Path(tmpdir))
            assert result is False

    def test_has_local_config_true_when_exists(self):
        """has_local_config returns True when config.toml exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            indexed_dir = Path(tmpdir) / ".indexed"
            indexed_dir.mkdir()
            config_file = indexed_dir / "config.toml"
            config_file.write_text("[test]\nkey = 'value'")
            result = has_local_config(workspace=Path(tmpdir))
            assert result is True


class TestEnsureStorageDirs:
    """Test directory creation."""

    def test_ensure_storage_dirs_creates_all_directories(self):
        """ensure_storage_dirs creates root, data, collections, and caches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "test_root"
            assert not root.exists()

            ensure_storage_dirs(root)

            assert root.exists()
            assert (root / "data").exists()
            assert (root / "data" / "collections").exists()
            assert (root / "data" / "caches").exists()

    def test_ensure_storage_dirs_idempotent(self):
        """ensure_storage_dirs can be called multiple times safely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "test_root"

            # Call twice - should not raise
            ensure_storage_dirs(root)
            ensure_storage_dirs(root)

            assert root.exists()


class TestStorageResolver:
    """Test the StorageResolver class."""

    def test_resolver_global_root(self):
        """Resolver exposes global root."""
        resolver = StorageResolver()
        assert resolver.global_root == Path.home() / ".indexed"

    def test_resolver_local_root(self):
        """Resolver exposes local root based on workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            resolver = StorageResolver(workspace=workspace)
            assert resolver.local_root == workspace / ".indexed"

    def test_resolver_workspace(self):
        """Resolver exposes workspace path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            resolver = StorageResolver(workspace=workspace)
            assert resolver.workspace == workspace

    def test_resolve_root_defaults_to_global(self):
        """resolve_root defaults to global when no override or preference."""
        resolver = StorageResolver()
        result = resolver.resolve_root()
        assert result == resolver.global_root

    def test_resolve_root_with_local_override(self):
        """resolve_root returns local when mode_override is 'local'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            resolver = StorageResolver(workspace=workspace, mode_override="local")
            result = resolver.resolve_root()
            assert result == resolver.local_root

    def test_resolve_root_with_global_override(self):
        """resolve_root returns global when mode_override is 'global'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            resolver = StorageResolver(workspace=workspace, mode_override="global")
            result = resolver.resolve_root()
            assert result == resolver.global_root

    def test_resolve_root_with_workspace_preference(self):
        """resolve_root respects workspace preference when no override."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            resolver = StorageResolver(workspace=workspace)
            result = resolver.resolve_root(workspace_preference="local")
            assert result == resolver.local_root

    def test_mode_override_takes_precedence_over_preference(self):
        """Mode override beats workspace preference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            resolver = StorageResolver(workspace=workspace, mode_override="global")
            # Even with local preference, override wins
            result = resolver.resolve_root(workspace_preference="local")
            assert result == resolver.global_root

    def test_get_collections_path_resolved(self):
        """get_collections_path uses resolved root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            resolver = StorageResolver(workspace=workspace, mode_override="local")
            result = resolver.get_collections_path()
            expected = workspace / ".indexed" / "data" / "collections"
            assert result == expected

    def test_get_caches_path_resolved(self):
        """get_caches_path uses resolved root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            resolver = StorageResolver(workspace=workspace, mode_override="local")
            result = resolver.get_caches_path()
            expected = workspace / ".indexed" / "data" / "caches"
            assert result == expected

    def test_has_conflict_false_when_only_global(self):
        """has_conflict returns False when only global config exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            resolver = StorageResolver(workspace=workspace)
            # No local config created
            assert resolver.has_conflict() is False

    def test_has_conflict_false_when_only_local(self):
        """has_conflict returns False when only local config exists (no global)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            # Create local config
            local_dir = workspace / ".indexed"
            local_dir.mkdir()
            (local_dir / "config.toml").write_text("[test]\nkey = 'value'")

            resolver = StorageResolver(workspace=workspace)
            # Mock has_global_config to isolate the test from real global config
            with patch("indexed_config.storage.has_global_config", return_value=False):
                assert resolver.has_conflict() is False


class TestResolverSingleton:
    """Test the module-level resolver singleton."""

    def test_get_resolver_creates_singleton(self):
        """get_resolver returns a StorageResolver instance."""
        reset_resolver()
        resolver = get_resolver()
        assert isinstance(resolver, StorageResolver)

    def test_get_resolver_returns_same_instance(self):
        """get_resolver returns same instance on subsequent calls."""
        reset_resolver()
        resolver1 = get_resolver()
        resolver2 = get_resolver()
        assert resolver1 is resolver2

    def test_get_resolver_with_reset(self):
        """get_resolver with reset=True creates new instance."""
        reset_resolver()
        resolver1 = get_resolver()
        resolver2 = get_resolver(reset=True)
        assert resolver1 is not resolver2

    def test_reset_resolver_clears_singleton(self):
        """reset_resolver clears the singleton."""
        reset_resolver()
        resolver1 = get_resolver()
        reset_resolver()
        resolver2 = get_resolver()
        assert resolver1 is not resolver2
