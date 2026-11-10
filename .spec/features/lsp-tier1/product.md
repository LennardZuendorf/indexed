---
type: feature-product
feature: lsp-tier1
sibling: tech.md
parent: ../../plan.md
updated: 2026-11-10
---

# `indexed lsp` — Tier 1 (product)

**Issue:** [#241](https://github.com/LennardZuendorf/indexed/issues/241)
**Plan:** [plan.md](plan.md) · **Architecture:** [tech.md](tech.md)

## Why

Tier 0 made the index *visible* in the editor: a symbol palette that searches
the knowledge base and a hover that says what the index knows about the file
under the cursor. Visible is not navigable. Tier 1 makes it navigable — jump to
where a thing is defined, then (in the next slices) find where else the index
has seen it, and let the editor surface what the index thinks of the open file.

The promise does not change between tiers: **every answer is a fact the index
actually holds.** Tier 0 already degrades honestly rather than inventing a
position; Tier 1 keeps that rule on a surface where inventing one is much
easier, because "go to definition" is a feature people expect to always work.

## What `textDocument/definition` is

- Resolves the identifier under the cursor to the indexed chunks that define
  it, and answers with real `Location`s: the chunk's own indexed line span in
  the defining file.
- When the source has **no line span** (Markdown, Jira, Confluence, Outline —
  the index knows the document, not the line), it answers with a range covering
  that whole document, measured from the file. It never answers with a guessed
  line and column.
- When there is nothing honest to point at — an unknown identifier, a cursor in
  whitespace, a file no collection owns, a remote document whose text the server
  cannot read — it answers `null`. No empty hover-style shrug dressed up as a
  result.
- It is **one keyed, bounded query** against the collection that owns the file,
  so holding "go to definition" down cannot re-scan the store.

## What `textDocument/references` is

- Answers with the locations the index holds for the identifier under the
  cursor: every chunk the engine returns for that name that literally contains
  it as a whole token, across the files of the owning collection.
- **Bounded on purpose** — at most 50 locations, from one keyed query capped at
  10 documents and 40 chunks. Holding "find references" down cannot turn into a
  scan of the store, and the answer is the engine's best matches, not a claim to
  have enumerated every use in the corpus.
- Same degradation as `definition`: a span-less source resolves to the whole
  document, and a document the server cannot read yields no location at all.
- `[]` when nothing is found — an empty reference list is a list, not `null`.

## What Tier 1 is not

- Not a symbol table. There is no scope resolution and no type information, so a
  use site can outrank a declaration; the result is the engine's best
  chunk-level match that literally contains the identifier.
- No `LocationLink` (`originSelectionRange`/`targetSelectionRange`): there is no
  target symbol range to report, only the chunk's indexed extent.
- No code actions, no document sync, no TCP transport (unchanged from Tier 0).
- Not a completeness claim for `references`: it will answer with a documented
  cap and say so, rather than pretend to have enumerated every use.

## Acceptance

| # | Claim | Evidence |
|---|-------|----------|
| 1 | Identifier with a line span → the chunk's exact indexed range | `tests/unit/indexed/lsp/test_resolver.py` |
| 2 | Span-less source → range covering the whole document, never a fabricated position | `tests/unit/indexed/lsp/test_resolver.py` |
| 3 | Unknown identifier / unowned file / cursor off an identifier → `null`, and no engine call where nothing is resolvable | `tests/unit/indexed/lsp/test_resolver.py` |
| 4 | Definition is advertised only because it is implemented; other methods still `MethodNotFound` | `initialize` capabilities + `tests/system/test_lsp_out_of_process.py` |
| 5 | Out-of-process stdio transcript and golden payload | verification slice of Tier 1 (own card) |
| 6 | References across files: every whole-token hit in engine order, semantic neighbours (`alphabet`) excluded | `tests/unit/indexed/lsp/test_resolver.py` |
| 7 | A reference in a span-less source degrades to the whole document, never a fabricated position | `tests/unit/indexed/lsp/test_resolver.py` |
| 8 | The result cap is enforced (50) and the query stays one keyed search at its documented bounds | `tests/unit/indexed/lsp/test_resolver.py` |
| 9 | No references returns `[]`, not `null`; bad params return `-32602` | `tests/unit/indexed/lsp/test_resolver.py` |
