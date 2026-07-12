---
type: feature-tech
feature: review-remediation
sibling: product.md
parent: ../../tech.md
updated: 2026-07-12
---

# Feature: Review Remediation — Architecture

How each PR #155 review finding is fixed: the confirmed defect site (file:line at
HEAD), the mechanism, and the fix shape. Line numbers are anchors — verify against
the file before editing. Every P1/P2 finding below carries a review verdict of
CONFIRMED or PLAUSIBLE (many with live repros); see the per-item notes.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

---

## Files

```
src/indexed/config/store.py                                   # write-target resolver hardcodes preference=None (R1)
src/indexed/config/service.py                                 # _disk_baseline reads via stored preference (R1)
src/indexed/config/env_writer.py                              # non-atomic .env write; export-line dup (R11, P3)
src/indexed/config/store.py                                   # _env_to_mapping scalar-vs-nested order (P3)
src/indexed/mcp/server.py                                     # lifespan config load unguarded (R2)
src/indexed/mcp/tools.py                                      # _run_search / search_collection error handling (P3)
src/indexed/mcp/resources.py                                  # collection_status catches only IndexedError (P3)
src/indexed/core/v1/engine/services/inspect_service.py        # ENOENT vs EACCES in _discover_collections (R3)
src/indexed/core/v1/engine/persisters/disk_persister.py       # _raise_on_error; replace_folder swap window (R3)
src/indexed/core/v1/engine/services/search_service.py         # dead-for-CLI discover: staging filter, ENOENT (P3)
src/indexed/connectors/confluence/async_confluence_cloud_reader.py  # isinstance(Exception) vs BaseException (R4); dropped retry/skip (R13)
src/indexed/connectors/jira/unified_jira_document_reader.py   # enhanced_jql None guard (R5)
src/indexed/connectors/jira/async_jira_cloud_reader.py        # dropped retry/skip; dead max_skipped (R13)
src/indexed/connectors/jira/unified_jira_document_converter.py# ADF ordered/nested list joins (P3)
src/indexed/connectors/jira/connector.py                      # _jira_from_manifest hard baseUrl KeyError (P3)
src/indexed/connectors/confluence/connector.py                # _confluence_from_manifest hard baseUrl KeyError (P3)
src/indexed/connectors/document_cache_reader_decorator.py     # cache key omits parse settings (R6)
src/indexed/connectors/files/files_document_reader.py         # get_reader_details omits ocr/table/max_tokens (R6)
src/indexed/connectors/files/change_tracker.py                # mtime-only strategy miss (P3)
src/indexed/connectors/_incremental.py                        # order-by split inside quoted literals (P3)
src/indexed/connectors/_url_guard.py                          # IPv6 host collapse in _client_host (P3)
src/indexed/parsing/code_chunker.py                           # char-not-token bound; unbounded accumulator; acc_start-or-0 (R12); .tsx grammar (P3)
src/indexed/parsing/plaintext_parser.py                       # token sum ignores join separators (R12)
src/indexed/parsing/docling_parser.py                         # format_options PDF-only (R14)
src/indexed/cli/utils/console.py                              # shared Console(markup=True) — central fix seam (R7)
src/indexed/cli/utils/progress_bar.py                         # unescaped query/collection in markup (R7)
src/indexed/cli/utils/components/key_value_panel.py           # unescaped Table.grid cells (R7)
src/indexed/cli/utils/components/cards.py                     # reference: hardened Text() wrap (R7)
src/indexed/cli/utils/storage_info.py                         # unescaped path in markup (R7)
src/indexed/cli/utils/init.py / cli/init.py                   # unescaped model name in markup (R7)
src/indexed/utils/logger.py                                   # rich sink parses markup, catch=True swallows (R7)
src/indexed/config/commands/_render.py                        # core/logging panels gated on show_defaults (R8)
src/indexed/cli/knowledge/commands/_create_commands.py        # bools always in cli_overrides (R9)
src/indexed/cli/knowledge/commands/_create_options.py         # option types (bool vs Optional[bool]) (R9)
src/indexed/config/service.py                                 # validate_requirements precedence (R9, reference)
src/indexed/utils/batch.py                                    # infinite loop on empty page (R12)
scripts/connector_stub.py                                     # stub ignores offset; default comment mode (P3)
tests/fixtures/connectors/stub_routes.py                      # no auth-header / attachment routes (P3)
tests/system/test_connectors_e2e_cli.py                       # exit-0-only assertions; coverage gaps (P3)
```

---

## Implementation Detail

