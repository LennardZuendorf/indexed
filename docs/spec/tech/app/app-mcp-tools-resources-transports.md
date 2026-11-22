---
type: tech
updated: 2026-11-22
applies: "src/indexed/mcp/**"
---

# MCP tools, resources, transports

`tools.register_tools` registers `search(query)` and
`search_collection(collection, query)`. Both call `_run_search`, which passes raw
`core.engine.search` results to `build_search_payload(raw_results, query)`.
Successful searches return the `indexed.search/1` payload below. Collection listing
and status use resources, not search tools.

## Resources

```python
@mcp.resource("resource://collections")          # list of names
@mcp.resource("resource://collections/status")    # status for all
@mcp.resource("resource://collection/{name}")     # status for one
```

## Transports

| Transport | Use Case | Implementation |
|-----------|----------|----------------|
| **stdio** | Claude Desktop, Cline | default, stdin/stdout |
| **http** | network access | HTTP server on port 8000 |
| **sse** | Server-Sent Events | SSE streaming |

`src/indexed/mcp/cli.py` handles transport selection.
