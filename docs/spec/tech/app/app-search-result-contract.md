---
type: tech
updated: 2026-11-22
applies: ["src/indexed/mcp/**", src/indexed/protocols/results.py]
---

# Search result contract (`indexed.search/1`)

**Source of truth for every machine consumer:** `indexed search --json` and the MCP
tools `search` / `search_collection`. One typed contract
(`src/indexed/protocols/results.py`), one builder
(`indexed.mcp.formatting.build_search_payload`), so the two surfaces cannot drift into
lookalikes (issues #108/#109). Downstream consumers — the eval harness (#204), the
`index-use` skill text (#222) — branch on `schema`, never on the presence of a key. The
LSP server (#241) reads the engine's results directly and reuses only this contract's
locator vocabulary (`indexed.utils.provenance`), so it cannot drift into a third
provenance shape.

```json
{
  "schema": "indexed.search/1",
  "query": "how is relevance unified",
  "counts": {"documents": 1, "hits": 1},
  "collections": ["indexed-src", "notes-v2"],
  "collection_errors": [{"collection": "jira", "error": "…"}],
  "documents": [
    {
      "collection": "indexed-src",
      "source_type": "localFiles",
      "id": "src/indexed/utils/relevance.py",
      "path": "/repo/src/indexed/utils/relevance.py",
      "url": "https://…",
      "score_kind": "l2_squared",
      "hits": [
        {
          "relevance": 0.625,
          "score": 0.75,
          "locator": {"kind": "line_span", "start_line": 18, "end_line": 19},
          "text": "HIGHER_IS_BETTER = frozenset({\"cosine\", \"rerank\"})"
        }
      ]
    }
  ]
}
```

Rules the shape encodes — each one exists because the old flat payload got it wrong:
