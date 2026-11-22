---
type: tech
updated: 2026-11-22
applies: "src/indexed/**"
---

# Dependency Direction

```text
┌──────────────────────────────────────────────────────┐
│  CLI / MCP (src/indexed/cli/, src/indexed/mcp/)      │  ← UI only, thin commands
│  May import: core (facade), connectors.registry,     │
│  config, protocols, utils                            │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Core Engine (src/indexed/core/)                     │  ← Business logic
│  May import: protocols, config, utils                │
│  MUST NOT import: CLI, MCP, concrete connectors      │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Connectors (src/indexed/connectors/)                │  ← Data source adapters
│  May import: protocols, config, utils, parsing       │
│  MUST NOT import: core engine, CLI, MCP              │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Config, Utils, Parsing, Protocols (infrastructure)  │  ← Shared foundation
│  MUST NOT import: anything above                     │
└──────────────────────────────────────────────────────┘
```

- Dependencies flow **downward only** — never import from a higher layer
- Core engine receives connectors via **dependency injection**, never imports concrete implementations
- Protocols/interfaces live in the lowest layer that needs them
- Circular dependency → extract the shared interface into a lower package
