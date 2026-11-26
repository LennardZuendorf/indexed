---
type: tech
updated: 2026-11-26
applies: "src/indexed/mcp/**"
---

# MCP tools, resources, transports

`tools.register_tools` registers `search(query)` and
`search_collection(collection, query)`. Both resolve the **request's** workspace
scope first ([mcp-request-scope](../../features/mcp-request-scope/tech.md)) and
then call `_run_search`, which passes raw `core.engine.search` results to
`build_search_payload(raw_results, query)`. Successful searches return the
`indexed.search/1` payload below. Collection listing and status use resources,
not search tools.

## Resources

```python
@mcp.resource("resource://collections")          # the request's selected names
@mcp.resource("resource://collections/status")    # their status, definition order
@mcp.resource("resource://collection/{name}")     # status for one, if selected
```

Every tool and resource resolves scope from the client's MCP roots on each
request, so `search` and status answer for the same repository. Scope errors
(`NoRequestScopeError`, `AmbiguousRequestScopeError`,
`CollectionOutsideScopeError`) are envelopes, like every other failure.

## Transports

| Transport | Use Case | Implementation |
|-----------|----------|----------------|
| **stdio** | Claude Desktop, Cline | default, stdin/stdout |
| **http** | network access | HTTP server on port 8000 |
| **sse** | Server-Sent Events | SSE streaming |

`src/indexed/mcp/cli.py` handles transport selection.
