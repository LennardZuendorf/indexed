---
type: tech
updated: 2026-11-22
applies: "src/indexed/**"
---

# Package Structure

Single package, one wheel (`indexed-sh`); no workspace, no `una`:

```text
indexed/
├── src/indexed/
│   ├── cli/                  # Typer app; composition.py is the single wiring site
│   ├── mcp/                  # FastMCP server
│   ├── lsp/                  # LSP server (stdio JSON-RPC): symbol palette + hover
│   ├── core/                 # Indexing & search engine; facade in core/__init__.py
│   ├── connectors/           # Source connectors (files/jira/confluence/outline)
│   ├── config/                # Config management (ConfigService singleton)
│   ├── parsing/               # Shared parsing module (Docling, tree-sitter)
│   ├── protocols/             # Typed contracts + connector protocols — the leaf
│   └── utils/                 # Shared utilities (logging, retry, batching, provenance)
└── tests/                     # Test suite
```

**Build system:** a single `hatchling` build produces one wheel.
