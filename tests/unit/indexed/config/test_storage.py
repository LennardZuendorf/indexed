"""Storage path helpers — one global root (workspace-profile/1, R1).

The local/global axis is gone: no ``StorageMode``, no ``StorageResolver``, no
``get_local_root``, no ``.gitignore`` guard. What survives is plain path
arithmetic over the single root at ``~/.indexed``.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import indexed.config as config_pkg
from indexed.config.storage import (
    ensure_storage_dirs,
    get_caches_path,
    get_collections_path,
    get_config_path,
    get_data_root,
    get_env_path,
    get_global_caches_path,
    get_global_collections_path,
    get_global_root,
    has_global_config,
)


class TestPathFunctions:
    """Test the basic path resolution functions."""

    def test_get_global_root_returns_home_indexed(self):
        """Global root should be ~/.indexed."""
        assert get_global_root() == Path.home() / ".indexed"

    def test_get_config_path(self):
        """Config path should be root/config.toml."""
        root = Path("/test/root")
        assert get_config_path(root) == root / "config.toml"

    def test_get_env_path(self):
        """Env path should be root/.env."""
        root = Path("/test/root")
        assert get_env_path(root) == root / ".env"

    def test_get_data_root(self):
        """Data root should be root/data."""
        root = Path("/test/root")
        assert get_data_root(root) == root / "data"

    def test_get_collections_path(self):
        """Collections path should be root/data/collections."""
        root = Path("/test/root")
        assert get_collections_path(root) == root / "data" / "collections"

    def test_get_caches_path(self):
        """Caches path should be root/data/caches."""
        root = Path("/test/root")
        assert get_caches_path(root) == root / "data" / "caches"

    def test_global_collections_and_caches_anchor_to_home(self, tmp_path: Path):
        """workspace-profile/1 R1: collections always live under ~/.indexed/data."""
        with patch.object(Path, "home", return_value=tmp_path):
            assert (
                get_global_collections_path()
                == tmp_path / ".indexed" / "data" / "collections"
            )
            assert get_global_caches_path() == tmp_path / ".indexed" / "data" / "caches"


class TestStorageExistence:
    """Test the global-config existence check."""

    def test_has_global_config_false_when_not_exists(self, tmp_path: Path):
        with patch.object(Path, "home", return_value=tmp_path):
            assert has_global_config() is False

    def test_has_global_config_true_when_exists(self, tmp_path: Path):
        (tmp_path / ".indexed").mkdir()
        (tmp_path / ".indexed" / "config.toml").write_text("")
        with patch.object(Path, "home", return_value=tmp_path):
            assert has_global_config() is True


class TestEnsureStorageDirs:
    """Test directory creation."""

    def test_ensure_storage_dirs_creates_all_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "storage"
            ensure_storage_dirs(root)

            assert root.exists()
            assert (root / "data").exists()
            assert (root / "data" / "collections").exists()
            assert (root / "data" / "caches").exists()

    def test_ensure_storage_dirs_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "storage"
            ensure_storage_dirs(root)
            ensure_storage_dirs(root)

            assert (root / "data" / "collections").exists()

    def test_ensure_storage_dirs_writes_no_gitignore(self):
        """workspace-profile/1 R1: the .env/.gitignore guard is gone with local storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "storage"
            ensure_storage_dirs(root)

            assert not (root / ".gitignore").exists()


@pytest.mark.parametrize(
    "symbol",
    [
        "StorageMode",
        "StorageResolver",
        "get_local_root",
        "has_local_storage",
        "has_local_config",
        "resolve_storage_mode",
        "_ensure_gitignore",
        "StorageConflictError",
    ],
)
def test_storage_mode_symbols_are_gone(symbol: str):
    """workspace-profile/1 R1: no local-vs-global choice remains importable."""
    import indexed.config.storage as storage_mod

    assert not hasattr(storage_mod, symbol)
    assert not hasattr(config_pkg, symbol)
