---
type: tech
updated: 2026-11-26
applies: "src/indexed/mcp/**"
---

# MCP Server

Embedded `FastMCP` server (`src/indexed/mcp/`), decomposed into
`server.py`, `tools.py`, `resources.py`, `formatting.py`, `config.py`,
`scope.py`. Reuses the same `SearchService` + `ConfigService` as the CLI — agent
sees what the user sees.

One process serves many clients, so **scope is per request**: every tool call and
resource read resolves the client's MCP roots to one committed `indexed.toml`
(`mcp/scope.py`) and serves exactly that selection from the global store.
Requests with no roots, no definition, or conflicting definitions fail closed
with a named error envelope. See
[features/mcp-request-scope](../features/mcp-request-scope/tech.md).

The lifespan's `CliContext` is **not** the request scope; it is resolved once at
startup for the watcher's root only.
