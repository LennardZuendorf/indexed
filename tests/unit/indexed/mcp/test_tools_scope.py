"""Search and status apply the request's scope (#345).

Tool-level: the engine is faked, the store is real. What is asserted is which
collections reach the engine and what a scoped / unscoped request returns —
search and status must never disagree about scope.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
from typing import Any, Optional, Sequence

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

import indexed.mcp.resources as resources_module
import indexed.mcp.tools as tools_module
from indexed.mcp.server import mcp

pytestmark = pytest.mark.unit


# --- harness -----------------------------------------------------------------


class _Root:
    def __init__(self, uri: str) -> None:
        self.uri = uri


class _FakeContext:
    def __init__(self, roots: Sequence[_Root] = (), *, unsupported: bool = False):
        self._roots = list(roots)
        self._unsupported = unsupported
        # Attributes FastMCP's dependency wrapper touches on the current context.
        self.is_background_task = False
        self._request_state = {}

    async def list_roots(self):
        if self._unsupported:
            raise McpError(ErrorData(code=0, message="List roots not supported"))
        return self._roots


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


def _store(home: Path, *names: str) -> Path:
    collections = home / ".indexed" / "data" / "collections"
    for name in names:
        (collections / name).mkdir(parents=True, exist_ok=True)
        (collections / name / "manifest.json").write_text("{}", encoding="utf-8")
    return collections


def _repo(tmp_path: Path, *names: str) -> Path:
    repo = tmp_path / "repos" / "alpha"
    repo.mkdir(parents=True, exist_ok=True)
    entries = ", ".join(f'"{name}"' for name in names)
    (repo / "indexed.toml").write_text(
        f"version = 1\n\n[collections]\nuse = [{entries}]\n", encoding="utf-8"
    )
    return repo


def _ctx(*roots: Path) -> _FakeContext:
    return _FakeContext([_Root(uri=root.resolve().as_uri()) for root in roots])


def _status(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        number_of_documents=1,
        number_of_chunks=1,
        updated_time="2026-11-26T09:00:00+00:00",
        last_modified_document_time="2026-11-26T09:00:00+00:00",
        indexers=["indexer_FAISS"],
        index_size=1,
        source_type="localFiles",
        relative_path=f"{name}/src",
        disk_size_bytes=10,
        freshness=None,
    )


def _tool(name: str) -> Any:
    return asyncio.run(mcp.get_tool(name))


def _resource(uri: str) -> Any:
    return asyncio.run(mcp.get_resource(uri))


def _template(uri: str) -> Any:
    return asyncio.run(mcp.get_resource_template(uri))


@contextmanager
def _bound(ctx: Any):
    """Run a resource read on ``ctx``, the way FastMCP's server does."""
    from fastmcp.server.context import _current_context

    token = _current_context.set(ctx)
    try:
        yield
    finally:
        _current_context.reset(token)


def _read(uri: str, ctx: Any, **params: Any) -> Any:
    """Call a resource's own function with ``ctx`` as the current FastMCP context."""
    resource = _resource(uri) if not params else _template(uri)
    with _bound(ctx):
        return asyncio.run(resource.fn(**params))


def _call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    result = fn(*args, **kwargs)
    return asyncio.run(result) if asyncio.iscoroutine(result) else result


class _Statuses:
    """``svc_status`` stand-in over a fixed name set."""

    def __init__(self, *names: str) -> None:
        self.names = names

    def __call__(self, *args: Any, **kwargs: Any) -> list[Any]:
        requested = args[0] if args else None
        if requested:
            wanted = {n for n in requested if n in self.names}
            return [_status(n) for n in self.names if n in wanted]
        return [_status(n) for n in self.names]


def test_an_unresolvable_definition_entry_is_an_envelope(
    home: Path, tmp_path: Path
) -> None:
    """The definition names a collection the store no longer serves (#345).

    ``load_selection`` raises ``WorkspaceSelectionError``; the tool boundary must
    turn that into the documented envelope, never a protocol error an agent
    cannot read.
    """
    _store(home, "beta-docs")
    repo = _repo(tmp_path, "alpha-docs")

    result = _call(_tool("search").fn, "query", ctx=_ctx(repo))

    assert result["type"] == "WorkspaceSelectionError"
    assert "alpha-docs" in result["error"]
    assert "documents" not in result


# --- search ------------------------------------------------------------------


def test_search_without_scope_returns_the_documented_error_envelope(
    home: Path, tmp_path: Path
) -> None:
    _store(home, "alpha-docs")
    result = _call(_tool("search").fn, "query", ctx=_FakeContext())

    assert result["type"] == "NoRequestScopeError"
    assert "documents" not in result