### R1 — config set/delete write-target mismatch (CONFIRMED, data loss)

Read baseline: `service.py:_disk_baseline` (~161-174) → `workspace.resolve_storage_mode()`
passes `workspace_preference=self.get_preference()` (the **stored** `[workspace] mode`).
Write target: `store.py:write` → `_resolve_write_target` (~357-383) calls the same
cascade but hardcodes `workspace_preference=None` at ~line 380. Cascade order
(`storage.py:190-196`): `mode_override` → `workspace_preference` → `has_local_config` →
default `global`. Divergence when a stored preference exists but no local file backs it
(`set_preference` writes `mode=local` into global only, never creates the local file).
`save_raw` then atomically replaces the *global* file with just the written key + `_meta`,
destroying the rest including `[workspace]`.
**Fix:** resolve the write target with the same `workspace_preference` used for the read
baseline (thread the resolved mode through, or have `_resolve_write_target` read the stored
preference). Regression test: set local preference with no local file, `config set` a global
key, assert the sibling keys survive.

### R2 — MCP lifespan crashes on malformed config (CONFIRMED, repro'd)

`mcp/server.py:lifespan` (44-56) calls `register_app_config()` (48) and
`resolve_collections_context()` (49) with no try/except; only `_get_config()` (35-41,
called after) has the fallback. Chain: `resolve_collections_context` → `get_preference`
→ `TomlStore._read_toml_file` → `tomllib.load` (`store.py:137`) raises `TOMLDecodeError`.
**Fix:** wrap the lifespan config resolution in the same defensive fallback `_get_config()`
uses (or make `read_for_mode`/`get_preference` tolerate a parse error by returning defaults
with a logged warning). Test: plant a malformed global config, assert `lifespan` yields.

### R3 — fail-loud over-correction on missing dir (CONFIRMED)

`disk_persister.py:read_folder_files` (~157-167) uses `os.walk(path, onerror=_raise_on_error)`;
`_raise_on_error` (~161-162) re-raises unconditionally. On a missing top dir, `os.walk`
invokes `onerror` with the initial `os.scandir` `FileNotFoundError`.
`inspect_service._discover_collections` (100-123) re-raises `StorageError`; `app.py:224-241`
maps it to exit 3. Affects `indexed inspect` **and** `indexed index search` (no
`--collection`) — the search CLI reaches it via `search.py:131 status_svc` →
`InspectService`, **not** `SearchService._discover_collections` (that path is dead for CLI,
only functional/MCP `configs=None`).
**Fix:** distinguish `ENOENT` (missing dir → treat as empty list, normal) from other
`OSError` (e.g. `EACCES` → raise `StorageError`). Apply in the shared
`InspectService._discover_collections` path (single fix point for both entrypoints).
The existing fail-loud test only mocks a generic permission `OSError`; add a real
missing-dir test asserting empty + exit 0.

### R4 — Confluence CancelledError not routed to failure (CONFIRMED)

`async_confluence_cloud_reader.py` comment-fetch (260) and attachment-fetch (360) use
`isinstance(result, Exception)`. `outline_document_reader.py:300-303` uses
`isinstance(result, BaseException)` with an explanatory comment (same PR). A
`CancelledError` (a `BaseException`, not `Exception`) falls through to the else branch and
is stored as `comments_map[i]`/`attachments_map[i]`; the converter
(`unified_confluence_document_converter.py:114-116,188-190`) iterates it → `TypeError`.
**Fix:** change both checks to `BaseException`, matching outline. Test: gather returns a
`CancelledError`, assert it lands in the failure branch (defaults to `[]`).

### R5 — Jira enhanced_jql None deref (CONFIRMED)

`unified_jira_document_reader.py:do_request` (322-328) returns `enhanced_jql(...)` with no
`or {}`; line 336 does `result.get("issues", [])`. Siblings `jql()` at 279-281 and 381-389
guard with `or {}`.
**Fix:** add `or {}` to the `enhanced_jql` result (and audit `approximate_issue_count` at
~278, also unguarded). Test: mock `enhanced_jql` → `None`, assert empty page not crash.

### R6 — document cache key omits parse settings (CONFIRMED, silent stale)

`document_cache_reader_decorator.py:__build_cache_key` (99-103) hashes
`get_reader_details()`. For files, `files_document_reader.py:get_reader_details` (164-172)
returns 6 fields and omits `_ocr`/`_table_structure`/`_max_tokens` (stored 86-88, applied at
parse, baked into cached chunks via `v1_adapter.reader_output`). Cache dir is global
(`create_collection_factory.py:60-71`), namespaced only by the sha256; `use_cache` default
True; `_clear_caches` gated on `force` (default False).
**Fix:** include ocr/table_structure/max_chunk_tokens in `get_reader_details()` (or in the
cache-key input). Test: two reads over the same path with different `max_tokens` produce
different cache keys.

