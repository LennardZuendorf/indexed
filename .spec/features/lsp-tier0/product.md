---
type: feature-product
feature: lsp-tier0
sibling: tech.md
parent: ../../plan.md
updated: 2026-11-10
---

# `indexed lsp` — Tier 0 (product)

**Issue:** [#241](https://github.com/LennardZuendorf/indexed/issues/241)
**Plan:** [plan.md](plan.md) · **Architecture:** [tech.md](tech.md)

## Why

Every editor speaks the Language Server Protocol. An agent already reaches the
index through MCP; a *human* looking at code has no way in without leaving the
editor. Tier 0 puts the index where the human already is: a symbol palette that
searches the knowledge base, and a hover that shows what the index knows about
the file under the cursor.

The point is not "go to definition" — the index is not a compiler. The point is
that a file rarely explains itself: hover on `alpha()` shows what the index
knows about that file — the matching chunk, which collection it came from, how
fresh that collection is, and how well the chunk scored.

Tier 0 answers from the one collection that owns the file under the cursor, so
hover never reopens every collection on a keystroke (issue #126). Surfacing a
Jira issue or a Confluence page from a *different* collection in the same hover
is deferred to Tier 1; in Tier 0 the cross-collection surface is
`workspace/symbol`.

## What shipped (Tier 0)

- `indexed lsp` serves LSP over stdio from the same collections the CLI and MCP
  server read (active storage mode, `--local` honored).
- `initialize` advertises only what is implemented and tested:
  `workspace/symbol`, `textDocument/hover`, and `textDocumentSync: 0` (no
  document state). Nothing else is advertised — an honest capability list is
  the product promise of this surface. (Tier 1 moves `textDocumentSync` to
  open/close/save notifications so it can publish diagnostics; see
  [lsp-tier1](features/lsp-tier1/product.md).)
- `workspace/symbol` answers with hits whose `location.uri` is the document's
  real uri (`file://…` for local sources, percent-encoded) and whose range comes
  from the chunk's own line metadata.
- `textDocument/hover` answers with the top matching chunk for the word under
  the cursor, carrying its collection, source type, freshness and relevance.
- Unsupported methods answer JSON-RPC `MethodNotFound` (-32601) — never an empty
  result that looks like "the index has nothing".

## What Tier 0 deliberately is not

- Not a type checker, no scope resolution, no completions/signature help.
- Not `definition`/`references`/`publishDiagnostics` (Tier 1), no code actions
  (Tier 2), no TCP/websocket transport.
- Not a VS Code extension: the server is client-agnostic; the client snippet in
  the docs site is the human-facing integration, so Neovim/Zed/Helix work with
  no changes.
- No document sync (`textDocumentSync: 0` in Tier 0; Tier 1 advertises
  open/close/save notifications with `change: 0`, still no content). Hover
  context is read from the file on disk, which is what keeps a sync-less server
  honest.

## Acceptance (all verified by tests)

| # | Claim | Evidence |
|---|-------|----------|
| 1 | `indexed lsp` starts, completes `initialize`, shuts down cleanly | `tests/system/test_lsp_out_of_process.py` (exit code 0 after `shutdown`/`exit`) |
| 2 | `workspace/symbol` → real file uri + range from chunk metadata | golden `tests/unit/indexed/lsp/golden/symbols.json` + system test |
| 3 | `textDocument/hover` → chunk text + collection + source type + freshness | golden `tests/unit/indexed/lsp/golden/hover.md` |
| 4 | Unsupported request → MethodNotFound, never a silent empty result | `tests/unit/indexed/lsp/test_server.py` |
| 5 | Documented with a working client snippet | indexed-web `content/docs/reference/lsp-commands.mdx` |
