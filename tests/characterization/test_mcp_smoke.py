"""Characterization: MCP resource smoke tests.

The server resolves its scope per request (#345): it reads the client's MCP
roots, finds the nearest committed ``indexed.toml`` at or above one of them, and
serves exactly that definition's ``[collections].use`` selection from the GLOBAL
store under ``~/.indexed``. The server's own working directory is not scope, so
every fixture here builds an isolated ``$HOME`` with a global store and a
repository carrying a definition, then presents that repository as the client's
root.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Sequence

import pytest

from indexed.mcp.server import mcp

COLLECTION_NAME = "mcp-smoke-collection"

#: ``~/.indexed/data/collections`` — the one store a definition selects from.
GLOBAL_STORE = (".indexed", "data", "collections")

RESOURCE_URIS = ("resource://collections", "resource://collections/status")


class _ScopedContext:
    """Just enough of a FastMCP ``Context`` to serve one scoped request.

    ``is_background_task`` and ``_request_state`` are the attributes FastMCP's
    dependency wrapper touches on the current context; ``list_roots`` is the one
    call that carries this request's scope.
    """

    is_background_task = False

    def __init__(self, roots: Sequence[Path] = ()) -> None:
        from mcp.types import FileUrl, Root

        self._roots = [
            Root(uri=FileUrl(Path(root).resolve().as_uri()), name=Path(root).name)
            for root in roots
        ]
        self._request_state: dict[str, Any] = {}

    async def list_roots(self) -> list[Any]:
        return list(self._roots)


def _define(repo: Path, *names: str) -> Path:
    """Write the repository's committed ``indexed.toml`` selecting ``names``."""
    repo.mkdir(parents=True, exist_ok=True)
    entries = ", ".join(f'"{name}"' for name in names)
    path = repo / "indexed.toml"
    path.write_text(
        f"version = 1\n\n[collections]\nuse = [{entries}]\n", encoding="utf-8"
    )
    return path


def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the global store (``~/.indexed``) at a per-test ``tmp_path/home``."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


@pytest.fixture
def mcp_resource_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write_manifest
):
    """A scoped request: one global collection, one repository selecting it."""
    from fastmcp.server.context import Context, _current_context

    home = _isolated_home(tmp_path, monkeypatch)
    write_manifest(home.joinpath(*GLOBAL_STORE), COLLECTION_NAME)

    repo = tmp_path / "repo"
    _define(repo, COLLECTION_NAME)
    ctx = _ScopedContext([repo])

    # A resource read through ``mcp.read_resource`` builds FastMCP's own Context
    # for the request, and a real one cannot reach a client's roots without a
    # session. Install the client's capability on that class so the request sees
    # the same roots as the context below.
    async def _list_roots(_self: Context) -> list[Any]:
        return await ctx.list_roots()

    monkeypatch.setattr(Context, "list_roots", _list_roots)

    token = _current_context.set(ctx)
    yield ctx
    _current_context.reset(token)


def _read_resource_json(uri: str) -> dict[str, object]:
    result = asyncio.run(mcp.read_resource(uri))
    assert result.contents
    return json.loads(result.contents[0].content)


def test_mcp_collections_list_resource_keys(mcp_resource_context) -> None:
    del mcp_resource_context
    payload = _read_resource_json("resource://collections")
    assert "collections" in payload
    assert COLLECTION_NAME in payload["collections"]


def test_mcp_collections_status_resource_keys(mcp_resource_context) -> None:
    del mcp_resource_context
    payload = _read_resource_json("resource://collections/status")
    assert "collections" in payload
    collections = payload["collections"]
    assert isinstance(collections, list)
    assert len(collections) >= 1
    status = collections[0]
    for key in (
        "name",
        "number_of_documents",
        "number_of_chunks",
        "source_type",
        "indexers",
    ):
        assert key in status


def test_mcp_resources_without_roots_report_no_request_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write_manifest
) -> None:
    """A client that presents no roots is told, and served nothing.

    The store and a definition selecting ``COLLECTION_NAME`` both exist; the
    client simply never says which workspace it belongs to, so the server must
    not fall back to every collection.
    """
    from fastmcp.server.context import Context

    home = _isolated_home(tmp_path, monkeypatch)
    write_manifest(home.joinpath(*GLOBAL_STORE), COLLECTION_NAME)
    _define(tmp_path / "repo", COLLECTION_NAME)

    async def _no_roots(_self: Context) -> list[Any]:
        return []

    monkeypatch.setattr(Context, "list_roots", _no_roots)

    for uri in RESOURCE_URIS:
        payload = _read_resource_json(uri)
        assert payload["type"] == "NoRequestScopeError", payload
        assert "collections" not in payload
