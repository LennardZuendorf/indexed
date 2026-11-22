---
type: question
updated: 2026-11-22
---

# Stray fragments left by union merges

Open question: these lines were stranded at the end of the old tech.md by union merges. Each repeats text that lives elsewhere (the component table, the utils/protocols paragraph, the package tree, the import-graph rule). Kept verbatim; delete once a human confirms they are redundant.

| `src/indexed/cli/`, `src/indexed/mcp/` | [tech/app](../tech/app/README.md) | CLI architecture, storage-mode, Rich UI, logging, MCP server |
`src/indexed/utils/` (logging, retry, batching) is a thin shared foundation — no
separate doc; helpers are imported by every layer. `src/indexed/protocols/` (typed
contracts + connector protocols, the leaf) has no separate doc either — covered
inline below (§ Protocols Subpackage) and in [tech/core](../tech/core/README.md) / [tech/connectors](../tech/connectors/README.md).
│   └── utils/                 # Shared utilities (logging, retry, batching)
`scripts/check_imports.py`'s `cli/mcp ↛ core.v1, core.v2` rule, not merely a documented
lazily re-exported v1 config-model/utility symbols, so cli/mcp files never import