### R7 — Rich markup safety (CONFIRMED, repro'd; systemic — fix at altitude)

Shared `Console()` (`cli/utils/console.py:17`) has markup enabled. Unescaped user data
reaches markup-parsed sinks at: `progress_bar.py` search query/collection
(`build_search_phase_label` 220-235 → `add_task` 107-110, `TextColumn("[progress.description]…")`
54); `key_value_panel.py` `Table.grid` cells (119/127); `cards.py` title; `storage_info.py`
path (74); `init.py` model name (116/119); `logger.py` rich sink (165/179, `catch=True`
swallows the resulting `MarkupError`, dropping the real message/traceback). `cards.py:39-54`
already wraps values in `Text()` for exactly this (bug E2).
**Fix (preferred, at altitude):** stop hand-escaping per call site. Route user data through
`Text(str(x))` / a `markup=False` render path, or a single escaping helper applied at every
user-data sink. For the logger sink, render with `markup=False`. Add a regression test that
`search "list[int]"`, `config list` with a bracketed value, and a bracketed traceback all
render literally without `MarkupError`.

### R8 — config list hides manually-set values (CONFIRMED, sweep)

`config/commands/_render.py`: Core Settings panel gated
`if core_sections and (show_defaults or section_filter=='core')` (~123); logging/mcp/perf
panel `if rows and show_defaults` (~160). Both override the per-key `should_show_key`
predicate (91-97) that keeps manually-set (non-default) values. Sources panel has no gate.
**Fix:** render a panel when it has any manually-set (non-default) row even without
`--show-defaults`. Test: `config set core.v1.indexing.chunk_size 256` then `config list`
shows it.

### R9 — create bool flags always override config.toml (CONFIRMED)

`_create_commands.py` assigns `cli_overrides["respect_gitignore"]` (45),
`read_all_comments` (126), `include_attachments`/`ocr_enabled` (166-167) unconditionally.
Options are typed plain `bool` (`_create_options.py` 104-110 etc.), so Typer has no
"unset" sentinel. `service.py:validate_requirements` (236-240) checks `cli_overrides` before
`config_data`.
**Fix:** type these options `Optional[bool]` (default `None`) and only add to `cli_overrides`
when not `None` — mirroring the already-correct `if path:` / `if jql:` pattern next to them.
Test: config.toml `respect_gitignore=false` + no flag → honored.

### R11 — env_writer atomicity (+ P3 export dup) (PLAUSIBLE)

`env_writer.py:write` (~58) truncates with `open(path,'w')` + `writelines` — non-atomic;
`TomlStore.write` was made atomic (tmp → `os.replace`) this PR. Also `write` matches only
`KEY=`/`KEY =` lines, not `export KEY=`, appending a duplicate binding (P3).
**Fix:** temp-write + `os.replace`; extend the key-match regex to accept an optional
`export ` prefix. Test: kill-sim leaves the original intact; updating an `export`-prefixed
key replaces in place.

### R12 — chunk/token bounds + batch loop (CONFIRMED)

`code_chunker.py` bounds by `len(text) > _max_chars` (`_max_chars = _max_tokens*4`, 100-102)
at 178/260 and never calls `count_tokens`; the between-nodes accumulator (194-198) has no
size guard; `acc_start or child.start_point[0]` (171, 210) drops a legitimate row-0
`acc_start`. `plaintext_parser.py` sums per-piece `count_tokens` but emits `sep.join(buf)`
without counting separators (~155). `utils/batch.py` (20/65/66): `start_at += len(items)`
never advances on an empty page while `start_at < total` stays True → infinite loop; the
`max_skipped_items_in_row` guard is exception-only.
**Fix:** bound emitted code chunks by `count_tokens` (import from `_model_window`); guard the
accumulator by the same bound; use `acc_start if acc_start is not None else …`; count the
join separators in plaintext; in batch, break (or raise) when `len(items) == 0` with
`start_at` unchanged. Tests per sub-item.

### R13 — dropped retry / skip-and-continue (PLAUSIBLE)

