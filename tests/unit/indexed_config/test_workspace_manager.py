"""Additional WorkspaceManager coverage."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from indexed.config.storage import StorageResolver
from indexed.config.store import TomlStore
from indexed.config.workspace import WorkspaceManager


@pytest.fixture
def workspace_manager(tmp_path: Path) -> WorkspaceManager:
    store = TomlStore(workspace=tmp_path)
    resolver = StorageResolver(workspace=tmp_path)
    return WorkspaceManager(store, resolver, tmp_path)


def test_clear_preference_returns_false_when_missing(
    workspace_manager: WorkspaceManager,
) -> None:
    with patch.object(TomlStore, "read_for_mode", return_value={}):
        assert workspace_manager.clear_preference() is False


def test_clear_preference_deletes_section(workspace_manager: WorkspaceManager) -> None:
    with (
        patch.object(
            TomlStore, "read_for_mode", return_value={"workspace": {"mode": "local"}}
        ),
        patch.object(TomlStore, "write") as mock_write,
    ):
        assert workspace_manager.clear_preference() is True
        written = mock_write.call_args[0][0]
        assert "workspace" not in written


def test_get_config_returns_empty_for_invalid_mode(
    workspace_manager: WorkspaceManager,
) -> None:
    workspace_manager._store.read_for_mode = MagicMock(  # type: ignore[method-assign]
        return_value={"workspace": {"mode": "invalid"}}
    )
    assert workspace_manager.get_config() == {}


def test_resolve_storage_mode_auto_detects_local(tmp_path: Path) -> None:
    (tmp_path / ".indexed").mkdir()
    (tmp_path / ".indexed" / "config.toml").write_text("", encoding="utf-8")
    store = TomlStore(workspace=tmp_path)
    resolver = StorageResolver(workspace=tmp_path)
    mgr = WorkspaceManager(store, resolver, tmp_path)
    with patch.object(mgr, "get_preference", return_value=None):
        assert mgr.resolve_storage_mode() == "local"


def test_has_conflict_and_differences_delegate_to_store(
    workspace_manager: WorkspaceManager,
) -> None:
    workspace_manager._store.configs_differ = MagicMock(return_value=True)  # type: ignore[method-assign]
    workspace_manager._store.get_config_differences = MagicMock(
        return_value={"k": (1, 2)}
    )  # type: ignore[method-assign]
    assert workspace_manager.has_conflict() is True
    assert workspace_manager.get_differences() == {"k": (1, 2)}


def test_set_preference_persists_custom_global_path(
    workspace_manager: WorkspaceManager,
) -> None:
    with (
        patch.object(TomlStore, "read_for_mode", return_value={}),
        patch.object(TomlStore, "write") as mock_write,
    ):
        workspace_manager.set_preference("local", global_path="/custom/global")

    written = mock_write.call_args[0][0]
    assert written["workspace"]["global_path"] == "/custom/global"


def test_get_collections_and_caches_paths(workspace_manager: WorkspaceManager) -> None:
    workspace_manager._resolver.get_collections_path = MagicMock(
        return_value=Path("/c")
    )  # type: ignore[method-assign]
    workspace_manager._resolver.get_caches_path = MagicMock(return_value=Path("/k"))  # type: ignore[method-assign]
    with patch.object(workspace_manager, "resolve_storage_mode", return_value="local"):
        assert workspace_manager.get_collections_path() == Path("/c")
        assert workspace_manager.get_caches_path() == Path("/k")
    workspace_manager._resolver.ensure_dirs = MagicMock()  # type: ignore[method-assign]
    with patch.object(workspace_manager, "get_preference", return_value="local"):
        workspace_manager.ensure_storage_dirs()
    workspace_manager._resolver.ensure_dirs.assert_called_once_with("local")
