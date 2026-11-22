---
type: tech
updated: 2026-11-22
applies: "src/indexed/lsp/**"
---

# LSP Server (`indexed lsp`)

`src/indexed/lsp/` is a fourth presentation surface (peer of `cli`/`mcp`),
served by `indexed lsp` over stdio. Tier 0 scope: `workspace/symbol` and
`textDocument/hover`, nothing else. Full detail:
[features/lsp-tier0/tech.md](../../features/lsp-tier0/tech.md).

- **Framing is LSP's, not MCP's**: `Content-Length: N\r\n\r\n<utf-8 json>`
  (`lsp/protocol.py`); the MCP stdio transport is newline-delimited and cannot
  be reused. stdout belongs to the protocol — log records go to stderr.
- **Capabilities are the contract**: `initialize` advertises
  `textDocumentSync: 0`, `hoverProvider`, `workspaceSymbolProvider` and nothing
  else. (Tier 1 replaces `textDocumentSync: 0` with open/close/save
  notifications and adds `definitionProvider`/`referencesProvider` plus pushed
  diagnostics — see [features/lsp-tier1/tech.md](../../features/lsp-tier1/tech.md).)
  Anything unimplemented answers `MethodNotFound` (-32601).
- **One provenance normaliser**: `utils/provenance.py::build_locator` is the
  only locator builder — `mcp/formatting.py` (the `indexed.search/1` payload)
  and `lsp/results.py` both use it, so no surface can drift into a second
  shape. LSP ranges are 0-based; the locator's line spans are 1-based
  inclusive over 0-based chunk metadata.
- **Cost discipline**: status is cached (2 s TTL) and hover searches only the
  collection whose `manifest.reader.basePath` owns the file — no full-store
  scan per keystroke (issue #126).
- **Layer rule**: `lsp` is an "up" layer in `scripts/check_imports.py` — it may
  use only the core facade, and nothing below may import it.
