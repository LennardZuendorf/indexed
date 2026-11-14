---
type: feature-plan
feature: lsp-tier0
sibling: product.md
parent: ../../plan.md
updated: 2026-11-10
---

# `indexed lsp` — Tier 0 delivery plan

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

### lsp-tier0/1 — Transport and lifecycle

`indexed lsp` starts over stdio, completes `initialize` with a capability list
that contains only what is implemented, answers `shutdown`, and exits 0 after
`exit` (1 if the client never shut down). Malformed frames are answered and do
not end the session.

Evidence: `tests/unit/indexed/lsp/test_protocol.py`,
`tests/unit/indexed/lsp/test_server.py`,
`tests/system/test_lsp_out_of_process.py`.

### lsp-tier0/2 — Symbol palette with honest locations

`workspace/symbol` searches the active collections and returns
`SymbolInformation` whose `location.uri` is the document's real uri and whose
range comes from chunk metadata; the position-less path stub is never emitted.

Evidence: `tests/unit/indexed/lsp/test_results.py` + `golden/symbols.json`.

### lsp-tier0/3 — Hover with provenance

`textDocument/hover` takes the identifier at the position from the file on disk,
searches the collection that owns the file, and returns markdown with the chunk
text, collection, source type, freshness and score.

Evidence: `tests/unit/indexed/lsp/test_results.py` + `golden/hover.md`,
`test_hover_searches_only_the_owning_collection`.

### lsp-tier0/4 — Refusals are protocol-shaped

Any method the server does not implement answers `MethodNotFound` (-32601);
request-before-initialize answers -32002; after shutdown -32600; engine failures
answer -32603 and the session survives.

Evidence: `tests/unit/indexed/lsp/test_server.py`.

### lsp-tier0/5 — Documented client snippet

The docs site documents `indexed lsp`, the two capabilities and a working VS Code
`settings.json` / Neovim `nvim-lspconfig` entry.

Evidence: indexed-web `content/docs/reference/lsp-commands.mdx`, linked from the
reference index.
