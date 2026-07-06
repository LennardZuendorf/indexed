---
type: feature-tech
feature: foundation
sibling: product.md
parent: ../../tech.md
updated: 2026-07-06
---

# Feature: Foundation — Bug Catalogue (full audit detail)

The complete, buildable list of every correctness defect found in the 2026-07-06
deep hunt (5 agents + reproduction pass). Each bug is anchored to `file:line`,
tagged with severity + confidence, and paired with a concrete fix approach and
the behavior assertion that proves it fixed. Bugs are grouped to match the
foundation fix units so an implementer can pick up a unit and work top-to-bottom.

**Overview:** [tech.md](tech.md)
**Requirements:** [product.md](product.md)

**Parent:** [../../tech.md](../../tech.md)

## Legend

**Severity** — `CORRUPT` (bad data written / index desync) · `LOSS` (user data or
content destroyed / dropped) · `LEAK` (secret exposure) · `WRONG` (incorrect
result, no crash) · `CRASH` (traceback / abort).
**Confidence** — `CONFIRMED` (read at line and/or reproduced with `uv run`) ·
`PLAUSIBLE` (read, not yet reproduced end-to-end).

## Unit → group → requirement map

| Group | Fix unit | Requirement | Theme |
|---|---|---|---|
| A — Search recall | [foundation/2](plan.md) | [R4](product.md#requirement-search-recall-correctness) | chunking, top-k, threshold |
| B — Durability | foundation/3 | [R5](product.md#requirement-storage-durability) | persist / atomic writes / safe create |
| C — Security & secrets | foundation/4 | [R3](product.md#requirement-read-mostly-configuration) / [R6](product.md#requirement-connector-fidelity) | secret routing, url-guard, `.env` |
| D — Connector fidelity | foundation/5 | [R6](product.md#requirement-connector-fidelity) | attachments, change-tracking, ADF/storage |
| E — Honest CLI/MCP | foundation/6 | [R7](product.md#requirement-honest-cli-and-mcp-behavior) | failure paths, markup, logging, caching |
| F — Reporting (minor) | foundation/6 | [R7](product.md#requirement-honest-cli-and-mcp-behavior) | counts, timestamps, config sections |

---

## Group A — Search recall correctness → foundation/2 (R4)

The data path silently truncates and starves results — the defects here strike
the core value proposition (search returns partial or missing content).

### A1 — Chunker ignores `max_tokens`; headingless bodies become one truncated chunk

- **Symptom:** Any large document without markdown headings is embedded as a
  single chunk; everything past ~256 tokens is silently unsearchable.
- **Root cause:** `plaintext_parser.py:48` and `docling_parser.py:61` construct
  `HierarchicalChunker(max_tokens=..., include_metadata=True)`, but
  `HierarchicalChunker` has **no** `max_tokens`/`include_metadata` fields (its
  fields are `delim, serializer_provider, code_chunking_strategy,
  always_emit_headings, merge_list_items`). Pydantic silently drops both kwargs.
  It splits only on headings, so a headingless body of any size is one chunk.
  MiniLM `max_seq_length=256` then truncates it at embed. The docstring claims a
  token-aware `HybridChunker`; the code uses `HierarchicalChunker`.
- **Severity/Confidence:** CORRUPT / CONFIRMED.
- **Fix approach:** Switch to a token-aware chunker (docling `HybridChunker` with
  a real tokenizer/`max_tokens`, or a post-split that enforces the embedder's
  `max_seq_length`). Wire the embedder's actual token window (see A4) into the
  chunker contract so `max_tokens ≤ max_seq_length`. This chunker contract is
  finalized in foundation/7.
- **Regression test:** Chunk a 5,000-token headingless plaintext doc; assert
  `len(chunks) > 1` and every chunk's tokenized length `≤ max_seq_length`.
  Assert content from the final 10% of the document is retrievable by search.

### A2 — Code chunker slices decoded `str` with tree-sitter **byte** offsets

- **Symptom:** Source files containing any non-ASCII byte (comments, string
  literals, identifiers) produce wrong or empty code chunks from that point on.
- **Root cause:** `code_chunker.py:115-117,148` — `read_bytes()` → `decode()` →
  `source[child.start_byte:child.end_byte]`. tree-sitter offsets are **byte**
  positions; slicing a decoded `str` with them mis-aligns by one position per
  multibyte char, shifting every later slice.
- **Severity/Confidence:** CORRUPT / CONFIRMED (reproduced).
- **Fix approach:** Slice the **bytes** buffer with the byte offsets, then
  `.decode()` each chunk — `source_bytes[start:end].decode("utf-8")`. Keep a
  single `source_bytes` and never index the decoded string with byte offsets.
- **Regression test:** Chunk a Python file whose first function contains a
  non-ASCII comment (e.g. `# café`); assert the second function's chunk text
  equals its true source (byte-exact), not a shifted slice.

### A3 — Plaintext splitter only breaks on `\n\n`

- **Symptom:** CSV/JSON/YAML/log/XML files with no blank lines collapse to one
  chunk → truncated at 256 tokens; most of the file is unsearchable.
- **Root cause:** `plaintext_parser.py:138` splits generic text solely on the
  `\n\n` (blank-line) delimiter. Formats without paragraph breaks never split.
- **Severity/Confidence:** CORRUPT / CONFIRMED (reproduced).
- **Fix approach:** Replace the `\n\n`-only splitter with a token-budget splitter
  that falls back to single newlines / character windows when no blank line
  exists, capped at the embedder window (shared with A1's token-aware path).
- **Regression test:** Chunk a 2,000-line log file (no blank lines); assert
  multiple chunks and each within the token window; assert a line near EOF is a
  search hit.

### A4 — Chunk window is 2× the model window (no embed-time guard)

- **Symptom:** Even when chunking works, chunks target ~512 tokens while the
  model window is 256 — the back half of every full chunk is unsearchable; two
  texts identical in their first 256 tokens embed to distance 0.
- **Root cause:** Chunkers target `max_tokens≈512`; `max_seq_length=256`; there
  is no guard in `sentence_embeder.py` reconciling the two.
- **Severity/Confidence:** WRONG / CONFIRMED.
- **Fix approach:** Make the embedder expose `max_seq_length` and have the
  chunker derive `max_tokens` from it (single source of truth). Optionally assert
  at embed time that no input exceeds the window (log/split rather than truncate).
- **Regression test:** Two docs sharing an identical 256-token prefix but
  differing suffixes must embed to **non-zero** distance; assert the suffix is
  a distinguishing search hit.

### A5 — Top-k starvation + filter-after-truncate

- **Symptom:** A single many-chunk document (any code file) fills the neighbor
  list and starves other matching docs; searches return fewer than `max_docs`
  results with no backfill. Reproduced: 4 matching docs → 1 returned.
- **Root cause:** `documents_collection_searcher.py:41` fetches exactly
  `max_chunks (= max_docs*3)` FAISS neighbors, then
  `search_service.py:228-231` derives documents from them — chunks from one doc
  crowd out others. `_filter_by_score` runs **after** the `max_docs` truncation
  (`search_service.py:273-284`), so score-filtered slots are never backfilled.
- **Severity/Confidence:** WRONG / CONFIRMED (reproduced).
- **Fix approach:** Decouple `max_chunks` from `max_docs` (fetch a larger neighbor
  pool, dedup to documents, then take `max_docs`); apply `_filter_by_score`
  **before** the `max_docs` truncation and backfill from the remaining ranked
  pool until `max_docs` distinct docs are collected or the pool is exhausted.
- **Regression test:** Index 4 docs each matching a query, one of them large
  (many chunks); assert exactly 4 distinct docs returned when `max_docs≥4`.
  With a score filter that removes rank-1, assert rank-5 backfills the slot.

### A6 — `score_threshold` wrong scale + direction + cap + description

- **Symptom:** Sane thresholds (>1.0) are unconfigurable; the config description
  is inverted; the service docstring's own `1.5` example fails validation.
- **Root cause:** `config_models.py:106` declares `ge=0, le=1.0` with the label
  "Minimum similarity", but the engine keeps `squared-L2 <= threshold` over range
  `[0,4]` where **lower is better** (`search_service.py:156`). The scale, the
  direction, and the `le=1.0` cap are all wrong. (The package CLAUDE.md's "raw L2"
  is also wrong — it is *squared* L2.)
- **Severity/Confidence:** WRONG / CONFIRMED.
- **Fix approach:** Fix the field bounds to the real range (`ge=0, le=4.0`, or
  normalize to a cosine-similarity scale and convert internally), rewrite the
  description to state "max squared-L2 distance, lower = more similar", and update
  the docstring example to a valid value. Correct the CLAUDE.md/spec note to
  "squared L2".
- **Regression test:** A threshold of `1.5` validates and filters correctly
  (keeps hits with squared-L2 ≤ 1.5); assert the field rejects negatives and
  accepts values in `[0,4]`.

---

## Group B — Storage durability → foundation/3 (R5)

Data-destroying and index-desync defects. The collections persister is atomic
(tmp→fsync→rename); these paths bypass or predate it.

### B1 — Deletions-only update never persists `indexer.faiss`

- **Symptom:** After a deletions-only update, on-disk FAISS vectors outlive their
  mapping keys. The next query whose top-k hits an orphan raises `KeyError` in the
  searcher → the whole collection returns an error, permanently (the post-run hook
  saves ChangeTracker state, so it never self-heals).
- **Root cause:** `save_faiss_index` is only called inside
  `__add_documents_to_index` (`documents_collection_creator.py:371`). The
  deletions-only branch (`documents_collection_creator.py:158-169`) and
  `__remove_explicit_deletions` (`:408`) mutate the in-memory index + mapping
  JSONs but never write the FAISS file to disk.
- **Severity/Confidence:** CORRUPT / CONFIRMED (reproduced end-to-end).
- **Fix approach:** Call `save_faiss_index` (through the atomic persister) on
  **every** mutating branch — the deletions-only path and
  `__remove_explicit_deletions` — so the on-disk index and mapping JSONs commit
  together. Consider a single `__persist_index()` helper invoked by all branches.
- **Regression test:** Create a collection, run a deletions-only update, reload
  from disk, and search a query whose neighbors included a deleted doc; assert no
  `KeyError` and that deleted content is absent from results.

### B2 — Zero-chunk batch crashes both embed paths

- **Symptom:** Indexing a source that yields only empty-body documents (e.g.
  Outline empty pages) crashes; in `create` it fires **after** the collection
  folder was already deleted (see B4), destroying the prior collection.
- **Root cause:** `sentence_embeder.py:44-58` calls `np.vstack([])` on an empty
  list; `encode([])` returns shape `(0,)` which `faiss_indexer.py:26` fails to
  unpack.
- **Severity/Confidence:** CRASH / CONFIRMED.
- **Fix approach:** Guard the empty case in both the embedder (`embed_batch`
  returns an empty `(0, dim)` array instead of `vstack([])`) and the FAISS indexer
  (no-op on zero vectors). Skip index add when there are no chunks.
- **Regression test:** Create/update a collection whose documents all have empty
  bodies; assert it completes without traceback and produces an empty-but-valid
  index (searchable, 0 chunks).

### B3 — `config set <key> null` truncates `config.toml` to 0 bytes

- **Symptom:** `indexed config set some.key null` destroys the entire config file
  (including credential pointers). Reproduced.
- **Root cause:** `config/cli.py:114` `_coerce_value` maps `"null"`→`None`;
  `TomlStore.write` opens the target in `"w"` (truncate) **then** `tomlkit.dump`
  raises on the `None` value (`store.py:358-359`) — the file is already truncated
  when the dump fails. The write is non-atomic (unlike the collections persister).
- **Severity/Confidence:** LOSS / CONFIRMED (reproduced).
- **Fix approach:** Make `TomlStore.write` atomic (serialize to a tmp file →
  fsync → `os.replace`) and **validate/serialize before touching the target** so
  an unserializable value raises before any write. Reject `None`/unserializable
  values in `config set` with a clear error (or map `null` to key deletion,
  explicitly).
- **Regression test:** `config set` with an unserializable value leaves the
  original `config.toml` byte-identical (assert file unchanged) and exits
  non-zero with a clear message.

### B4 — `create` deletes the existing collection before rebuilding

- **Symptom:** A failed re-create (bad path, zero-chunk crash, network error)
  loses the prior collection even though the persister is atomic.
- **Root cause:** `documents_collection_creator.py:77` deletes the collection
  folder up front, before the new index is built.
- **Severity/Confidence:** LOSS / CONFIRMED.
- **Fix approach:** Build the new collection **aside** (temp directory) and swap
  it in by `os.replace`/rename only on success; never delete the existing
  collection until the replacement is durable on disk.
- **Regression test:** Force a create failure over an existing collection (inject
  a zero-chunk/embed error); assert the original collection is intact and
  searchable afterward.

### B5 — Non-transactional 4-file index commit

- **Symptom:** A crash between writing `manifest.json`, `documents.json`,
  `chunks.json`, and `index.faiss` leaves a collection whose four files disagree
  (counts/mappings out of sync), producing wrong results or `KeyError`.
- **Root cause:** Each file is persisted independently; there is no single commit
  boundary spanning the four artifacts (`documents_collection_creator.py` persist
  paths; `disk_persister.py` is atomic per-file but not per-collection).
- **Severity/Confidence:** CORRUPT / PLAUSIBLE.
- **Fix approach:** Stage all four files in a temp collection dir and swap the
  directory in by a single rename (aligns with B4's build-aside approach), so a
  collection is either fully the old version or fully the new one.
- **Regression test:** Interrupt a persist after 2 of 4 files (simulate); assert
  the on-disk collection still loads as the pre-write version (no mixed state).

---

## Group C — Security & secrets → foundation/4 (R3 secret / R6 url-guard)

### C1 — `config set` on a secret writes plaintext TOML, echoes it, and `inspect` shows it unmasked

- **Symptom:** Setting a secret (token/password) writes it in cleartext into
  `config.toml`, prints it in the summary card, and `config inspect` displays it
  unmasked.
- **Root cause:** `config/cli.py:1533` (write), `:1557` (echo), `:1020`
  (inspect print). `_is_sensitive_key` exists but is **never applied** on any of
  these paths.
- **Severity/Confidence:** LEAK / CONFIRMED.
- **Fix approach:** Route sensitive keys through `EnvFileWriter` (`.env`, never
  TOML); mask the value in the summary card and in `config inspect`
  (`****`/last-4). Gate all three call sites on `_is_sensitive_key`.
- **Regression test:** `config set jira.token secret123` writes nothing to
  `config.toml`, writes `.env`, and `config inspect` shows a masked value;
  assert `secret123` never appears in stdout or TOML.

### C2 — `INDEXED__*` env secrets baked into `save_raw`

- **Symptom:** An env-supplied secret (`INDEXED__jira__token=...`) is round-tripped
  into `config.toml` by **any** later unrelated `config set`, persisting a secret
  that was intentionally kept out of the file.
- **Root cause:** `service.py:183` merges env overrides into the dict that
  `save_raw` writes, so `set` re-serializes env values into TOML.
- **Severity/Confidence:** LEAK / CONFIRMED.
- **Fix approach:** Keep env overrides as an **in-memory overlay only** (R3);
  `set` must persist the on-disk baseline plus the single changed key, never the
  merged env layer. Strip `INDEXED__*`-sourced values before `save_raw`.
- **Regression test:** With `INDEXED__jira__token` set in env, run
  `config set core.v1.search.max_docs 10`; assert the token is absent from the
  written `config.toml`.

### C3 — `_url_guard` parser differential (credential leak to attacker host)

- **Symptom:** `https://evil.com\@good.com/…` — `is_same_origin` sees host
  `good.com` and approves, but `requests`/urllib3 parse the authority differently
  and send the Bearer/basic credentials to `evil.com`. Also rejects legitimate
  trailing-dot FQDNs.
- **Root cause:** `_url_guard.py:52-53` uses `urllib.parse.urlsplit`, whose
  authority parsing differs from the HTTP client's (`requests`/urllib3) — a parser
  differential the guard doesn't account for.
- **Severity/Confidence:** LEAK / CONFIRMED (reproduced).
- **Fix approach:** Parse the authority the same way the HTTP client does — reuse
  `requests.utils`/`urllib3.util.url.parse_url` (or validate that the host
  contains no `\`, `@`, or embedded credentials and normalize trailing dots)
  before comparing origins. Fail closed on any parse disagreement.
- **Regression test:** `is_same_origin("https://evil.com\\@good.com/x",
  "https://good.com")` returns `False`; a legitimate `https://good.com.` FQDN
  compared to `https://good.com` matches (or both fail closed consistently).

### C4 — `.env` writer stores secrets unquoted

- **Symptom:** Tokens containing ` #` are truncated on the next dotenv reload;
  tokens containing `${...}` are interpolated — both corrupt the credential,
  producing a confusing 401 on later runs.
- **Root cause:** `env_writer.py:20` writes `KEY=value` with no quoting/escaping.
- **Severity/Confidence:** LOSS / CONFIRMED (mechanics reproduced).
- **Fix approach:** Quote values (single-quote or escape per dotenv rules) so
  `#`, `$`, spaces, and newlines survive a reload. Round-trip through the same
  dotenv parser the app loads with.
- **Regression test:** Write a token containing ` #x` and `${y}`, reload via the
  app's dotenv path, assert the value is byte-identical.

---

## Group D — Connector fidelity → foundation/5 (R6)

### D1 — Jira/Confluence Cloud attachments always skipped

- **Symptom:** Attachment content is never indexed — the async client fails on the
  302 redirect to the media/S3 host.
- **Root cause:** `async_jira_cloud_reader.py:185` lacks `follow_redirects`, and
  `raise_for_status()` at `:227` raises on the 302. The Confluence async reader
  has the same shape.
- **Severity/Confidence:** LOSS / CONFIRMED (Jira); PLAUSIBLE (Confluence).
- **Fix approach:** Enable `follow_redirects=True` on the async client (or handle
  the 3xx explicitly) and do **not** `raise_for_status()` on redirect codes for
  attachment fetches. NOTE (per Learnings): media is served off-origin from a CDN,
  so the `_url_guard` origin check must be **selectively excluded** for these
  attachment downloads or the guard silently drops them all.
- **Regression test:** Stub a Jira attachment endpoint returning 302→media host;
  assert the reader downloads the body and the attachment text is in a chunk.

### D2 — git change-tracker misses reverted edits + mangles non-ASCII names

- **Symptom:** A file edited then reverted in the working tree is never
  re-indexed (stays stale forever); files with non-ASCII names are never
  re-indexed.
- **Root cause:** `change_tracker.py:141-220` compares git-vs-HEAD and never the
  **stored content hashes**, so a revert (working tree == HEAD) is invisible.
  `:237-316` reads git's C-quoted path output without **unquoting**, so
  non-ASCII/whitespace filenames don't match real paths.
- **Severity/Confidence:** LOSS / CONFIRMED.
- **Fix approach:** Compare against the **stored** content hashes from the prior
  run (not git HEAD) so any content change — including a revert to a previously
  indexed state that differs from the stored snapshot — is detected. Unquote git's
  C-style quoted paths (or use `-z`/`core.quotepath=false`) before matching.
- **Regression test:** Edit + revert a tracked file → assert it is re-scanned and
  its stored hash matches; add a file named `café.py` → assert it is detected and
  indexed.

### D3 — ADF leaf nodes dropped from Jira text

- **Symptom:** Assignees, mention names, and link URLs vanish from indexed Jira
  content.
- **Root cause:** `unified_jira_document_converter.py:122-190` `_parse_adf_nodes`
  walks `content` children only; `mention`, `inlineCard`, `media`, `emoji`,
  `date`, `status` carry their data in `attrs`, not `content`, so they are dropped.
- **Severity/Confidence:** WRONG / CONFIRMED.
- **Fix approach:** In `_parse_adf_nodes`, extract text from the `attrs` of leaf
  node types (`mention.text`/`id`, `inlineCard.url`, `media`/`emoji`/`date`/
  `status` attributes) so their content contributes to the chunk text.
- **Regression test:** Convert an ADF doc containing a `mention` and an
  `inlineCard`; assert the mention display name and the card URL appear in the
  output text.

### D4 — Confluence `ac:link`/`ac:image` titles & filenames dropped

- **Symptom:** Confluence link titles and image filenames are missing from
  indexed content.
- **Root cause:** `unified_confluence_document_converter.py:119` — storage-format
  `ac:link`/`ac:image` leaf nodes' titles/filenames are not extracted.
- **Severity/Confidence:** WRONG / CONFIRMED.
- **Fix approach:** Extend the storage-format walker to pull `ri:*` attributes /
  link body titles and image filenames into the text (mirror D3 for the storage
  format).
- **Regression test:** Convert storage XML with an `ac:image`/`ri:attachment`;
  assert the filename appears in a chunk.

### D5 — Empty stored query → malformed leading-`AND` JQL/CQL

- **Symptom:** An incremental update on a collection created with an empty
  query builds `AND updated >= ...`, which the Jira/Confluence API rejects.
- **Root cause:** `connector_wiring.py:49,62` prepends the incremental clause with
  a leading `AND` without checking whether the stored base query is empty.
- **Severity/Confidence:** WRONG / PLAUSIBLE (empty-query collections only).
- **Fix approach:** Build the query by joining non-empty clauses with `AND`
  (skip the connector prefix when the base query is empty) rather than string
  concatenation.
- **Regression test:** Incremental update with an empty base query produces a
  valid JQL/CQL string (no leading `AND`).

---

## Group E — Honest CLI & MCP behavior → foundation/6 (R7)

### E1 — Missing/corrupt-collection guards are dead code

- **Symptom:** `search -c nonexistent` → raw `IndexError` traceback (even in
  `--simple-output`); `update nonexistent` → misleading message with **exit 0**;
  a single corrupt manifest crashes a default multi-collection `search` wholesale.
- **Root cause:** `InspectService` returns a zero-filled **placeholder** status
  for unreadable/missing collections (`inspect_service.py:204-220`), so the
  `if not statuses` guards never fire. `search.py:423` then does
  `coll_status.indexers[0]` → `IndexError`.
- **Severity/Confidence:** CRASH/LIE / CONFIRMED.
- **Fix approach:** `InspectService` must **omit** missing/unreadable collections
  (or return an explicit error status), not zero-fill. Callers detect the empty/
  error result and raise a documented CLI error with a **non-zero exit**; never a
  traceback, never exit 0.
- **Regression test:** `search -c nonexistent` exits non-zero with a clear
  message (no traceback); `update nonexistent` exits non-zero; a corrupt manifest
  in one of N collections doesn't crash the others.

### E2 — Rich markup injection from query and indexed content

- **Symptom:** Searching content containing `[/...]` crashes with `MarkupError`
  (reproduced); `arr[i]`/`dict[key]` in content is silently swallowed in the
  display — the common case for a code-search tool.
- **Root cause:** Query and indexed document content are interpolated into Rich
  markup f-strings: `search.py:400,184-187,211`, `cards.py:38`, error print
  `app.py:370`.
- **Severity/Confidence:** CRASH/WRONG / CONFIRMED (crash reproduced).
- **Fix approach:** Escape user/content strings with `rich.markup.escape` (or pass
  as non-markup `Text`) at every interpolation site; never build markup from
  untrusted content.
- **Regression test:** Render a search result whose content contains `[/bold]`
  and `arr[i]`; assert no exception and both substrings appear verbatim.

### E3 — `--verbose`/`--log-level`/`INDEXED_LOG_LEVEL` reset to WARNING

- **Symptom:** Verbose/debug flags are silently ignored by every knowledge
  command; the themed console + file log are dropped.
- **Root cause:** Each knowledge command calls `setup_root_logger(None)` →
  `bootstrap_logging("WARNING")` (`logger.py:361`), clobbering the callback's
  resolved level.
- **Severity/Confidence:** LIE / CONFIRMED (reproduced).
- **Fix approach:** Resolve the log level once in the app callback and thread it
  (or read the already-resolved level) instead of re-bootstrapping to WARNING.
  Stop calling `setup_root_logger(None)` inside commands. (Ties to the known
  `is_verbose_mode()` unreliability lesson.)
- **Regression test:** `search --verbose` (and `INDEXED_LOG_LEVEL=DEBUG`) emit
  debug/info log lines; assert level ≤ INFO is active during the command.

### E4 — `create` persists CLI overrides + prompted values before success

- **Symptom:** A failed `create files -p /bad` leaves `path="/bad"` in
  `config.toml`; the next create silently reuses it → cross-collection
  contamination for path/url/query.
- **Root cause:** `_create_helpers.py:137` and `create.py:239,453,701` write
  overrides/prompted values to `config.toml` **before** (and regardless of)
  success.
- **Severity/Confidence:** LOSS/WRONG / CONFIRMED (reproduced).
- **Fix approach:** Never persist runtime overrides to `config.toml` (R3 —
  overrides are an in-memory overlay). Pass them through the create call in
  memory; store per-collection source config in the manifest, not global config.
- **Regression test:** A failed create leaves `config.toml` unchanged; a
  subsequent create with no path does **not** inherit the failed path.

### E5 — Empty files-path prompt indexes the CWD

- **Symptom:** Pressing Enter at the files-path prompt indexes the entire current
  working directory.
- **Root cause:** `create.py:205` accepts empty input, persists `path=""`, and
  `Path("") == Path(".")` passes validation → whole CWD indexed. (jira/confluence
  error on empty URL; outline defaults — four commands, four behaviors.)
- **Severity/Confidence:** WRONG / CONFIRMED (reproduced).
- **Fix approach:** Reject empty path input with a re-prompt/validation error;
  normalize + validate the path (see E7) before use. Unify empty-input handling
  across the four create commands.
- **Regression test:** Empty files-path input is rejected (non-zero / re-prompt);
  assert the CWD is never indexed.

### E6 — Cloud/Server misroute on trailing slash/whitespace

- **Symptom:** `https://x.atlassian.net/` (trailing slash) is treated as Server →
  wrong config class + wrong credential scheme → auth fails with no hint.
- **Root cause:** `create.py:58` tests `url.endswith(".atlassian.net")` without
  `.strip()`/normalization.
- **Severity/Confidence:** WRONG / CONFIRMED.
- **Fix approach:** Strip whitespace and normalize the URL (drop trailing slash,
  lowercase host) before the Cloud/Server detection; detect on the parsed host,
  not a raw `endswith`.
- **Regression test:** `https://x.atlassian.net/ ` (trailing slash + space)
  routes to Cloud; assert the Cloud config class + credential scheme are chosen.

### E7 — Files source path stored unnormalized

- **Symptom:** `update` from a different CWD errors or indexes the wrong
  directory because the manifest stored a relative / `~`-unexpanded path.
- **Root cause:** `files_document_reader.py:143` stores the path without
  `expanduser()`/`resolve()`.
- **Severity/Confidence:** WRONG / CONFIRMED.
- **Fix approach:** `Path(p).expanduser().resolve()` before storing in the
  manifest; single normalization helper shared with E5.
- **Regression test:** Create with `~/docs` or a relative path, `cd` elsewhere,
  `update`; assert it reads the originally intended absolute directory.

### E8 — `update` (all) aborts the whole loop; single failures exit 0

- **Symptom:** One collection failing during `update` (all) leaves every later
  collection stale and unlisted; a single failure is counted as "all up to date"
  with **exit 0**.
- **Root cause:** `update.py:366,414` `break` on first failure; the `continue`
  path returns exit 0.
- **Severity/Confidence:** WRONG / CONFIRMED.
- **Fix approach:** Continue the loop on per-collection failure (collect errors),
  report each, and set a **non-zero** exit code if any collection failed.
- **Regression test:** `update` over 3 collections where #1 fails; assert #2 and
  #3 are still updated and the process exits non-zero.

### E9 — MCP serves ~1h-stale results (response caching, no invalidation)

- **Symptom:** After a CLI re-index, MCP tool/resource responses continue serving
  the old results for up to an hour; cached error envelopes too.
- **Root cause:** `mcp/server.py:56` adds `ResponseCachingMiddleware()` with
  default (~1h) TTL and no invalidation on re-index.
- **Severity/Confidence:** WRONG / CONFIRMED.
- **Fix approach:** Remove or tightly bound the caching middleware (short TTL,
  and/or invalidate on collection mtime change); never cache error envelopes.
  Simplest correct fix: drop `ResponseCachingMiddleware` (searcher cache already
  provides the latency win).
- **Regression test:** Re-index a collection between two MCP `search` calls;
  assert the second call reflects the new content.

### E10 — Per-collection search failures silently swallowed (MCP)

- **Symptom:** An agent sees "0 matches" instead of "index failed" when a
  collection errors.
- **Root cause:** `mcp/formatting.py:27` `format_search_results_for_llm`
  `continue`s past a failed collection without surfacing the error.
- **Severity/Confidence:** WRONG / CONFIRMED.
- **Fix approach:** Include an explicit per-collection error entry in the LLM
  envelope (name + error) instead of `continue`; distinguish "no matches" from
  "collection failed".
- **Regression test:** One of two collections raises during search; assert the
  MCP response reports the failure for that collection, not silent 0-matches.

### E11 — Nonexistent collection → all-zeros healthy status via MCP

- **Symptom:** MCP resource returns a healthy zero-filled status for a collection
  that doesn't exist; CLI `search -c nonexistent` raw-`IndexError`s (same root as
  E1).
- **Root cause:** `inspect_service.py:204` returns the zero-filled placeholder;
  the guard never fires. CLI `search.py:423` `coll_status.indexers[0]`.
- **Severity/Confidence:** WRONG/CRASH / CONFIRMED.
- **Fix approach:** Same as E1 — omit/error missing collections; MCP resource
  returns an explicit not-found status, never all-zeros-healthy.
- **Regression test:** MCP `resource://collections/{missing}` returns a not-found/
  error status, not a zeroed healthy record.

### E12 — Dead / mis-registered config sections

- **Symptom:** Setting `core.v1.indexing/embedding/storage` keys has no effect;
  `[core.v1.storage]` keys are silently ignored; the same query returns different
  results from CLI vs MCP.
- **Root cause:** `core.v1.indexing/embedding/storage` are registered, settable,
  and templated but read nowhere (model comes from the indexer name; batch size
  is hardcoded 64 vs config 128). `[core.v1.storage]` is registered under the key
  `core.v1.vector_store` (`bootstrap.py:28` vs `config/cli.py:295`), so
  `storage.*` keys never bind. CLI search ignores `[core.v1.search]` entirely
  (only MCP reads it).
- **Severity/Confidence:** WRONG / CONFIRMED.
- **Fix approach:** Reconcile the registration key (`core.v1.storage` ↔
  `vector_store`) so settable keys actually bind; read the registered batch
  size/model instead of hardcoding; have the CLI search read `[core.v1.search]`
  so CLI and MCP behave identically. Delete truly-dead sections (or wire them).
- **Regression test:** `config set core.v1.search.max_docs 3` changes CLI search
  result count; `config set` on the storage section actually binds; CLI and MCP
  return the same results for the same query/config.

---

## Group F — Reporting (minor, still wrong) → foundation/6 (R7)

| ID | Bug | Symptom | Root cause `file:line` | Sev/Conf | Fix approach |
|---|---|---|---|---|---|
| F1 | Vector count shown as bytes | `inspect` reports the chunk count formatted as a byte size | `get_size()`→`index_size_bytes`→`format_size`, `inspect_service.py:277` | WRONG / CONFIRMED | Report count as a count; keep a separate real byte size for the index file. |
| F2 | `createdTime` always None | Collections show no creation time | inspect/manifest path (`inspect_service.py` reporting) | WRONG / CONFIRMED | Populate `createdTime` on create and read it back in inspect. |
| F3 | `avg_doc_size` inflated | Average doc size includes index bytes | `inspect_service.py` reporting (same block as F1) | WRONG / CONFIRMED | Compute average from document byte totals only, excluding the index. |
| F4 | `config set` destination lie | Success message names the wrong file in global mode | `config/cli.py` set summary | WRONG / CONFIRMED | Report the actual resolved target path (from the store) in the summary. |
| F5 | `_coerce_value` overreach | `"001"`→1, `"nan"`→nan | `config/cli.py:114` | WRONG / CONFIRMED | Only coerce when the schema type is numeric; preserve string-typed values verbatim. |
| F6 | Env-var mapping drift | `INDEXED__*` name↔key mapping diverges from registered specs (surfaces in F5/C2 territory) | config env mapping (`store.py:136-171` read path is correct; the write/echo side drifts) | WRONG / PLAUSIBLE | Derive the env-var name from the registered spec key in one place; test the round-trip. |

---

## Cleared — do not chase

Checked in the 2026-07-06 hunt and found **not** to be bugs. Do not re-investigate:

- **Batch-vs-single embed identical** — max diff 1.3e-7; batching does not change
  results.
- **Ranking is correct** — embeddings are unit-normalized, so squared-L2 is
  monotonic with cosine similarity; ordering matches.
- **`INDEXED__*` env overrides ARE applied** in the read path
  (`store.py:136-171`). (The *write* side leaks them — that's C2, a separate bug.)
- **No missed-change crash window** — ChangeTracker state is saved only after a
  successful run, so a crash never records an unprocessed change as done.
- **No `asyncio.run`-inside-running-loop** — MCP never calls the async readers.
- **FAISS `-1` padding skipped**, empty `remove_ids` is a no-op, mmap index
  mutate+resave works, `_safe_join` blocks `..`, cloud doc-ids don't collide,
  single-connector collections can't mix naive/aware datetimes, and the model
  cache worst case is a perf double-load — **not** a correctness bug.
