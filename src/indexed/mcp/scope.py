"""Per-request workspace scope for the MCP server (#345).

One long-lived server serves many clients, each in its own repository, so scope
belongs to the request: the client declares the directories it works in (MCP
**roots**) and the server resolves them to exactly one committed
``indexed.toml`` — the same discovery and resolver the CLI and the LSP use.

The server never guesses. No roots, no definition at any root, or two
definitions that disagree is a named error, not an unfiltered store: a client it
cannot place must not be able to see another project's collections.

This is the presentation layer: it may import ``config`` and nothing above it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import unquote, urlparse

from loguru import logger

from indexed.config.collections_registry import CollectionRegistry
from indexed.config.errors import IndexedError
from indexed.config.storage import get_collections_path, get_global_root
from indexed.config.workspace_selection import (
    WorkspaceSelection,
    find_definition,
    load_selection,
)


class MCPScopeError(IndexedError):
    """A request cannot be given a workspace scope, so it must not be served."""


class NoRequestScopeError(MCPScopeError):
    """The request presents no roots, or no root carries an ``indexed.toml``."""


class AmbiguousRequestScopeError(MCPScopeError):
    """The request's roots resolve to more than one workspace definition."""


class CollectionOutsideScopeError(MCPScopeError):
    """An explicitly named collection is outside the request's scope."""


@dataclass(frozen=True)
class RequestScope:
    """The one workspace definition a request is scoped to."""

    selection: WorkspaceSelection
    #: Always the global store: a definition pins the whole store, so the
    #: server's own storage mode must never decide where a request reads.
    collections_path: Path
    #: The client's roots as resolved filesystem paths (diagnostics only).
    roots: tuple[Path, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return self.selection.names


def root_path(uri: Any) -> Optional[Path]:
    """The filesystem path of a root URI, or ``None`` for a remote root.

    Only ``file://`` roots can hold a worktree definition. Anything else — a
    ``git+ssh://`` root, a URL — is not ignored silently as evidence of scope,
    but it cannot contribute one either.
    """
    parsed = urlparse(str(uri))
    if parsed.scheme != "file":
        return None
    path = Path(unquote(parsed.path))
    return path


def _describe(paths: Iterable[Path]) -> str:
    return ", ".join(f"'{path}'" for path in paths) or "none"


def scope_from_roots(roots: Iterable[Path]) -> RequestScope:
    """Resolve already-parsed root paths to one scope, or raise a named error.

    Roots without a definition contribute nothing: a scratch directory beside a
    repository must not turn a scoped request into an unscoped one. Roots that
    resolve to the *same* definition (a repo root and a subdirectory) are one
    scope, not an ambiguity.
    """
    paths = tuple(roots)
    definitions: dict[Path, Path] = {}
    for root in paths:
        definition = find_definition(root)
        if definition is not None:
            definitions.setdefault(definition, root)

    if not definitions:
        raise NoRequestScopeError(
            f"No 'indexed.toml' was found at or above this client's roots "
            f"({_describe(paths)}). Commit one at the repository root "
            "(see `indexed storage migrate`) or connect the client from a "
            "repository that has one — this server never falls back to every "
            "collection."
        )
    if len(definitions) > 1:
        raise AmbiguousRequestScopeError(
            "This client's roots resolve to more than one workspace definition "
            f"({_describe(sorted(definitions))}). An indexed MCP request has "
            "exactly one scope; connect one client per repository."
        )

    definition = next(iter(definitions))
    collections_path = get_collections_path(get_global_root())
    selection = load_selection(
        definition.parent,
        registry=CollectionRegistry(),
        collections_path=collections_path,
        # A search degrades per source (#340): a definition entry the store can
        # no longer serve is reported as a `missing` source, not as a failure
        # that costs the other collections' answer. Broken *files* still raise.
        strict=False,
    )
    # ``find_definition`` just found this file from this directory; if it is gone
    # already (a branch switch between discovery and resolution), fail closed with
    # the scope error rather than serving an unscoped request.
    if selection is None:
        raise NoRequestScopeError(
            f"Workspace definition '{definition}' disappeared while this request "
            "was being resolved. Retry; if the definition is gone, commit one at "
            "the repository root or connect the client from a repository that has "
            "one."
        )
    return RequestScope(
        selection=selection, collections_path=collections_path, roots=paths
    )


async def request_roots(ctx: Any) -> tuple[Path, ...]:
    """The client's roots for this request, as paths (``McpError`` on absence)."""
    if ctx is None or not hasattr(ctx, "list_roots"):
        raise NoRequestScopeError(
            "This MCP request carries no client context, so it presents no "
            "workspace scope. An indexed MCP client must advertise the "
            "repository directory it works in (MCP roots)."
        )
    try:
        declared = await ctx.list_roots()
    except Exception as exc:  # noqa: BLE001 - any failure here means "unscoped"
        # The common case is a client that does not implement the roots
        # capability: the protocol call itself raises "List roots not
        # supported". Fail closed with our own named error rather than letting
        # a protocol error escape or, worse, serving the whole store.
        logger.debug("MCP client did not present roots: {}", exc)
        raise NoRequestScopeError(
            "This MCP client does not present workspace roots, so the server "
            "cannot tell which repository the request belongs to. Configure "
            "the client to advertise its repository root (MCP roots)."
        ) from exc
    return tuple(
        path for path in (root_path(root.uri) for root in declared) if path is not None
    )


async def resolve_request_scope(ctx: Any) -> RequestScope:
    """Resolve *this request's* scope from the client's roots.

    Called per tool call and per resource read: nothing is cached, so an edited
    ``indexed.toml`` or a switched branch is visible on the next request.

    Raises an :class:`IndexedError` for every way a request can be unplaceable —
    the scope errors below, or ``WorkspaceSelectionError`` out of
    ``load_selection`` when the definition names a collection the store no longer
    serves. The MCP boundary envelopes ``IndexedError``, so an agent always gets
    ``{"error", "type"}`` rather than a protocol error it cannot read.
    """
    return scope_from_roots(await request_roots(ctx))


def require_in_scope(scope: RequestScope, name: str) -> None:
    """Raise unless ``name`` is selected by the request's definition.

    Membership is judged on the *intended* scope (``selection.scope``), so a name
    the definition lists but the store no longer serves is in scope — it then
    reaches the store and is reported as unusable/missing, which is the true
    problem, instead of being called someone else's collection.
    """
    if name in scope.selection.scope:
        return
    selected = ", ".join(f"'{entry}'" for entry in scope.selection.scope)
    raise CollectionOutsideScopeError(
        f"Collection '{name}' is outside this request's workspace scope: "
        f"'{scope.selection.path}' selects {selected}. Ask the user to add it "
        "to that file, or connect the client from a repository whose "
        "definition selects it."
    )
