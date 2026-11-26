"""Per-request workspace scope for the MCP server (#345).

The server is one process for many clients, so scope is a property of the
request: the client's MCP roots resolve to exactly one committed
``indexed.toml``. No roots, no definition, or two definitions is a named error —
never the whole store.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Sequence

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from indexed.mcp.scope import (
    AmbiguousRequestScopeError,
    NoRequestScopeError,
    RequestScope,
    resolve_request_scope,
)

pytestmark = pytest.mark.unit


# --- harness -----------------------------------------------------------------


class _Root:
    """The one attribute of ``mcp.types.Root`` the resolver reads."""

    def __init__(self, uri: str) -> None:
        self.uri = uri


class _FakeContext:
    """Just enough of a FastMCP ``Context``: an awaitable ``list_roots``."""

    def __init__(self, roots: Sequence[_Root] = (), *, unsupported: bool = False):
        self._roots = list(roots)
        self._unsupported = unsupported

    async def list_roots(self) -> list[_Root]:
        if self._unsupported:
            raise McpError(ErrorData(code=0, message="List roots not supported"))
        return self._roots


def _root(path: Path) -> _Root:
    return _Root(uri=path.resolve().as_uri())


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at an isolated directory with a global store."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


def _store(home: Path, *names: str) -> Path:
    """Create ``names`` as collections of the global store under ``home``."""
    collections = home / ".indexed" / "data" / "collections"
    for name in names:
        (collections / name).mkdir(parents=True, exist_ok=True)
        (collections / name / "manifest.json").write_text("{}", encoding="utf-8")
    return collections


def _define(root: Path, *names: str) -> Path:
    """Write a committed ``indexed.toml`` at ``root`` selecting ``names``."""
    root.mkdir(parents=True, exist_ok=True)
    entries = ", ".join(f'"{name}"' for name in names)
    path = root / "indexed.toml"
    path.write_text(
        f"version = 1\n\n[collections]\nuse = [{entries}]\n", encoding="utf-8"
    )
    return path


def _resolve(ctx: Any) -> RequestScope:
    return asyncio.run(resolve_request_scope(ctx))


# --- resolution --------------------------------------------------------------


def test_one_root_with_a_definition_scopes_the_request(home: Path, tmp_path: Path):
    collections = _store(home, "alpha-docs", "beta-docs")
    alpha = tmp_path / "repos" / "alpha"
    definition = _define(alpha, "alpha-docs")

    scope = _resolve(_FakeContext([_root(alpha)]))

    assert scope.selection.names == ("alpha-docs",)
    assert scope.selection.path == definition
    assert scope.collections_path == collections


def test_scope_always_reads_the_global_store(home: Path, tmp_path: Path):
    """A definition pins the global store; the server's own mode never leaks in."""
    collections = _store(home, "alpha-docs")
    alpha = tmp_path / "repos" / "alpha"
    _define(alpha, "alpha-docs")
    # A local store next to the "server workspace" must not be consulted.
    local = tmp_path / "server-cwd" / ".indexed" / "data" / "collections" / "local"
    local.mkdir(parents=True)

    scope = _resolve(_FakeContext([_root(alpha)]))

    assert scope.collections_path == collections


def test_two_clients_two_roots_two_answers(home: Path, tmp_path: Path):
    _store(home, "alpha-docs", "beta-docs")
    alpha = tmp_path / "repos" / "alpha"
    beta = tmp_path / "repos" / "beta"
    _define(alpha, "alpha-docs")
    _define(beta, "beta-docs")
    shared = _FakeContext([_root(alpha)])
    other = _FakeContext([_root(beta)])

    assert _resolve(shared).selection.names == ("alpha-docs",)
    assert _resolve(other).selection.names == ("beta-docs",)


def test_no_roots_is_a_named_error(home: Path):
    with pytest.raises(NoRequestScopeError) as raised:
        _resolve(_FakeContext([]))
    assert "root" in str(raised.value).lower()


def test_a_client_without_the_roots_capability_is_a_named_error(home: Path):
    with pytest.raises(NoRequestScopeError) as raised:
        _resolve(_FakeContext(unsupported=True))
    assert "roots" in str(raised.value).lower()


def test_a_root_without_a_definition_is_a_named_error(home: Path, tmp_path: Path):
    _store(home, "alpha-docs")
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    with pytest.raises(NoRequestScopeError) as raised:
        _resolve(_FakeContext([_root(scratch)]))

    assert "indexed.toml" in str(raised.value)


def test_two_definitions_are_ambiguous(home: Path, tmp_path: Path):
    _store(home, "alpha-docs", "beta-docs")
    alpha = tmp_path / "repos" / "alpha"
    beta = tmp_path / "repos" / "beta"
    alpha_definition = _define(alpha, "alpha-docs")
    beta_definition = _define(beta, "beta-docs")

    with pytest.raises(AmbiguousRequestScopeError) as raised:
        _resolve(_FakeContext([_root(alpha), _root(beta)]))

    message = str(raised.value)
    assert str(alpha_definition) in message
    assert str(beta_definition) in message


def test_two_roots_in_one_repository_are_one_scope(home: Path, tmp_path: Path):
    _store(home, "alpha-docs")
    alpha = tmp_path / "repos" / "alpha"
    _define(alpha, "alpha-docs")
    nested = alpha / "src" / "pkg"
    nested.mkdir(parents=True)

    scope = _resolve(_FakeContext([_root(alpha), _root(nested)]))

    assert scope.selection.names == ("alpha-docs",)


def test_a_root_without_a_definition_does_not_widen_a_scoped_request(
    home: Path, tmp_path: Path
):
    _store(home, "alpha-docs", "beta-docs")
    alpha = tmp_path / "repos" / "alpha"
    _define(alpha, "alpha-docs")
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    scope = _resolve(_FakeContext([_root(scratch), _root(alpha)]))

    assert scope.selection.names == ("alpha-docs",)


def test_a_non_file_root_is_ignored(home: Path, tmp_path: Path):
    _store(home, "alpha-docs")
    alpha = tmp_path / "repos" / "alpha"
    _define(alpha, "alpha-docs")

    scope = _resolve(
        _FakeContext([_Root(uri="git+ssh://example.invalid/repo"), _root(alpha)])
    )
    assert scope.selection.names == ("alpha-docs",)

    with pytest.raises(NoRequestScopeError):
        _resolve(_FakeContext([_Root(uri="git+ssh://example.invalid/repo")]))


def test_scope_is_re_resolved_per_request(home: Path, tmp_path: Path):
    """A branch switch between two calls must change the answer."""
    _store(home, "alpha-docs", "beta-docs")
    alpha = tmp_path / "repos" / "alpha"
    _define(alpha, "alpha-docs")
    ctx = _FakeContext([_root(alpha)])

    assert _resolve(ctx).selection.names == ("alpha-docs",)

    _define(alpha, "beta-docs")
    assert _resolve(ctx).selection.names == ("beta-docs",)


def test_definition_order_is_preserved(home: Path, tmp_path: Path):
    _store(home, "a-docs", "b-docs")
    repo = tmp_path / "repos" / "alpha"
    _define(repo, "b-docs", "a-docs")

    scope = _resolve(_FakeContext([_root(repo)]))

    assert scope.selection.names == ("b-docs", "a-docs")
