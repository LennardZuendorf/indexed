---
type: feature-research
feature: right-sizing
sibling: product.md
parent: ../../tech.md
updated: 2026-07-06
---

# Feature: Right-Sizing — Research (2026-07-06 audit)

Condensed evidence base from the full-codebase architecture audit (main pass +
app-layer, packages-layer, and adversarial overengineering reviews). Numbers
verified against the tree at branch `claude/architecture-audit-review-kkeihg`.

## Size inventory (verified)

| Area | LOC | Note |
|---|---|---|
| apps/indexed src | 9,764 | 45% of all source is the "thin UI layer" |
| indexed-connectors src | 5,548 | 4 sources |
| indexed-core src | 3,020 | the actual engine |
| indexed-config src | 1,584 | reads/writes TOML + .env |
| parsing / utils / protocols | 828 / 588 / 269 | |
| tests | 25,244 | 1.17× source; 1,410 test functions |
| `.agents/` vendored skills | 12,592 | larger than core+config+connectors combined |
| `config/cli.py` alone | 1,959 | larger than the whole config package it fronts |
| `create.py` | 992 | 4 near-identical ~230-line command clones |

## Rotten foundations (must not survive into v2's base)

1. **config.toml as mutable runtime state.** `ConfigService.set()` persists to
   disk (`store.py:322` writes TOML); `bootstrap.build_connector` and
   `connector_wiring._populate_*_config` call it during create/update, writing
   CLI args and **date-stamped derived queries** into the user's config.
2. **Untyped dict contracts.** Manifest (`manifest["reader"]["type"]`),
   documents/chunks (v1 dict format), search results (`Dict[str, Any]` with
   `"results"`/`"matchedChunks"` keys) — layer purity is enforced on imports
   while the actual data contract is stringly typed.
3. **Protocol fiction.** `protocols.DocumentReader` declares only
   `read_documents()`; zero callers exist — the engine calls
   `get_number_of_documents()` / `read_all_documents()` / `get_reader_details()`
   (`documents_collection_creator.py:202,225,500`). All consumption points are
   `Any`-typed, so mypy can't see it.
4. **Engine imports upward** from `core.v1.engine.services.models`
   (`documents_collection_creator.py:28`) — the cycle that forced the lazy
   import in `collection_service.py:111` and the `_types.py` leaf module.
5. **DI callable soup.** Four injected `Callable | None` params
   (`connector_factory`, `cache_decorator_factory`, `manifest_connector_factory`,
   `local_files_update_factory`) with runtime `missing_wiring_error` guards;
   the moved logic re-couples anyway: per-connector `if/elif` + camelCase
   manifest keys in app-layer `connector_wiring.py:124-145`, private reaches
   into `connector._config/._path/._include_patterns` (lines 227-231), and an
   `os.environ` side-channel for the Outline cutoff (line 164).
6. **Core still knows connectors**: `if connector_type == "localFiles"`
   (`update_collection_factory.py:87`, `search_service.py:244`).
7. **Broken failure paths.** `app.py:371` raises `typer.Exit` outside the click
   runner → traceback + exit 1, exit-code table dead (reproduced). MCP catches
   only `IndexedError` (`resources.py:57,75,96`, `tools.py:45`) but core raises
   none → envelope unreachable.
8. **Create deletes before building** (`documents_collection_creator.py:77`):
   failed re-create loses the existing collection despite the atomic-write persister.
9. **Config path logic triplicated** (`TomlStore.has_local_config` vs
   `storage.has_local_config` vs `StorageResolver`), singleton with conditional
   self-replacement (`service.py:72-79`), plus a second module-level singleton
   in `search_service.py:301`.
10. **Composition incoherence.** `register_app_config` runs in 3 places;
    `resolve_collections_context(reset=True)` discards those registrations;
    works only because connectors self-register in `from_config`.
    `update.py:360,374` omits `collections_path`, relying on singleton side-effects.

## Dead weight (delete list)

- `SearchArgs` DTO (`search_service.py:369`) — zero usages.
- `CONFIG_REGISTRY`, `get_config_class`, `list_connector_types`
  (`connectors/registry.py`) — zero production consumers; tests only.
- Indexer registry/factory naming scheme (`indexer_registry.py` 163 +
  `indexer_factory.py` 97) — exactly one indexer exists (`faiss_indexer.py`).
- Multi-indexer lists/loops + `manifest["indexers"][0]` asymmetry;
  `indexing_batch_size=500_000` batching that never batches.
- Sync `confluence_cloud_document_reader.py` (293 LOC) — never instantiated;
  async reader borrows its static helpers only.
- `_UpdatingCollectionCreator` wrapper class; `get_raw()` alias; tautological
  `test_core_shims.py`; 4× registry-membership `test_init.py` clones;
  protocol-conformance stub tests; ~3,770 LOC of Rich component markup tests;
  632 LOC testing `migration.py` (itself one-time legacy code still shipping).
