---
type: feature-tech
feature: mcp-request-scope
sibling: product.md
parent: ../../tech.md
updated: 2026-11-26
---

# Feature: MCP Request Scope — Tech

**Sibling:** [product.md](product.md) · **Plan:** [plan.md](plan.md) ·
issue [#345](https://github.com/LennardZuendorf/indexed/issues/345).

## Where scope comes from

MCP **roots**: the protocol's client-declared set of directories
(`roots/list`). The server asks for them on **every** request —
`await ctx.list_roots()` inside each tool and resource — so scope is a function
of the request, never of the process. The server's CWD, its startup
`CliContext` and whatever the previous request used are not inputs.

A root URI is a `file://` URL; anything else (a remote root) cannot hold a
worktree definition and is ignored for scope. Roots are directories, or a file
whose parent is used.

## Resolution (`src/indexed/mcp/scope.py`)

```
roots → (find_definition per root) → distinct definitions
 0 distinct  → NoRequestScopeError
 >1 distinct → AmbiguousRequestScopeError
 1 distinct  → WorkspaceSelection via load_selection (same resolver as CLI/LSP)
```

- `find_definition` is the workspace-selection discovery: nearest
  `indexed.toml` at or above the root, stopping before `$HOME`. Same rule for
  CLI, LSP and MCP — the parity requirement is one fixture, three surfaces.
- Roots that resolve to **no** definition contribute nothing and never widen a
  request to the whole store. A root set with exactly one definition is scoped
  to it even if another root (a scratch directory, a tool cache) has none.
- Two roots resolving to the **same** definition (a repo root and a subdirectory,
  two worktrees on identical branches) are one scope, not an ambiguity.
- Resolution runs per request and is not cached: a branch switch or an edited
  `indexed.toml` must be visible on the next call. The file is small and
  `load_selection` reads it in one go.
- A client that does not advertise the roots capability makes
  `ctx.list_roots()` raise `McpError("List roots not supported")`; that is
  translated to `NoRequestScopeError`, not allowed to become a protocol error.

A definition always pins the **global** store (workspace-selection, precedence
row 1), so `RequestScope.collections_path` is
`get_collections_path(get_global_root())` — never the server process's local
mode. The server's startup `CliContext` keeps its one remaining job (the
watcher's root) and is no longer consulted for scope.

## Errors (documented envelopes)

All three subclass `MCPScopeError(IndexedError)`, so the existing boundary
(`mcp_error_envelope`) returns `{"error": <message>, "type": <ClassName>}` and
the resource boundary envelopes them like every other failure:

| Type | When |
|---|---|
| `NoRequestScopeError` | no roots, roots unsupported, or no root has an `indexed.toml` |
| `AmbiguousRequestScopeError` | the presented roots resolve to more than one `indexed.toml` |
| `CollectionOutsideScopeError` | an explicit collection name is outside the request's selection |

Messages name the roots that were presented, the definition(s) found, and the
remedy (commit `indexed.toml` at the repository root, or connect the client to
the repository). Every one is an error, never an empty success: an agent must
be able to tell "nothing matched" from "you may not see".

## Where the scope is applied

| Surface | Behaviour |
|---|---|
| `search` | builds per-collection search configs from the selection, in definition order (the CLI's code path) — the store is never enumerated unfiltered |
| `search_collection(name)` | `name` outside the selection → `CollectionOutsideScopeError`; inside → unchanged |
| `resource://collections` | the selection's names, definition order |
| `resource://collections/status` | the selection's statuses, definition order |
| `resource://collection/{name}` | out of scope → `CollectionOutsideScopeError`; inside → unchanged |

Tools and resources become `async def` because `ctx.list_roots()` is a coroutine;
FastMCP runs async tools on the server loop, and the scope lookup is the only
awaited call before the existing synchronous engine work. Search execution stays
sync — it is CPU/IO-bound engine work, not I/O the loop can overlap.

A selected collection the store no longer serves is caught during resolution
(`load_selection` validates every entry against the store) and raises
`WorkspaceSelectionError`; the tool surfaces it as an envelope, never as a
narrower result.

## Divergence from the CLI, on purpose

The CLI's absence-of-definition rule ("every collection", workspace-selection
R4) and its explicit-`--collection`-wins rule (R5) are user-at-the-keyboard
affordances: one user, one process, one store. The MCP server is one process for
many unrelated repositories, so both become errors (product R5). Parity is
asserted on a repository that has a definition — the case every surface must
agree on.

## Module boundaries

`mcp/scope.py` is a presentation-layer module: it may import `config`
(`workspace_selection`, `collections_registry`, `storage`) and `cli.errors`; it
imports neither `core` nor `cli` at module top. `tools.py` and `resources.py`
call it once per request; `config.py` keeps its config/lifespan helpers.
