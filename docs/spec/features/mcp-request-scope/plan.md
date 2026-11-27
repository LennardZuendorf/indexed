---
type: feature-plan
feature: mcp-request-scope
sibling: tech.md
parent: ../../plan.md
updated: 2026-11-27
---

# Feature: MCP Request Scope — Plan

**Parent:** issue [#345](https://github.com/LennardZuendorf/indexed/issues/345) ·
**Product:** [product.md](product.md) · **Tech:** [tech.md](tech.md).

## Slices

| # | Slice | Gate | Status |
|---|-------|------|--------|
| 1 | `mcp/scope.py` — roots → one definition, three named errors | two roots, two definitions, two answers; zero and two definitions each raise their own type | ✅ DONE |
| 2 | tools and resources resolve scope per request | one server, two clients, `search` and `resource://collections*` each scoped to their own client | ✅ DONE |
| 3 | CLI and LSP resolve the same fixture to the same names | one fixture, three surfaces, identical collection names | ✅ DONE |

## Acceptance test (can go red)

`tests/system/test_mcp_request_scope.py` — one out-of-process HTTP server over
one global store, two concurrent FastMCP clients:

- client A rooted at `alpha` (its `indexed.toml` selects `alpha-docs`),
  client B rooted at `beta` (`beta-docs`): A's search hits only `alpha-docs`
  documents, B's only `beta-docs`; each client's
  `resource://collections` and `resource://collections/status` list exactly its
  own selection, in definition order;
- a client with no roots gets a `NoRequestScopeError` envelope and zero
  collections;
- a client presenting both roots gets an `AmbiguousRequestScopeError` envelope;
- a `resource://collection/{name}` read for a name outside the client's
  selection is the *same* `CollectionOutsideScopeError` envelope — message
  included — that `search_collection` returns, and the in-scope read still
  answers with that collection's status;
- the CLI (`indexed search`, cwd `alpha`) and the LSP backend resolved for
  `alpha` name the same collections as client A.

The HTTP/server pair is out-of-process for the reason recorded in
`docs/spec/lessons.md`: an in-process FastMCP client next to llama-index and
torch segfaults.

## Dependencies

- [workspace-selection](../workspace-selection/tech.md) — shipped; this feature
  consumes its resolver and its `find_definition` rule unchanged.
- Installer roots ([#348](https://github.com/LennardZuendorf/indexed/issues/348))
  — out of scope. A client that does not advertise roots is now told so, by a
  named error, instead of silently searching the whole store.
