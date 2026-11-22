---
type: tech
updated: 2026-11-22
applies: "src/indexed/mcp/**"
---

# MCP Server

Embedded `FastMCP` server (`src/indexed/mcp/`), decomposed into
`server.py`, `tools.py`, `resources.py`, `formatting.py`, `config.py`. Reuses the
same `SearchService` + `ConfigService` as the CLI — agent sees what the user sees.