def test_search_sends_only_the_selected_collections_to_the_engine(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store(home, "alpha-docs", "beta-docs")
    repo = _repo(tmp_path, "alpha-docs")
    monkeypatch.setattr(
        tools_module, "svc_status", _Statuses("alpha-docs", "beta-docs")
    )

    seen: dict[str, Any] = {}

    def fake_search(query: str, configs: Optional[list[Any]] = None, **kwargs: Any):
        seen["configs"] = configs
        return {}

    monkeypatch.setattr(tools_module, "svc_search", fake_search)

    result = _call(_tool("search").fn, "query", ctx=_ctx(repo))

    assert [config.name for config in seen["configs"]] == ["alpha-docs"]
    assert "type" not in result


def test_search_fails_closed_when_a_selected_collection_is_unusable(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store(home, "alpha-docs")
    repo = _repo(tmp_path, "alpha-docs")
    # The collection is registered but the manifest is unreadable now: status
    # omits it, so the search must report, never quietly search fewer.
    monkeypatch.setattr(tools_module, "svc_status", _Statuses("beta-docs"))
    monkeypatch.setattr(tools_module, "svc_search", lambda *a, **k: {})
    monkeypatch.setattr(
        "indexed.mcp.collection_errors.svc_collection_exists", lambda *a, **k: True
    )

    result = _call(_tool("search").fn, "query", ctx=_ctx(repo))

    assert "error" in result
    assert "alpha-docs" in result["error"]


def test_search_collection_outside_the_scope_is_an_error(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store(home, "alpha-docs", "beta-docs")
    repo = _repo(tmp_path, "alpha-docs")
    monkeypatch.setattr(
        tools_module, "svc_status", _Statuses("alpha-docs", "beta-docs")
    )
    monkeypatch.setattr(
        tools_module, "svc_search", lambda *a, **k: pytest.fail("engine was called")
    )

    result = _call(_tool("search_collection").fn, "beta-docs", "query", ctx=_ctx(repo))

    assert result["type"] == "CollectionOutsideScopeError"
    assert "alpha-docs" in result["error"]


def test_search_collection_inside_the_scope_runs(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store(home, "alpha-docs")
    repo = _repo(tmp_path, "alpha-docs")
    monkeypatch.setattr(tools_module, "svc_status", _Statuses("alpha-docs"))
    seen: dict[str, Any] = {}

    def fake_search(query: str, configs: Optional[list[Any]] = None, **kwargs: Any):
        seen["configs"] = configs
        return {}

    monkeypatch.setattr(tools_module, "svc_search", fake_search)

    result = _call(_tool("search_collection").fn, "alpha-docs", "query", ctx=_ctx(repo))

    assert [config.name for config in seen["configs"]] == ["alpha-docs"]
    assert "type" not in result


# --- status resources --------------------------------------------------------


def test_collections_resource_lists_only_the_selection(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store(home, "alpha-docs", "beta-docs")
    repo = _repo(tmp_path, "alpha-docs")
    monkeypatch.setattr(
        resources_module, "svc_status", _Statuses("alpha-docs", "beta-docs")
    )

    result = _read("resource://collections", _ctx(repo))

    assert result == {"collections": ["alpha-docs"]}


def test_status_resource_agrees_with_search_in_definition_order(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store(home, "a-docs", "b-docs", "c-docs")
    repo = _repo(tmp_path, "b-docs", "a-docs")
    monkeypatch.setattr(
        resources_module, "svc_status", _Statuses("a-docs", "b-docs", "c-docs")
    )

    result = _read("resource://collections/status", _ctx(repo))

    assert [entry["name"] for entry in result["collections"]] == ["b-docs", "a-docs"]


def test_status_resource_without_scope_is_the_named_error(
    home: Path, tmp_path: Path
) -> None:
    _store(home, "alpha-docs")

    result = _read("resource://collections/status", _FakeContext())

    assert result["type"] == "NoRequestScopeError"
    assert "collections" not in result


def test_collection_resource_refuses_a_collection_outside_the_scope(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store(home, "alpha-docs", "beta-docs")
    repo = _repo(tmp_path, "alpha-docs")
    monkeypatch.setattr(
        resources_module, "svc_status", _Statuses("alpha-docs", "beta-docs")
    )

    result = _read("resource://collection/{name}", _ctx(repo), name="beta-docs")

    assert result["type"] == "CollectionOutsideScopeError"
