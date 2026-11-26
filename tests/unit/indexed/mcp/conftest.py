"""Per-request scope harness for the MCP server tests (#345).

The MCP tools and resources resolve their workspace scope from the client's MCP
roots on every request, so a test that wants real output must present a real
workspace: an isolated ``$HOME`` with a global collection store, and a
repository whose committed ``indexed.toml`` selects the collections under test.
``scoped("a", "b")`` builds exactly that and returns the request context.

The two scope-specific suites (``test_request_scope``, ``test_tools_scope``)
carry their own local harnesses on purpose: they pin the resolver's edges
(no roots, ambiguity, foreign roots) which these conveniences would hide.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, Sequence

import pytest
from fastmcp.server.context import Context
from mcp.types import FileUrl, Root

STORE_PARTS = (".indexed", "data", "collections")


class ScopeContext:
    """Just enough of a FastMCP ``Context`` to serve one scoped request."""

    def __init__(
        self, roots: Sequence[Path] = (), *, lifespan: Optional[dict] = None
    ) -> None:
        self._roots = [
            Root(uri=FileUrl(Path(root).resolve().as_uri())) for root in roots
        ]
        self.lifespan_context = {} if lifespan is None else lifespan
        # Attributes FastMCP's dependency wrapper touches on the current context.
        self.is_background_task = False
        self._request_state: dict[str, Any] = {}

    async def list_roots(self) -> list[Root]:
        return list(self._roots)


def _store(home: Path, *names: str) -> Path:
    """Create ``names`` as collections of the global store under ``home``."""
    collections = home.joinpath(*STORE_PARTS)
    for name in names:
        (collections / name).mkdir(parents=True, exist_ok=True)
        (collections / name / "manifest.json").write_text("{}", encoding="utf-8")
    return collections


def _define(repo: Path, *names: str) -> Path:
    """Write a committed ``indexed.toml`` at ``repo`` selecting ``names``."""
    repo.mkdir(parents=True, exist_ok=True)
    entries = ", ".join(f'"{name}"' for name in names)
    path = repo / "indexed.toml"
    path.write_text(
        f"version = 1\n\n[collections]\nuse = [{entries}]\n", encoding="utf-8"
    )
    return path


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated ``$HOME``; a scoped request reads its global store here."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


@pytest.fixture
def scoped(tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Factory: ``scoped("a", "b")`` → a context whose roots select ``a`` and ``b``.

    The client's roots are the only source of scope, so the returned context is
    what a tool call must receive as ``ctx``. The roots capability is also
    installed on FastMCP's own ``Context`` so an end-to-end read through
    ``mcp.read_resource`` sees the same client, exactly like a real client that
    advertises its repository.
    """

    def build(*names: str, lifespan: Optional[dict] = None) -> ScopeContext:
        _store(home, *names)
        repo = tmp_path / "repos" / "alpha"
        _define(repo, *names)

        async def _list_roots(_self: Context) -> list[Root]:
            return [Root(uri=FileUrl(repo.resolve().as_uri()))]

        monkeypatch.setattr(Context, "list_roots", _list_roots)
        return ScopeContext([repo], lifespan=lifespan)

    return build


@pytest.fixture
def bound() -> Any:
    """Context manager making an object the current FastMCP context.

    Resources inject ``ctx`` from FastMCP's context variable (a template
    function is validation-wrapped, so ``ctx`` cannot be passed as a keyword),
    so a resource read in a test binds its scope context the way the server
    binds the request's context.
    """

    @contextmanager
    def bind(ctx: Any) -> Any:
        from fastmcp.server.context import _current_context

        token = _current_context.set(ctx)
        try:
            yield
        finally:
            _current_context.reset(token)

    return bind


@pytest.fixture
def mcp_status() -> Any:
    """Factory for a ``svc_status`` result: every field ``_format_status`` reads."""

    def build(
        name: str,
        *,
        indexers: Sequence[str] = ("indexer_FAISS",),
        source_type: Optional[str] = "localFiles",
        **overrides: Any,
    ) -> SimpleNamespace:
        fields: dict[str, Any] = {
            "name": name,
            "number_of_documents": 1,
            "number_of_chunks": 1,
            "updated_time": "2026-11-26T09:00:00+00:00",
            "last_modified_document_time": "2026-11-26T09:00:00+00:00",
            "indexers": list(indexers),
            "index_size": 1,
            "source_type": source_type,
            "relative_path": f"{name}/src",
            "disk_size_bytes": 10,
            "freshness": None,
        }
        fields.update(overrides)
        return SimpleNamespace(**fields)

    return build
