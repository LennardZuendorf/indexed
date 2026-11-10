---
type: feature-tech
feature: lsp-tier1
sibling: product.md
parent: ../../plan.md
updated: 2026-11-10
---

# `indexed lsp` — Tier 1 (architecture)

## Modules

| File | Responsibility |
|------|----------------|
| `src/indexed/lsp/resolver.py` | The cursor→identifier→chunk path, shared by `definition` and (next) `references`: the one tokenizer, the strict `identifier_at`, the provenance-derived range or file-level fallback, the bounded location builder. |
| `src/indexed/lsp/server.py` | Dispatch: adds `textDocument/definition` to the existing handler map and `definitionProvider` to the capabilities. No second server, no second lifecycle. |
| `src/indexed/lsp/results.py` | Unchanged: LSP ranges (`lsp_range`), URIs (`document_uri`), chunk access. |
| `src/indexed/utils/provenance.py` | Unchanged: the one locator normaliser. The resolver *asks it* what a hit knows and does not re-derive the rule. |

`resolver.py` sits inside the `indexed/lsp` presentation layer and imports only
`indexed.utils.provenance` from below plus its own sibling `results.py`; nothing
below may import it (`scripts/check_imports.py`).

## One request, one bounded query

```
uri ──uri_to_path──▶ path ──identifier_at──▶ word
                                    │
                        backend.collection_for_path(path) ──▶ collection
                                    │
        backend.search(word, collection, max_docs=5, max_chunks=15)
                                    │
                     matching_locations(...) ──▶ Location[] | []
```

- The collection comes from the file's owning `manifest.reader.basePath`
  (longest prefix wins) — the same seam hover uses, so a keystroke never
  enumerates every collection.
- The identifier is read from the file on disk at the cursor's line, because the
  server still advertises `textDocumentSync: 0` and holds no document text.
- `identifier_at` is **strict**: the token under the cursor or nothing. Hover's
  forgiving `word_at` (nearest preceding word, then the line, then the file
  stem) would answer a question the user did not ask.
- A hit survives only if the identifier appears in its text as a **whole token**
  (`alpha` must not resolve to `alphabet`), after the embedder's path prefix is
  stripped, so a chunk that merely matched semantically is not called a
  definition.
- Caps: `DEFINITION_LIMIT` 5 locations, `DEFINITION_MAX_DOCS` 5,
  `DEFINITION_MAX_CHUNKS` 15. Duplicates (same uri and range) collapse.

## Degradation, derived from the locator

The resolver never inspects `start_line` itself — it asks `build_locator`, so
there is exactly one place that decides what a hit knows:

| Locator kind | Range emitted |
|---|---|
| `line_span` | the chunk's 0-based inclusive span, via `lsp_range` (end character = length of the chunk's last indexed line) |
| `page`, `headings`, `document` | the **whole document** at the target path, measured from the file (`document_range`): `0,0` → the file's own end |
| any of the above, target is not a local file | **no location** — a remote Jira/Confluence page has no text to measure, and `0,0` would point at content the index never read |

`document_range` reads the file to count lines; an unreadable or vanished file
yields no location. Symbol lists keep their `0,0` placeholder (a list row with
no position is harmless); a *definition* must not inherit it.

## Result shape

- `Location[]` when something honest resolves, `null` otherwise. LSP allows both
  and a client renders both as "no definition"; `null` is the sharper statement
  and is what the unknown-identifier case returns. Empty list is never sent —
  a caller that cannot distinguish "nothing" from "nothing found" is a caller
  that will misreport.
- No `LocationLink`: the index knows a chunk's extent, not a symbol's target
  range.

## Shared with `references`

`matching_locations` and `chunk_location` are the public seam:
`references` reuses the same identifier, the same collection scoping and the
same location builder, and only adds its own cap and plural search. It must not
grow a second lookup path, and it must keep the same "span-less → whole
document, unmeasurable → no location" rule.

## Testing

- Unit (`tests/unit/indexed/lsp/test_resolver.py`): strict cursor extraction; a
  span hit resolving to its exact range; the span-less Markdown heading case
  resolving to the document's measured extent (with and without a trailing
  newline); a remote span-less hit yielding no location; empty file;
  unknown identifier; longer-token rejection; path-stub rejection; cursor
  whitespace and unowned file short-circuiting before the engine; parameter
  errors; dedupe and cap.
- System: the existing out-of-process stdio session asserts the capability set
  verbatim, so `definitionProvider` is proven advertised by a real
  `initialize` over a pipe. The Tier 1 verification slice adds the transcript
  and golden payload for the new method.
