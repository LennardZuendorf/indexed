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
| `src/indexed/lsp/resolver.py` | The cursor→identifier→chunk path, shared by `definition` and `references`: the one tokenizer, the strict `identifier_at`, the provenance-derived range or file-level fallback, the bounded location builder, and one private `_lookup` the two public resolvers differ only in bounds within. |
| `src/indexed/lsp/server.py` | Dispatch: adds `textDocument/definition` and `textDocument/references` to the existing handler map and `definitionProvider`/`referencesProvider` to the capabilities. No second server, no second lifecycle. |
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
        backend.search(word, collection, max_docs=..., max_chunks=...)
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
  `DEFINITION_MAX_CHUNKS` 15 — and, for the plural method,
  `REFERENCES_LIMIT` 50, `REFERENCES_MAX_DOCS` 10, `REFERENCES_MAX_CHUNKS` 40
  (see below). Duplicates (same uri and range) collapse.

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

## `references`: the same path, plural

`resolve_references` and `resolve_definitions` are the same private `_lookup` —
same `identifier_at`, same `collection_for_path`, same `matching_locations` —
differing only in bounds and in what the protocol wants back:

| | `definition` | `references` |
|---|---|---|
| locations cap | `DEFINITION_LIMIT` 5 | `REFERENCES_LIMIT` 50 |
| docs per query | `DEFINITION_MAX_DOCS` 5 | `REFERENCES_MAX_DOCS` 10 |
| chunks per query | `DEFINITION_MAX_CHUNKS` 15 | `REFERENCES_MAX_CHUNKS` 40 |
| empty answer | `null` | `[]` |

**Bounded, not complete.** A reference list is wider than a definition shortlist
but it is still one keyed query against the owning collection and its best
chunks — a bounded *semantic* answer, never an exhaustive scan of the corpus. A
use site outside the engine's top hits is not found, and no location is invented
to make the answer look complete. That is the documented cap the product page
promises; there is no LSP field for "partial", so the honesty lives in the
bounds and the docs rather than in a fabricated `Location`.

`includeDeclaration` is accepted and ignored: chunks carry no declaration bit,
so filtering on it would be a lie either way; returning the declaration among
the references is the honest half.

## Result shape

- `Location[]` when something honest resolves, `null` otherwise. LSP allows both
  and a client renders both as "no definition"; `null` is the sharper statement
  and is what the unknown-identifier case returns. Empty list is never sent —
  a caller that cannot distinguish "nothing" from "nothing found" is a caller
  that will misreport.
- `textDocument/references` returns `Location[]` **always** — `[]` when nothing
  matches, because LSP reads `null` there as a protocol violation while `null`
  is the sharper "nothing defines this" for `definition`. One method's empty
  answer is a statement, the other's is a shape.
- No `LocationLink`: the index knows a chunk's extent, not a symbol's target
  range.

## Shared with `references`

`references` is that same `_lookup`: same identifier, same collection scoping,
same location builder, its own bounds. It did not grow a second lookup path, and
it kept the same "span-less → whole document, unmeasurable → no location" rule —
`resolve_references` exists so the *difference* between the two methods is a
table in one file, not two implementations.

## Testing

- Unit (`tests/unit/indexed/lsp/test_resolver.py`): strict cursor extraction; a
  span hit resolving to its exact range; the span-less Markdown heading case
  resolving to the document's measured extent (with and without a trailing
  newline); a remote span-less hit yielding no location; empty file;
  unknown identifier; longer-token rejection; path-stub rejection; cursor
  whitespace and unowned file short-circuiting before the engine; parameter
  errors; dedupe and cap. For `references`: hits across files all returned in
  engine order, a semantic neighbour (`alphabet`) excluded, the span-less
  Markdown hit degraded to the whole document, the default `REFERENCES_LIMIT`
  enforced against `REFERENCES_LIMIT + 2` hits, `[]` (never `null`) for an empty
  answer, parameter rejection, and the search bounds asserted verbatim so a
  future edit cannot quietly widen the query.
- System: the existing out-of-process stdio session asserts the capability set
  verbatim, so `definitionProvider` and `referencesProvider` are proven
  advertised by a real `initialize` over a pipe. The Tier 1 verification slice
  adds the transcript and golden payload for the new methods.
