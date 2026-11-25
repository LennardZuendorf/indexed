---
type: tech
updated: 2026-11-25
applies: ["src/indexed/mcp/**", src/indexed/protocols/results.py]
---

# Search result contract (`indexed.search/1`): Document-level facts are stated once

- **Document-level facts are stated once.** `collection`, `source_type`, `id`, `path`,
  `url` and `score_kind` belong to the document; only `relevance`, `score`, `locator`
  and `text` repeat per hit. Repeating `collection`/`document_id`/`document_url` on
  every chunk was most of the old payload's token cost.
- **A locator is honest.** `kind` is `line_span` (1-based inclusive lines — what
  `grep -n` prints — plus the file when the document states no `path`), `page`
  (positive page metadata, when supplied), `headings` (prose:
  Markdown/Jira/Confluence/Outline) or `document` (position genuinely unknown).
  A range is never invented to fill the field. A document locator may describe
  a body fragment; it does not imply a whole-document chunk. Multiple distinct
  locator paths omit document `path` and stay on their respective hits.
  `headings` is never empty: the converters emit `headings: [""]` for whole-file
  chunks, so headings are trimmed and blank ones dropped before the kind is chosen —
  a chunk left with no headings gets `document`, not `{"kind": "headings",
  "headings": []}`.
- **`relevance` is comparable, `score` is not.** `relevance` is higher-is-better,
  normally 0–1 but not clamped (squared-L2 distances above 2 yield negatives),
  unified across engines (`indexed.utils.relevance.unified_relevance`); `score` is the
  raw engine number, only comparable within one `score_kind` (`l2_squared` = v1,
  `cosine`/`rerank` = v2).
- **Ranking is document-first.** A document's position reflects its best hit; ties keep
  discovery order (stable sort). Ranking uses full precision before four-decimal
  output rounding.
- **`source_type` is a collection fact**, taken from `manifest.reader.type`; omitted
  rather than guessed when the manifest does not say.
- **No boilerplate to strip on normal returns.** `--json` stdout is only JSON
  (logs and notices — a skipped unsearchable collection, a no-op `--rerank` — go to
  stderr). Only an exact leading `# <metadata.file_path>\n` context prefix is
  stripped when that metadata path is present; other text stays unchanged.
- **`collection_errors` means "not done as asked", not "this collection failed".**
  Success payloads always carry it. Two states share the field, told apart by
  `collections`: a **failed** collection (unreachable engine, unreadable manifest,
  no indexers) is absent from `collections` and contributes no documents; a
  collection whose requested Git option was **skipped** stays in `collections`
  with its rows present — a skipped `--changed-since` leaves them unfiltered, a
  skipped `--git-rerank` leaves them similarity-ordered, and a skipped
  `--git-provenance`/`--git-line-blame` leaves documents and hits without
  attribution (all four v2-only). Every skip is stamped by
  `gitFilter`/`gitRerank`/`gitProvenance`/`gitLineBlame` and turned into an entry
  by `mcp/formatting.py`. Entries
  are per request-not-applied, so one collection may have two. CLI also retains
  skipped no-indexer statuses when other collections are searched; CLI status omits
  unreadable manifests; named MCP searches return a top-level error when status is
  unusable.
- **Machine payloads always request matched chunk content.** CLI JSON and both MCP
  tools pass `include_matched_chunks=True`, even when the search config sets it to
  false. Text and provenance are required by the fixed payload contract.
- **`--json` ignores `--compact` / `--no-content`** (they shape the human view only;
  `--simple-output`/`--json` wins). The machine payload is fixed, never flag-shaped.
