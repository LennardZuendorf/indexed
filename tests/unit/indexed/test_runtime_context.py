"""Tests for unified CLI/MCP runtime context resolution."""

from indexed_config import ConfigService, get_global_root, get_local_root
from indexed.runtime import CliContext, resolve_collections_context


def test_resolve_collections_context_global_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    ctx = resolve_collections_context(mode_override=None, workspace=tmp_path)

    assert isinstance(ctx, CliContext)
    assert ctx.mode == "global"
    expected = get_global_root() / "data" / "collections"
    assert ctx.collections_path == expected
    assert ctx.caches_path == get_global_root() / "data" / "caches"
    assert ctx.connector_registry
    assert ctx.config_service is ConfigService.instance()


def test_resolve_collections_context_local_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    local_root = get_local_root(tmp_path)
    (local_root / "data" / "collections").mkdir(parents=True)

    ctx = resolve_collections_context(mode_override="local", workspace=tmp_path)

    assert ctx.mode == "local"
    assert ctx.collections_path == local_root / "data" / "collections"
    assert ctx.caches_path == local_root / "data" / "caches"


def test_local_override_resets_singleton(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    global_ctx = resolve_collections_context(workspace=tmp_path)
    local_ctx = resolve_collections_context(mode_override="local", workspace=tmp_path)

    assert global_ctx.collections_path != local_ctx.collections_path
    assert local_ctx.mode == "local"