`async_jira_cloud_reader.py` (`_read_issues_sync` ~64) and
`async_confluence_cloud_reader.py` (~129) are hand-rolled while-loops that no longer call
the old `execute_with_retry` + `read_items_in_batches` skip-and-continue; `max_skipped_items_in_row`
is stored (~100) but unused.
**Fix:** either re-wire the skip-and-continue + retry (preferred: reuse `utils/retry` +
`utils/batch` `read_items_in_batches` once R12's loop is fixed) or delete the dead
`max_skipped_items_in_row` param and document the behavior change. Decide in the plan.

### R14 — docling options PDF-only (PLAUSIBLE)

`docling_parser.py` (~466) derives `_supported_extensions` from all `InputFormat` members
but `format_options` configures only `InputFormat.PDF`, so docx/pptx skip `do_ocr`/
`do_table_structure`.
**Fix:** build `format_options` for every supported input format (or document the PDF-only
scope explicitly). Test: a non-PDF path with `ocr=True` receives the option.

### Lower-Severity Backlog (P3)

Confirmed/plausible, narrower trigger or diagnosability/coverage. Fix, convert to an issue,
or defer with rationale before wrap-up:

- **MCP handler scope** — `mcp/tools.py:_run_search` (~45) and `mcp/resources.py:collection_status`
  (~594) catch only `IndexedError`; a non-`IndexedError` (e.g. `AttributeError` from a
  malformed manifest) escapes as a raw MCP protocol error instead of `mcp_error_envelope`.
- **search_collection fabricated fallback** — `mcp/tools.py` (~96/779) swallows any
  `svc_status` failure and searches a fabricated `DEFAULT_INDEXER` localFiles config,
  masking not-found/corrupt errors.
- **env scalar-vs-nested order** — `store.py:_env_to_mapping` (~2696 in patch / real ≪471):
  `INDEXED__A` scalar processed after `INDEXED__A__B` nested silently overwrites the dict;
  order-dependent crash vs silent drop.
- **_incremental order-by split** — `_incremental.py` splits on `ORDER BY` anywhere including
  inside quoted literals; a query with `text ~ "please order by …"` yields broken JQL/CQL.
- **_url_guard IPv6** — `_client_host` (~61) splits the authority on `:` with no IPv6 bracket
  handling; `[::1]`/`[::2]` both collapse to `[`, treated same-origin (self-hosted IPv6 only).
- **change_tracker mtime miss** — `change_tracker.py` (~432) `mtime > cutoff` with no hash
  fallback under the `mtime` strategy misses timestamp-preserving edits (rsync -a, git checkout).
- **logger swallow** — covered by R7 (rich sink markup + `catch=True`).
- **.tsx grammar** — `code_chunker.py:LANGUAGE_MAP` (~20) maps `.tsx`→`typescript`, never
  `language_tsx()`; TSX gets wrong semantic boundaries.
- **ADF list fidelity** — `unified_jira_document_converter.py`: orderedList rendered as `-`
  bullets (~149); listItem nested-list recurse joins with no separator (~159).
- **manifest KeyError** — `jira/connector.py:_jira_from_manifest` (~32) and
  `confluence/connector.py:_confluence_from_manifest` (~40) read `rd["baseUrl"]` hard after a
  defensive `rd.get("query")`; a manifest missing `baseUrl` raises unmapped `KeyError`.
- **connector e2e gaps** — `tests/fixtures/connectors/stub_routes.py` asserts no auth header;
  attachment/redirect routes unregistered; Confluence default `read_all_comments=True` path
  untested; outline stub ignores request `offset` (infinite-loop risk if reused for >1 doc).

### Cleanup (non-correctness, optional)

- `cli/composition.py` top-level `DiskPersister` import defeats the stated <1s lazy startup.
- `mcp/config.py` `resolve_cli_context` duplicates the `_MISSING` sentinel of `resolve_config`.

<!-- No merge blocks: these are point fixes, not cross-cutting architecture. The one
     altitude decision (R7 central markup safety) promotes to root tech.md only if the fix
     lands as a shared render seam rather than per-site escaping. -->

---

## Open Questions

1. **R13 wire-or-delete** — re-wire `max_skipped_items_in_row` retry/skip, or delete the dead
   param and accept fail-fast? Depends on whether partial-index tolerance is a product
   requirement. Recommendation: re-wire via shared `utils/retry` + `read_items_in_batches`
   after R12 fixes the batch loop; it restores documented behavior for large spaces.
2. **R7 scope** — central `markup=False`/`Text()` render seam vs per-site `escape()`. Altitude
   argues for the seam; scope is larger. Recommendation: seam for the logger sink + a single
   user-data helper, then convert call sites.
