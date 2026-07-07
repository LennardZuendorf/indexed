---
type: feature-plan
feature: foundation
sibling: tech.md
parent: ../../plan.md
updated: 2026-07-07
---

# Feature: Foundation — Implementation Plan

Nine units. A characterization/behavior test harness (foundation/1) ships first
and gates every refactor; then five parallel bug batches (foundation/2–6) repair
the reproduced recall, durability, security, connector, and honesty defects on
the current tree; then the two structural pieces the v2 seam needs — typed
contracts (foundation/7) and the facade + composition boundary (foundation/8) —
followed by the read-mostly config architecture (foundation/9). All work happens
in the current 7-package layout; the on-disk collection format is the
compatibility boundary and is never changed. Each unit leaves the suite green
and the CLI/MCP usable.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Starts now. Feature `simplify` starts when this feature is
`DONE` — the harness, typed contracts, and facade must exist so that `simplify`'s
deletions and workspace collapse happen against correct, tested, stable
contracts.

---

## Problem Frame

The engine is ~3k LOC of sound machinery, but the audit
([tech-bugfixes.md](tech-bugfixes.md) — the 2026-07-06 deep hunt) found the
search data path silently truncates most content, a deletions-only update
orphans on-disk FAISS vectors, `config set null` truncates `config.toml` to zero
bytes, secrets leak into TOML, missing collections crash with tracebacks, and
the "contracts" between layers are untyped dicts and a protocol no caller uses.
None of these can be safely refactored without first getting the test suite to
the right altitude, so foundation/1 both **adds** a coarse behavior net (green
characterization + red bug-specs) and **prunes** the brittle mechanism tests
that would fight the refactor without catching regressions — then gates every
subsequent unit. Bug batches run before the structural work so their diffs stay
small and bisectable (and they turn the red bug-specs green); typed contracts and
the facade come last because they touch the widest surface and the net must
already prove behavior is preserved. The chunker contract is co-designed across foundation/2 (behavioral
fix) and foundation/7 (typed model) — the fix ships first, the model finalizes it.

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Typed data contracts](product.md#requirement-typed-data-contracts) | foundation/7 |
| R2 | [Core swap seam](product.md#requirement-core-swap-seam) | foundation/8 |
| R3 | [Read-mostly configuration](product.md#requirement-read-mostly-configuration) | foundation/4 (secret routing), foundation/9 (overlay + resolution) |
| R4 | [Search recall correctness](product.md#requirement-search-recall-correctness) | foundation/2 |
| R5 | [Storage durability](product.md#requirement-storage-durability) | foundation/3 |
| R6 | [Connector fidelity](product.md#requirement-connector-fidelity) | foundation/4 (url-guard), foundation/5 |
| R7 | [Honest CLI and MCP behavior](product.md#requirement-honest-cli-and-mcp-behavior) | foundation/6 |
| — | Enabling harness (all requirements) | foundation/1 |

Every unit cites the R-IDs it satisfies. foundation/1 is an enabling unit for
R1–R7: it does not itself satisfy a requirement but is the gate that lets every
other unit prove it does.

---

## Key Technical Decisions

1. **Get the suite to the right altitude first — ADD then PRUNE.** foundation/1
   does two things before any fix or refactor, in this order: (a) **add** a
   coarse behavior net (create→search→update→inspect→remove per source, MCP
   smoke, config round-trip) plus red bug-specs for the known defects; (b)
   **prune** the brittle mechanism tests the net now covers — the
   import-structure / registry-membership / call-shape tests that will break en
   masse on the typed-contract, facade, and (later) collapse work without
   catching a real regression. Order is load-bearing: prune only what the net
   already covers, never prune-first (that leaves a blind coverage hole). It is a
   dependency of all of foundation/2–9; a refactor unit is not startable until
   the net covers the behavior it touches. This is what makes the rest bisectable
   instead of drowned in mechanism-test noise.
2. **The net is two distinct kinds of test.** *Characterization* tests pin
   current **correct** behavior and stay green through every refactor (the net
   proper). *Red bug-specs* assert the **desired** behavior of the known defects
   (large-doc fully searchable, delete-then-search consistent, `config set null`
   safe) — they are red the moment they're written and turn green as
   foundation/2–6 land. This prevents the classic trap of "characterizing" the
   buggy behavior and locking it in, and makes the same harness serve as both the
   refactor net and the bug-fix regression suite.
3. **Architecture in the current 7-package layout** (user decision 2026-07-06).
   Typed contracts (foundation/7) and the facade + composition module
   (foundation/8) land in today's `packages/*` / `apps/indexed` coordinates. The
   workspace collapse to a single package is deferred to Feature `simplify` — the
   accepted cost is that this architecture lands in old coordinates and then
   moves, mitigated by `git mv` + the harness in `simplify`.
4. **Two required injected callables replace the `| None` soup.** The four
   injected `Callable | None` params with runtime `missing_wiring_error` guards
   (`documents_collection_creator` DI, per research.md § Rotten foundations #5)
   collapse to two **required** callables passed by the composition module. No
   optional wiring, no runtime "must be injected by the app layer" guard on the
   happy path.
5. **Disk format is the compatibility boundary, not Python APIs.** Typed models
   round-trip today's camelCase collection JSON byte-stable; existing collections
   never re-index. This is what makes a v2 engine a drop-in behind the same
   facade over the same on-disk format.
6. **Bug batches are parallel and independently verifiable.** foundation/2–6
   each carry their own regression tests (they turn the red bug-specs from
   foundation/1 green) and can be worked in any order once foundation/1 lands;
   none depends on another.

---

## Unit IDs

Units are `foundation/n` — assigned once and never renumbered. Cite in commits
and tests, e.g. `fix(core): foundation/3 persist faiss on deletions-only`.

---

### foundation/1 — Test altitude: behavior net + prune brittle mechanism tests

**Goal:** Get the suite to the right altitude *before* any fix or refactor.
Two ordered moves: **(a) ADD** a coarse behavior net — green characterization
tests (assert current CORRECT behavior, stay green through every refactor) plus
red bug-specs (assert DESIRED behavior of the known defects, red until
foundation/2–6 fix them). **(b) PRUNE** the brittle mechanism tests the net now
covers — the ones that would break en masse on the contract/facade/collapse work
without catching a real regression. Prune ONLY what the net covers; never
prune-first. This is the safety net *and* the bug-fix regression suite, and it
stops mechanism-test noise from drowning real breaks in units 2–9.

**Requirements:** R1–R7 (enabling)

**Dependencies:** —

**Files:**

```
tests/characterization/**            # new/grow: behavior-asserting E2E net (green)
tests/characterization/test_known_bugs.py  # new: red bug-specs (turn green in 2–6)
tests/system/**                      # grow: MCP stdio smoke, config round-trip
tests/conftest.py                    # shared fixtures, stubbed HTTP for cloud sources
tests/unit/**                        # DELETE brittle mechanism tests the net covers
                                     #   (registry-membership test_init.py clones,
                                     #    test_core_shims.py, protocol-stub tests,
                                     #    import-structure/call-shape assertions)
```

**Test scenarios (the green net):**

- Per source, a full lifecycle: create → search (assert a known document is the
  top hit, not just "no error") → incremental update → inspect → remove. Files
  runs against a real temp corpus; jira/confluence/outline run against stubbed
  HTTP at the `read_documents` boundary (FAISS/embeddings run for real on small
  fixtures).
- One MCP stdio smoke: server starts, a `search` tool call returns results for a
  seeded collection.
- One `config get`/`set` round-trip through the real store.

**Red bug-specs (must exist, must be RED on landing):** large document is fully
searchable (not truncated at 256 tokens); delete-then-search leaves no orphaned
FAISS ids (no `KeyError`); `config set <k> null` leaves `config.toml` intact;
secret set routes to `.env` not TOML; missing collection → clean error + non-zero
exit; markup-injection query does not crash. Each maps to a foundation/2–6 fix.

**Prune criterion:** delete a mechanism test only when a green net test asserts
the same observable behavior; if nothing covers it and it looks real, keep it
(it becomes a net test instead). Deletion of tests paired with dead *code* is NOT
in scope here — that happens with the code in `simplify`.

**Verification:** `uv run pytest -q tests/characterization tests/system` — net
green (prove by temporarily breaking a lifecycle step); `test_known_bugs.py` runs
RED (the count of red specs equals the known-bug count, documented in the commit);
full `uv run pytest -q` still green after the mechanism-test prune (no coverage
hole). Use `tmp_path`; never touch real `~/.indexed/`.

---

### foundation/2 — Search recall fixes

**Goal:** Make the whole document searchable — token-aware chunking that honors
the embedder's real window, correct byte-offset slicing, a plaintext splitter,
`max_docs` honored with backfill, and a correctly-scaled `score_threshold`.

**Requirements:** R4

**Dependencies:** foundation/1

**Files:**

```
packages/indexed-parsing/src/parsing/plaintext_parser.py         # :48 max_tokens dropped; :138 splits only on \n\n
packages/indexed-parsing/src/parsing/docling_parser.py           # :61 HierarchicalChunker drops max_tokens/include_metadata
packages/indexed-parsing/src/parsing/code_chunker.py             # :115-117,148 slice decoded str with byte offsets
packages/indexed-core/src/core/v1/engine/indexes/embeddings/sentence_embeder.py   # honor max_seq_length (256); no 2× window
packages/indexed-core/src/core/v1/engine/core/documents_collection_searcher.py    # :41 fetch decoupled from max_docs
packages/indexed-core/src/core/v1/engine/services/search_service.py               # :228-231 max_chunks; :273-284 filter-then-truncate → backfill; :156 threshold scale
packages/indexed-core/src/core/v1/config_models.py               # :106 score_threshold ge/le/description for squared-L2 [0,4]
```

**Test scenarios:**

- A multi-thousand-token, headingless document: text near its end is in its own
  chunk within the token window and is returned as a hit (bugs #1,#3,#4).
- A CSV/JSON/log body with no blank lines chunks into multiple embeddable pieces,
  not one truncated chunk (#3).
- A non-ASCII source file chunks to correct, non-empty slices (#2, byte-offset).
- Four documents match a query where one is chunk-heavy: `max_docs` distinct docs
  are returned, not one (#5); `score_threshold` at a sane value (>1.0) is
  configurable and filters in the correct direction (#6).

**Verification:** `uv run pytest -q` green with the new recall regressions;
reproduce the pre-fix "1 of 4 returned" and large-doc-truncation cases now
passing.

---

### foundation/3 — Durability fixes

**Goal:** Never let on-disk state get destroyed or diverge — persist FAISS on
every mutation, guard zero-chunk batches, write config atomically with
pre-validation, and build a new collection aside so a failed create can't destroy
the prior one.

**Requirements:** R5

**Dependencies:** foundation/1

**Files:**

```
packages/indexed-core/src/core/v1/engine/core/documents_collection_creator.py    # :158-169 deletions-only + :408 __remove_explicit_deletions must save_faiss_index (only :371 does today); :77 delete-before-build
packages/indexed-core/src/core/v1/engine/indexes/embeddings/sentence_embeder.py   # :44-58 np.vstack([]) zero-chunk guard
packages/indexed-core/src/core/v1/engine/indexes/indexers/faiss_indexer.py        # :26 encode([]) unpack guard
packages/indexed-config/src/indexed_config/store.py                               # :358 write opens "w" then dump raises on None → atomic tmp→fsync→rename, reject unserializable BEFORE touching file
packages/indexed-core/src/core/v1/engine/persisters/disk_persister.py             # reuse its tmp→fsync→os.replace pattern for safe-create swap
```

**Test scenarios:**

- Deletions-only incremental update then a query whose neighbors hit the removed
  doc's former vectors: on-disk FAISS and mapping agree — no `KeyError`, no
  whole-collection error (#7, the delete-then-search consistency scenario).
- A zero-chunk batch (empty-body doc) does not crash embed or index (#9).
- `config set <key> null` (or any unserializable value): value rejected before
  the file is opened, `sha256(config.toml)` unchanged (#8).
- Create that fails mid-run against an existing collection name: the prior
  collection is intact afterward.

**Verification:** `uv run pytest -q` green; `sha256(config.toml)` stable across a
failing `config set`; crash-injection create test leaves prior collection intact.

---

### foundation/4 — Security fixes

**Goal:** Keep secrets out of TOML and off the console, stop baking env overrides
into saved config, and close the credential-guard parser differential.

**Requirements:** R3 (secret routing), R6 (url-guard)

**Dependencies:** foundation/1

**Files:**

```
apps/indexed/src/indexed/config/cli.py                       # :1533,:1557 secret written+echoed to TOML; :1020 inspect prints unmasked; apply existing _is_sensitive_key → .env
packages/indexed-config/src/indexed_config/service.py        # :183 stop round-tripping INDEXED__* env overrides into save_raw
packages/indexed-config/src/indexed_config/env_writer.py     # :20 quote .env values (` #` truncation / ${...} interpolation)
packages/indexed-connectors/src/connectors/_url_guard.py     # is_same_origin urlsplit vs requests/urllib3 authority differential
```

**Test scenarios:**

- `config set` on a secret field routes to `.env`, never writes plaintext to
  TOML, and is not echoed in the summary; `config inspect` masks it (#11).
- An env-supplied `INDEXED__*` secret is not baked into TOML by a later
  unrelated `set` (#11).
- A `https://evil.com\@good.com/...`-style URL: the guard resolves the same
  authority the HTTP client will use and refuses to attach credentials
  off-origin; a legitimate trailing-dot FQDN is still allowed (#12).
- A `.env` token containing ` #` or `${...}` survives a dotenv reload intact
  (#31).

**Verification:** `uv run pytest -q` green; grep/regression proving no secret
value appears in TOML or console output after a secret `set`; url-guard
differential test.

---

### foundation/5 — Connector fidelity fixes

**Goal:** Stop losing attachment content, reverted-edit changes, non-ASCII
filenames, and ADF/storage-format leaf text.

**Requirements:** R6

**Dependencies:** foundation/1

**Files:**

```
packages/indexed-connectors/src/connectors/jira/async_jira_cloud_reader.py                 # :185,:227 follow_redirects=True; don't raise_for_status on 3xx to media/S3
packages/indexed-connectors/src/connectors/confluence/async_confluence_cloud_reader.py     # same redirect/attachment fix
packages/indexed-connectors/src/connectors/files/change_tracker.py                         # :141-220 compare stored content hashes (catch reverted edits); :237-316 unquote git C-quoted non-ASCII paths
packages/indexed-connectors/src/connectors/jira/unified_jira_document_converter.py         # :122-190 keep mention/inlineCard/media/emoji/date/status leaf text
packages/indexed-connectors/src/connectors/confluence/unified_confluence_document_converter.py  # :119 keep ac:link/ac:image titles & filenames
```

**Test scenarios:**

- A Cloud attachment whose download 302-redirects to a media host is followed and
  indexed against a stubbed 302 (#13).
- A file edited then reverted in the working tree is re-indexed (hash compare),
  and a C-quoted non-ASCII filename is tracked (#14).
- An ADF payload with a `mention`/`inlineCard`/`media` node retains that text
  (assignee, link URL) after conversion; a Confluence `ac:link`/`ac:image` keeps
  its title/filename (#15).

**Verification:** `uv run pytest -q` green; converter unit tests asserting leaf
text is present; stubbed-302 attachment test indexes content.

---

### foundation/6 — Honest CLI/MCP behavior

**Goal:** Fail loud on missing/corrupt collections, survive markup injection,
honor log flags, stop persisting create overrides pre-success, invalidate the
MCP cache, surface per-collection errors, and wire up the dead config sections.

**Requirements:** R7

**Dependencies:** foundation/1

**Files:**

```
packages/indexed-core/src/core/v1/engine/services/inspect_service.py   # :204-220 omit (not zero-fill) missing/corrupt collections
apps/indexed/src/indexed/knowledge/commands/search.py                  # :423 coll_status.indexers[0] IndexError; :400,:184-187,:211 escape Rich markup on query/content
apps/indexed/src/indexed/knowledge/commands/update.py                  # :366,:414 don't break the loop; set non-zero exit on failure
apps/indexed/src/indexed/utils/components/cards.py                     # :38 escape/disable markup on content strings
apps/indexed/src/indexed/app.py                                        # :370-371 error print markup + typer.Exit outside click runner → mapped exit code
apps/indexed/src/indexed/utils/logging.py                              # setup_root_logger(None) resets to WARNING, clobbers --verbose/--log-level (research logger.py:361)
apps/indexed/src/indexed/knowledge/commands/_create_helpers.py         # :137 don't persist overrides before/regardless of success
apps/indexed/src/indexed/knowledge/commands/create.py                  # :205 empty files-path → CWD; :58 trailing-slash/whitespace cloud misroute; normalize/validate paths
apps/indexed/src/indexed/utils/storage_info.py                         # :100 storage.mode indicator vs real resolver
apps/indexed/src/indexed/mcp/server.py                                 # :56 ResponseCachingMiddleware ~1h stale; relax/invalidate
apps/indexed/src/indexed/mcp/formatting.py                             # :27 per-collection failure swallowed as "0 matches"
apps/indexed/src/indexed/mcp/{tools.py,resources.py}                   # tools.py:45, resources.py:57,75,96 catch broad exceptions → envelope
apps/indexed/src/indexed/bootstrap.py                                  # :28 storage registered as core.v1.vector_store vs CLI core.v1.storage; batch size 64 vs config 128
apps/indexed/src/indexed/config/cli.py                                 # :295 section mismatch; CLI ignores [core.v1.search]; dead indexing/embedding/storage sections
```

**Test scenarios:**

- `search`/`update`/`inspect` on a nonexistent or corrupt collection: documented
  "not found"-class error and non-zero exit — no raw `IndexError`, no success
  exit; a corrupt manifest among many does not crash the whole run (#19,#22).
- Query or indexed content containing `[/...]`/`arr[i]` renders without a
  `MarkupError` and without silently dropping the text (#23).
- `--verbose`/`--log-level`/`INDEXED_LOG_LEVEL` actually change log output (#24).
- A failed `create files -p /bad` leaves no `path` override in config; empty
  files-path is rejected rather than indexing CWD; a trailing-slash Cloud URL
  routes to Cloud (#25,#26,#27).
- `index update` across collections continues past a failure and exits non-zero
  (#28).
- MCP `search` after a CLI re-index returns fresh results, and a corrupt
  collection yields the error envelope surfacing the failure rather than "0
  matches" (#17,#18); every raised exception becomes an envelope.
- A `config set` to a previously-dead section (e.g. `[core.v1.search]`, storage)
  is actually read by the code path it names (#20).

**Verification:** `uv run pytest -q` green; subprocess exit-code test for
missing-collection and handled-error paths; MCP smoke asserting envelope +
freshness; grep/regression proving no dead config section remains settable-but-unread.

---

### foundation/7 — Typed contracts

**Goal:** Introduce `models.py` (Manifest / ConvertedDocument / Chunk /
SearchResult / SourceConfig / progress) and a corrected `protocols.py`, wire them
through creator/searcher/services, and finalize the chunker contract from
foundation/2 — with camelCase round-trip tests proving byte-stability.

**Requirements:** R1

**Dependencies:** foundation/1, foundation/2

**Files:**

```
packages/indexed-protocols/src/protocols/models.py       # typed Manifest/ConvertedDocument/Chunk/SearchResult/SourceConfig/progress
packages/indexed-protocols/src/protocols/connectors.py   # declare get_number_of_documents/read_all_documents/get_reader_details/convert (drop fictional read_documents-only DocumentReader)
packages/indexed-core/src/core/v1/engine/services/models.py                       # align/annotate; break engine→services upward import (research #4, creator :28)
packages/indexed-core/src/core/v1/engine/core/documents_collection_creator.py     # :202,:225,:500 typed against protocol methods
packages/indexed-core/src/core/v1/engine/services/search_service.py               # :369 typed SearchResult (not Dict[str,Any] results/matchedChunks)
packages/indexed-connectors/src/connectors/*/connector.py                         # conform readers to corrected protocol
```

**Test scenarios:**

- Manifest fixtures from all four sources round-trip byte-stable through the
  typed model (camelCase preserved) — existing collections keep working.
- `isinstance(reader, DocumentReader)` (and mypy) holds for every shipped reader,
  and the engine is typed against only protocol methods (#3, protocol fiction).
- mypy on the touched core + `models.py` + `protocols.py` adds 0 new errors.

**Verification:** `uv run pytest -q` green; `uv run mypy` clean on the typed
island; byte-stable round-trip assertion for all four sources; a deliberate
contract mismatch produces a mypy error.

---

### foundation/8 — Facade + composition + boundaries

**Goal:** Expose one core facade, replace the scattered wiring with a single
composition module, let connectors own their manifests, collapse the DI soup to
two required callables, and enforce the layer edges with an import check.

**Requirements:** R2

**Dependencies:** foundation/1, foundation/7

**Files:**

```
packages/indexed-core/src/core/v1/engine/services/collection_service.py           # facade: create/update/search/inspect/remove; :111 drop lazy cycle import
packages/indexed-core/src/core/v1/engine/factories/update_collection_factory.py   # :87 remove if connector_type == "localFiles" branch
packages/indexed-core/src/core/v1/engine/services/search_service.py               # :244 remove localFiles branch
apps/indexed/src/indexed/composition.py                                           # NEW: replaces bootstrap.py + connector_wiring.py + runtime.py
apps/indexed/src/indexed/bootstrap.py                                             # folded into composition
apps/indexed/src/indexed/connector_wiring.py                                      # :124-145 camelCase manifest keys, :227-231 private reaches, :164 os.environ channel — deleted
apps/indexed/src/indexed/runtime.py                                               # resolve_collections_context(reset=True) incoherence folded in
packages/indexed-connectors/src/connectors/*/connector.py                         # from_manifest(...) per source
scripts/check_import_graph.py                                                     # slim import check: core⊥connectors, core⊥app, connectors⊥core
```

**Test scenarios:**

- `update` works identically for all four sources via `from_manifest`, with the
  files source keeping deletions + change-tracker state saving, and core carrying
  no per-connector `if/elif` and no `localFiles` string branch.
- The two injected callables are required (no `| None`, no
  `missing_wiring_error` on the happy path); composition is the only wiring site.
- The import check fails when a forbidden edge is added (negative test); passes on
  the real tree.
- A stand-in engine behind the same facade over the same disk format serves an
  existing collection unchanged (drop-in scenario).

**Verification:** `uv run pytest -q` green; `python scripts/check_import_graph.py`
passes on the tree and fails on an injected forbidden import; characterization
lifecycle green through the facade for all four sources.

---

### foundation/9 — Read-mostly config architecture

**Goal:** Make runtime config an in-memory overlay, unify path/mode resolution to
one home, and replace the self-replacing singleton and the second module-level
singleton with a cached `get_config()`/`reload()`.

**Requirements:** R3

**Dependencies:** foundation/1

**Files:**

```
packages/indexed-config/src/indexed_config/service.py    # :72-79 conditional self-replacement singleton → cached get_config()/reload(); in-memory override overlay
packages/indexed-config/src/indexed_config/store.py       # :322 stop persisting runtime overrides; overlay reads only
packages/indexed-config/src/indexed_config/storage.py     # consolidate has_local_config
packages/indexed-config/src/indexed_config/path_utils.py  # single path/mode source of truth (vs TomlStore/StorageResolver triplication, research #9)
packages/indexed-config/src/indexed_config/workspace.py   # unify with resolver
packages/indexed-core/src/core/v1/engine/services/search_service.py   # :301 remove second module-level singleton
apps/indexed/src/indexed/bootstrap.py                     # register_app_config runs in 3 places (research #10) → once via overlay
```

**Test scenarios:**

- `index update` on a jira/confluence/outline fixture leaves `config.toml`
  byte-identical (overrides + dated query stay in the overlay), while the
  incremental cutoff still applies to the constructed request.
- Path/mode resolution matrix (flag / workspace pref / `.indexed` present /
  default) is unchanged — reuse existing behavior tests against the single
  resolver.
- `get_config()` returns the cached instance; `reload()` re-reads; no code
  re-parses TOML per call.

**Verification:** `uv run pytest -q` green; `sha256(config.toml)` before/after an
`update` is stable; resolution-matrix tests pass against the consolidated home.

---

## Dependencies

| Unit | Blocks | Blocked by |
|---|---|---|
| foundation/1 | 2, 3, 4, 5, 6, 7, 8, 9 | — |
| foundation/2 | 7 | foundation/1 |
| foundation/3 | — | foundation/1 |
| foundation/4 | — | foundation/1 |
| foundation/5 | — | foundation/1 |
| foundation/6 | — | foundation/1 |
| foundation/7 | 8 | foundation/1, foundation/2 |
| foundation/8 | — | foundation/1, foundation/7 |
| foundation/9 | — | foundation/1 |

foundation/1 gates all. foundation/2–6 (the bug batches) are independent of each
other and may run in parallel. foundation/7 needs the chunker contract from
foundation/2; foundation/8 needs the typed contracts from foundation/7.
foundation/9 is independent after foundation/1.

---

## Progress

| Unit | Status |
|---|---|
| foundation/1 | DONE |
| foundation/2 | DONE |
| foundation/3 | DONE |
| foundation/4 | DONE |
| foundation/5 | DONE |
| foundation/6 | DONE |
| foundation/7 | NOT STARTED |
| foundation/8 | NOT STARTED |
| foundation/9 | NOT STARTED |