- Two parallel progress systems (`ProgressCallback` + `PhasedProgressCallback`)
  coupled by magic phase-name strings across the core/CLI boundary.

## Worth keeping (the good bones)

- Atomic disk persistence (`disk_persister.py`: tmp → fsync → `os.replace`).
- Lazy ML imports (<1s startup discipline) and searcher caching
  (`SearchService._searcher_cache`).
- `_url_guard.py` off-origin credential guard; `change_tracker.py`
  (git/hash/mtime incremental indexing — a differentiating feature).
- The reader/converter split + `BaseConnector` idea (4 sources onboarded) —
  keep the protocol, fix its methods, drop the package around it.
- `retry.py` + `batch.py`; the MCP layer's proportions (~774 LOC total);
  system/e2e/benchmark tests; static `CONNECTOR_REGISTRY` (post-audit form).

## Performance notes

- `resolve_collections_context` eagerly imports all connectors (~0.4s measured)
  for commands that never use them; `register_app_config` adds schema imports
  in the app callback. Threatens the documented <1s startup.
- Pipeline writes every converted doc to disk, then re-reads all of them to
  embed (`__read_documents` → `__add_documents_to_index`) — double I/O + parse.
- `ConfigService.get/set` re-reads and re-parses TOML per call; update wiring
  performs up to 8 sequential read-parse-write cycles.

---

## Correctness bugs — 2026-07-06 deep hunt (5 agents + verification)

These are behavioral defects, not architecture. Each **CONFIRMED** item was
read at the cited line and/or reproduced with `uv run`. This is why
right-sizing is gated by a critical-fixes unit (right-sizing/0): several strike
the core value proposition or destroy user data. Severity tags:
CORRUPT / LOSS / LEAK / WRONG / CRASH.

### The data path is broken (search silently returns partial content)

1. **CORRUPT — chunker ignores `max_tokens`.** `HierarchicalChunker` has no
   `max_tokens`/`include_metadata` field (verified: its fields are
   `delim, serializer_provider, code_chunking_strategy, always_emit_headings,
   merge_list_items`); Pydantic drops both kwargs. It splits only on headings,
   so a headingless body of any size is one chunk. MiniLM `max_seq_length` is
   256, so the chunk is truncated at embed → most of every large doc is
   unsearchable. `plaintext_parser.py:48`, `docling_parser.py:61`. (docstring
   claims token-aware `HybridChunker`; code uses `HierarchicalChunker`.)
2. **CORRUPT — code chunker slices a decoded `str` with tree-sitter byte
   offsets** (`code_chunker.py:115-117,148`): `read_bytes()` → `decode()` →
   `source[child.start_byte:child.end_byte]`. Any non-ASCII byte upstream
   shifts every later slice → wrong/empty chunks. Reproduced.
3. **CORRUPT — plaintext splitter only breaks on `\n\n`**
   (`plaintext_parser.py:138`). CSV/JSON/YAML/log/XML with no blank lines →
   one giant chunk → truncated at 256 tokens. Reproduced.
4. **WRONG — chunk window is 2× the model window** even when chunking works:
   chunkers target `max_tokens≈512`, `max_seq_length=256`, no guard in
   `sentence_embeder.py` → second half of every full chunk is unsearchable;
   two texts identical in the first 256 tokens embed to distance 0.
5. **WRONG — top-k starvation.** Searcher fetches exactly `max_chunks`
   (`=max_docs*3`) neighbors then derives docs (`documents_collection_searcher.py:41`,
   `search_service.py:228-231`); one many-chunk doc (any code file) fills top-k
   and starves other matching docs. `_filter_by_score` runs *after* the
   `max_docs` truncation (`search_service.py:273-284`) → returns fewer than
   `max_docs` with no backfill. Reproduced: 4 matching docs → 1 returned.
