---
type: hub
updated: 2026-11-22
---

# App tech spec

CLI command architecture, storage-mode, Rich UI, logging, MCP server, LSP server, search result contract (src/indexed/cli, mcp, lsp).

- [App overview](app-overview.md)
- [Entry point (`app.py`)](app-entry-point.md)
- [Version flag (`--version`)](app-version-flag.md)
- [Command groups](app-command-groups.md)
- [Coding-agent installers (`install claude-code`, `install codex`)](app-agent-installers.md)
- [Storage Mode Resolution](app-storage-mode-resolution.md)
- [Engine Selection (`--engine`)](app-engine-selection.md)
- [Rich UI Patterns](app-rich-ui-patterns.md)
- [Logging Strategy](app-logging-strategy.md)
- [MCP Server](app-mcp-server.md)
- [Freshness & error envelopes](app-mcp-freshness-errors.md)
- [MCP tools, resources, transports](app-mcp-tools-resources-transports.md)
- [LSP Server (`indexed lsp`)](app-lsp-server.md)
- [Search result contract (`indexed.search/1`)](app-search-result-contract.md)
- [Search result contract (`indexed.search/1`): Document-level facts are stated once](app-search-result-contract-document-level-facts-are-state.md)
- [The two bodies: success and failure](app-search-result-bodies.md)
- [The two bodies: success and failure: MCP has no exit code](app-search-result-bodies-mcp-has-no-exit-code.md)
- [The two bodies: success and failure (3)](app-search-result-bodies-3.md)
- [Storage Indicator Timing](app-storage-indicator-timing.md)
- [CLI Startup Time](app-cli-startup-time.md)
