"""MCP ``search`` answers the request's scope, not the whole store (#340/#345).

The CLI has narrowed ``index search`` to ``indexed.toml`` since #344; the MCP
tool used to pass ``configs=None`` and search every collection in the store, and
then (before #345) took the *server process's* workspace. Now the scope is the
request's own: the selection decides the configs, an unresolvable entry is named
per source, and a fully dead selection never silently widens to the store.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from indexed.config.workspace_selection import (
    SelectedCollection,
    UnresolvedEntry,
    WorkspaceSelection,
)
from indexed.mcp import tools as tools_module
from indexed.mcp import server as server_module
from indexed.mcp.scope import RequestScope

pytestmark = pytest.mark.unit


def _request_scope(selection: WorkspaceSelection) -> RequestScope:
    return RequestScope(
        selection=selection, collections_path=Path("/store/collections"), roots=()
    )


def _scope_stub(selection: WorkspaceSelection):
    """An async resolver returning ``selection``'s request scope."""

    async def _resolve(_ctx: object = None) -> RequestScope:
        return _request_scope(selection)

    return _resolve


def _status(name: str, *, source_type: str = "localFiles", documents: int = 1) -> Mock:
    status = Mock()
    status.name = name
    status.indexers = ["default"]
    status.source_type = source_type
    status.number_of_documents = documents
    return status


def _selection(
    *names: str, unresolved: tuple[UnresolvedEntry, ...] = ()
) -> WorkspaceSelection:
    definition = Path("/repo/indexed.toml")
    collections = tuple(
        SelectedCollection(name=name, position=index)
        for index, name in enumerate(names)
    )
    return WorkspaceSelection(
        path=definition,
        root=definition.parent,
        collections=collections,
        unresolved=unresolved,
    )


def _raw(*names: str) -> dict:
    return {
        name: {
            "collectionName": name,
            "indexerName": "default",
            "sourceType": "localFiles",
            "results": [
                {
                    "id": f"{name}/doc",
                    "url": f"file:///repo/{name}/doc.md",
                    "matchedChunks": [
                        {
                            "chunkNumber": 0,
                            "score": 0.1,
                            "content": {
                                "indexedData": f"answer in {name}",
                                "metadata": {"headings": ["Answer"]},
                            },
                        }
                    ],
                }
            ],
        }
        for name in names
    }


def _call_search() -> dict:
    tool = asyncio.run(server_module.mcp.get_tool("search"))
    return asyncio.run(tool.fn("how do I rotate the signing key"))


def _config() -> Mock:
    search_cfg = Mock()
    search_cfg.max_docs = 10
    search_cfg.max_chunks = 30
    search_cfg.score_threshold = None
    search_cfg.include_full_text = False
    search_cfg.include_all_chunks = False
    search_cfg.git_provenance = False
    search_cfg.git_line_blame = False
    search_cfg.git_rerank = False
    return search_cfg


def test_mcp_search_uses_the_workspace_selection() -> None:
    """Only selected collections are searched, and the dead entry is named."""
    selection = _selection(
        "wiki",
        "src",
        unresolved=(
            UnresolvedEntry(
                entry="gone",
                name="gone",
                reason=(
                    "Workspace definition '/repo/indexed.toml' selects collection "
                    "'gone', which is not in the store."
                ),
                position=2,
            ),
        ),
    )
    seen_configs: list = []

    def fake_search(query, configs=None, **_kwargs):
        seen_configs.append(configs)
        return _raw(*(config.name for config in configs or ()))

    with (
        patch.object(tools_module, "_resolve_config", return_value=_config()),
        patch.object(
            tools_module,
            "resolve_request_scope",
            _scope_stub(selection),
        ),
        patch.object(
            tools_module,
            "svc_status",
            return_value=[
                _status("wiki"),
                _status("src"),
                # Present in the store but NOT selected: must not be searched.
                _status("unrelated"),
            ],
        ),
        patch.object(tools_module, "svc_search", side_effect=fake_search),
    ):
        payload = _call_search()

    assert [config.name for config in seen_configs[0]] == ["wiki", "src"]
    assert payload["collections"] == ["wiki", "src"]
    assert [source["collection"] for source in payload["sources"]] == [
        "wiki",
        "src",
        "gone",
    ]
    assert payload["sources"][2]["status"] == "missing"
    assert "not in the store" in payload["sources"][2]["error"]
    assert payload["collection_errors"] == [
        {"collection": "gone", "error": payload["sources"][2]["error"]}
    ]


def test_mcp_search_never_widens_to_the_store_when_every_selection_is_dead() -> None:
    """A fully unresolvable selection is a named empty answer, not the store."""
    selection = _selection(
        unresolved=(
            UnresolvedEntry(
                entry="wiki",
                name="wiki",
                reason="Collection 'wiki' is not in the store.",
                position=0,
            ),
        ),
    )
    search = Mock()

    with (
        patch.object(tools_module, "_resolve_config", return_value=_config()),
        patch.object(
            tools_module,
            "resolve_request_scope",
            _scope_stub(selection),
        ),
        patch.object(tools_module, "svc_status", return_value=[_status("unrelated")]),
        patch.object(tools_module, "svc_search", search),
    ):
        payload = _call_search()

    search.assert_not_called()
    assert payload["collections"] == []
    assert payload["counts"] == {"documents": 0, "hits": 0}
    assert [source["status"] for source in payload["sources"]] == ["missing"]
    assert "not in the store" in payload["sources"][0]["error"]
