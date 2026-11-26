"""Characterization: MCP `search` tool smoke against a real seeded collection.

Complements ``test_mcp_smoke.py`` (which covers the collection *resources*) by
driving the MCP ``search`` *tool* in-process against a collection built with the
real engine (real FAISS + embeddings), asserting a known document comes back.
This is the behavior-net proof that the agent-facing surface returns real hits.

Scope is per request (#345): the collection is seeded in the GLOBAL store under
an isolated ``$HOME``, and the tool call carries a context whose roots are a
repository whose ``indexed.toml`` selects it.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Sequence

import pytest

from indexed.config import reload as reload_config
from tests.conftest import model_available

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

COLLECTION = "mcp-search-net"

#: ``~/.indexed/data/collections`` — the one store a definition selects from.
GLOBAL_STORE = (".indexed", "data", "collections")


class _ScopedContext:
    """Just enough of a FastMCP ``Context`` to serve one scoped request.

    ``search`` resolves its scope from ``list_roots``; ``lifespan_context``
    carries the search config exactly as FastMCP's lifespan would inject it.
    """

    is_background_task = False

    def __init__(self, roots: Sequence[Path] = (), *, lifespan: Any = None) -> None:
        from mcp.types import FileUrl, Root

        self._roots = [
            Root(uri=FileUrl(Path(root).resolve().as_uri()), name=Path(root).name)
            for root in roots
        ]
        self.lifespan_context = {} if lifespan is None else lifespan
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
    """Point the global store (``~/.indexed``) at a per-test ``tmp_path/home``.

    Faking ``HOME`` hides the HOME-relative HuggingFace cache, so the real one is
    re-exported explicitly (same arrangement as ``tests/conftest.py``'s model
    fixtures): the engine still runs real embeddings from the cached model.
    """
    real_hf_home = Path(os.environ["HOME"]) / ".cache" / "huggingface"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("HF_HOME", str(real_hf_home))
    monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(real_hf_home / "hub"))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TQDM_DISABLE", "1")
    monkeypatch.setattr(Path, "home", lambda: home)
    reload_config()
    return home


def _get_tool(name: str):
    from indexed.mcp.server import mcp

    return asyncio.run(mcp.get_tool(name))


@pytest.fixture
def _no_response_cache():
    """Drop ResponseCachingMiddleware so the tool result is not cached."""
    from fastmcp.server.middleware.caching import ResponseCachingMiddleware

    from indexed.mcp.server import mcp

    original = list(mcp.middleware)
    mcp.middleware = [
        m for m in original if not isinstance(m, ResponseCachingMiddleware)
    ]
    yield
    mcp.middleware = original


def test_mcp_search_tool_returns_seeded_hit(
    local_workspace,
    files_corpus: Path,
    build_collection,
    _no_response_cache,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from indexed.connectors.files.connector import FileSystemConnector
    from indexed.core.v1.config_models import CoreV1SearchConfig

    # The store a definition selects from is the GLOBAL one under this test's
    # HOME, not the local ``./.indexed`` the workspace fixture materializes.
    home = _isolated_home(local_workspace.root, monkeypatch)
    collections_dir = home.joinpath(*GLOBAL_STORE)

    # Seed a real, searchable collection in that global store.
    connector = FileSystemConnector(path=str(files_corpus), include_patterns=["*.txt"])
    build_collection(
        collections_dir,
        COLLECTION,
        connector.reader,
        connector.converter,
    )

    # ...and a repository whose committed definition selects it.
    repo = local_workspace.root / "repo"
    _define(repo, COLLECTION)

    # A lifespan-shaped context passed straight to the tool fn (mirrors how
    # FastMCP injects it): its roots are the request's scope, its lifespan state
    # carries the search config.
    tool_ctx = _ScopedContext([repo], lifespan={"search_config": CoreV1SearchConfig()})

    # Fetch the tool BEFORE any context is active (get_tool must not await a mock).
    search_tool = _get_tool("search")
    result = asyncio.run(
        search_tool.fn("penguin migration survey Antarctic coastline", ctx=tool_ctx)
    )

    assert result["query"].startswith("penguin migration")
    assert result["schema"] == "indexed.search/1"
    assert len(result["collections"]) >= 1
    assert result["documents"], "MCP search tool returned no results for a seeded hit"
    top = result["documents"][0]
    assert top["id"].endswith("needle.txt"), (
        f"expected needle.txt as top MCP hit, got {top['id']!r}"
    )
    assert top["collection"] == COLLECTION