6. **WRONG — `score_threshold` wrong scale + direction + cap.**
   `config_models.py:106` `ge=0,le=1.0`, "Minimum similarity"; engine keeps
   `squared-L2 <= threshold` over range [0,4], lower=better
   (`search_service.py:156`). Sane thresholds (>1.0) are unconfigurable; the
   description is inverted; the service docstring's own `1.5` example fails
   validation. (Package CLAUDE.md "raw L2" is also wrong — it's squared.)

### Reproduced corruption / crash / data-loss

7. **CORRUPT — deletions-only update never persists `indexer.faiss`.**
   `save_faiss_index` is called only in `__add_documents_to_index`
   (`documents_collection_creator.py:371`); the deletions-only branch (`:158-169`)
   and `__remove_explicit_deletions` (`:408`) update in-memory index + mapping
   JSONs but not the on-disk FAISS. On-disk vectors then outlive their mapping
   keys → `KeyError` in the searcher for any query whose top-k hits an orphan →
   whole collection returns error. The post-run hook saves ChangeTracker state,
   so it never self-heals. Reproduced end-to-end.
8. **LOSS — `config set <key> null` truncates config.toml to 0 bytes.**
   `_coerce_value` maps `"null"`→`None` (`config/cli.py:114`); `TomlStore.write`
   opens `"w"` (truncate) *then* `tomlkit.dump` raises on `None`
   (`store.py:358`) → non-atomic write destroys the whole file (credentials
   pointers included). Reproduced. (The collections persister does atomic
   tmp→fsync→rename; the config writer does not.)
9. **CRASH — zero-chunk batch** crashes both embed paths
   (`sentence_embeder.py:44-58` `np.vstack([])`; `encode([])`→(0,) →
   `faiss_indexer.py:26` unpack error). Triggerable via Outline empty-body
   docs; in CREATE it fires *after* the folder was deleted.
10. **LOSS — `config update` clobbers local config with global content** and
    writes to the wrong file (`config/cli.py:1299-1310` reads global, writes via
    default-target `store.write` → local); **`config update --file` never worked**
    (`_specs` AttributeError, `config/cli.py:1387`). Both reproduced.

### Secret leaks

11. **LEAK — `config set` on a secret** writes plaintext to TOML, echoes it in
    the summary card, and `config inspect` prints it unmasked
    (`config/cli.py:1533,1557,1020`); `_is_sensitive_key` exists but is never
    applied. Env-supplied `INDEXED__*` secrets are baked into TOML by *any*
    later `set` (`service.py:183` round-trips env overrides into `save_raw`).
12. **LEAK — `_url_guard` parser differential.** `is_same_origin` uses
    `urlsplit`; the fetch uses `requests`/urllib3, which parse authority
    differently. `https://evil.com\@good.com/…` → guard sees host `good.com`
    (approves), requests sends to `evil.com` with the Bearer/basic creds.
    Reproduced. Also rejects legitimate trailing-dot FQDNs.

### Connector content loss / wrong results

13. **LOSS — Jira Cloud attachments always skipped**: async client lacks
    `follow_redirects` and `raise_for_status()` raises on the 302 to media/S3
    (`async_jira_cloud_reader.py:185,227`). Confluence async reader likely same.
14. **LOSS — git change-tracker misses reverted working-tree edits
    permanently** (compares git-vs-HEAD, never stored content hashes;
    `change_tracker.py:141-220`) and **mangles C-quoted non-ASCII filenames**
    (no unquoting; `:237-316`) → those files never re-indexed.
15. **WRONG — ADF leaf nodes dropped** from Jira text: `mention`, `inlineCard`,
    `media`, `emoji`, `date`, `status` carry data in `attrs`, not `content`, so
    `_parse_adf_nodes` drops them (`unified_jira_document_converter.py:122-190`)
    — assignees and link URLs vanish. Confluence `ac:link`/`ac:image` titles &
    filenames similarly dropped (`unified_confluence_document_converter.py:119`).
16. **WRONG — empty stored query → malformed leading-`AND` JQL/CQL** on
    incremental update (`connector_wiring.py:49,62`). PLAUSIBLE (empty-query
    collections only).

### MCP / cross-surface wrong results

17. **WRONG — MCP caches tool/resource responses ~1h** (fastmcp
    `ResponseCachingMiddleware()` defaults, `mcp/server.py:56`) with no
    invalidation from CLI re-index → stale search; cached error envelopes too.
18. **WRONG — per-collection search failures silently swallowed** by
    `format_search_results_for_llm` (`continue`, `mcp/formatting.py:27`) →
    agent sees "0 matches", not "index failed".
19. **WRONG/CRASH — nonexistent collection** → all-zeros healthy status via MCP
    resource (`inspect_service.py:204`, guard never fires); CLI
    `search -c nonexistent` → raw `IndexError` at `search.py:423`
    (`coll_status.indexers[0]`).
20. **WRONG — dead config sections.** `core.v1.indexing/embedding/storage` are
    registered, settable, and templated but read nowhere (model from indexer
    name; batch size hardcoded 64 vs config 128); `[core.v1.storage]` is
    registered as `core.v1.vector_store` so those keys are silently ignored
    (`bootstrap.py:28` vs `config/cli.py:295`). CLI search ignores
    `[core.v1.search]` entirely (only MCP reads it) → same query differs by
    surface.

### Reporting (minor, still wrong)

21. Inspect shows vector *count* as *bytes* (`get_size()`→`index_size_bytes`→
    `format_size`, `inspect_service.py:277`); `createdTime` always None;
    `avg_doc_size` inflated by index bytes; `config set` success message and
    destination lie in global mode; `_coerce_value` `"001"`→1, `"nan"`→nan.

### CLI flow bugs (all CONFIRMED, most reproduced)

22. **CRASH/LIE — missing-collection guards are dead code.** `InspectService`
    returns a zero-filled *placeholder* status for unreadable/missing collections
    (`inspect_service.py:204-220`), so `if not statuses` never fires:
    `search -c nonexistent` → raw `IndexError` (`search.py:423`, even in
    `--simple-output`); `update nonexistent` → misleading message + **exit 0**;
    default `search` crashes wholesale if any one collection's manifest is corrupt.
23. **CRASH/WRONG — Rich markup injection.** Query and *indexed document
    content* are interpolated into markup f-strings (`search.py:400,184-187,211`,
    `cards.py:38`, error print `app.py:370`). Content with `[/...]` → `MarkupError`
    crash (reproduced); `arr[i]`/`dict[key]` silently swallowed in display —
    the common case for a code-search tool.
24. **LIE — `--verbose`/`--log-level`/`INDEXED_LOG_LEVEL` silently reset to
    WARNING** by every knowledge command (`setup_root_logger(None)` →
    `bootstrap_logging("WARNING")`, `logger.py:361`), clobbering the callback
    and dropping the themed console + file log. Reproduced.
25. **LOSS/WRONG — create persists CLI overrides + prompted values to
    config.toml *before* (and regardless of) success** (`_create_helpers.py:137`,
    `create.py:239,453,701`). A failed `create files -p /bad` leaves
    `path="/bad"` in config → next create silently reuses it. Cross-collection
    contamination for path/url/query. Reproduced.
26. **WRONG — empty files-path prompt indexes the CWD.** Empty input accepted
    (`create.py:205`), persisted as `path=""`, and `Path("")==Path(".")` passes
    validation → whole cwd indexed. jira/confluence error on empty URL; outline
    defaults — four commands, four behaviors. Reproduced.
27. **WRONG — Cloud/Server misroute on trailing slash/whitespace.**
    `url.endswith(".atlassian.net")` with no `.strip()`/normalize
    (`create.py:58`); `…atlassian.net/` → treated as Server → wrong config class
    and wrong credential scheme → auth fails with no hint.
28. **WRONG — `update` (all) aborts the whole loop on first failure**
    (`break`, `update.py:366,414`) → collections after the failure stay stale,
    unlisted; single failures also `continue` with **exit 0** counted as
    "all up to date".
29. **WRONG — files source path stored unnormalized** (relative, `~`
    unexpanded) in the manifest → `update` from another CWD errors or indexes
    the wrong directory (`files_document_reader.py:143`, no `expanduser/resolve`).
30. **LIE — `init` ignores resolved mode** (`init.py:66` shows local, then
    `get_global_root()` unconditionally) — `--local init` repairs `~/.indexed`;
    and `storage.mode` config key is honored by the *indicator* but never by the
    real resolver (`storage_info.py:100` vs `workspace.py:106`) → label disagrees
    with where data is written. (The documented "config.toml storage mode" is a no-op.)
31. **LOSS — `.env` writer stores secrets unquoted** (`env_writer.py:20`):
    tokens containing ` #` (truncated) or `${…}` (interpolated) corrupt on the
    next dotenv reload → confusing 401 on later runs. Reproduced mechanics.
32. **Cache asymmetry — `remove` never clears the caches dir** (leaks read-cache
    forever) while **`create --force` wipes ALL collections' caches**
    (`collection_service.py:144,183`) → unrelated collections re-fetch from
    source next run.
33. Minor confirmed: per-collection search errors dropped in every CLI mode
    (looks like 0 matches); `--simple-output` emits Rich panels on error paths;
    `--no-fail-fast` can't override config `fail_fast=true` (falsy-override bug);
    piped runs print progress to stdout; `--limit` ignored by the card view;
    `remove` help says "one or more" but takes one; `docs` claims success on
    headless; `conflict_prompt.py`/`set_preference` unreachable; `update/search/
    remove/inspect` lack the `--local` flag `create` has.

### Cleared (checked, NOT bugs — do not re-chase)

- Batch-vs-single embed identical (max diff 1.3e-7); ranking correct
  (embeddings are unit-normalized, squared-L2 monotonic with cosine).
- `INDEXED__*` env overrides ARE applied in the read path (`store.py:136-171`).
- ChangeTracker state saved only after success → no crash-window missed change.
- No `asyncio.run`-inside-running-loop (MCP never calls readers).
- FAISS -1 padding skipped; empty `remove_ids` no-op; mmap index mutate+resave
  works; `_safe_join` blocks `..`; cloud doc-ids don't collide; single-connector
  collections can't mix naive/aware datetimes; model cache worst case is a perf
  double-load, not wrong results.
