# Implementation Plan — Review Remediation (PR #155 defects)

> **Type:** execution plan (writing-plans format) · **Feature:** review-remediation
> **Branch:** `claude/review-remediation-plan-feu6t7`
> **Spec source of truth:** [`.spec/features/review-remediation/`](../.spec/features/review-remediation/)
> ([product](../.spec/features/review-remediation/product.md) ·
> [tech](../.spec/features/review-remediation/tech.md) ·
> [plan](../.spec/features/review-remediation/plan.md))
> **Validated:** 2026-07-12, all 15 requirements re-confirmed against code at HEAD by
> six parallel subagents (Sonnet + Haiku). Line numbers below are the **current**
> HEAD locations, not the spec's original anchors.

---

## Goal

Fix every confirmed PR #155 review defect **behind a red→green regression test**, so
the next refactor cannot silently reintroduce it. Nine units (`review-remediation/1..9`,
IDs assigned once, never renumbered). Each unit is one or more green commits that pass
the full verify gate. Units touch mostly disjoint files and are built to run in
**parallel** (one fresh subagent per unit).

## Architecture summary (where the fixes live)

Four layers, top calls down only: **CLI/MCP** → **Services + core facade** (`indexed.core`)
→ **Engine** → **Infra** (config, connectors, parsing, utils, protocols). These are point
fixes on stable surface — no cross-cutting architecture change. The one altitude decision
(R7 markup safety) lands as a shared render seam in the CLI layer only.

## Tech stack / global constraints (copied from AGENTS.md)

- Python 3.11+, `uv` only. Run **everything** via `uv run` from the **project root**.
- **Verify gate** — all must pass before each commit:
  ```bash
  uv run ruff check . --fix && uv run ruff format
  uv run ty check src/indexed                 # 0 diagnostics, full-tree clean
  uv run pytest -q --cov=src/indexed          # full suite, >85% coverage
  python scripts/check_imports.py             # module-edge gate (4 edges, one package)
  bash .agents/skills/spec/scripts/validate.sh  # ONLY if .spec/ touched (see note)
  ```
  - **Coverage scope:** enforced on `core/connectors/config/parsing/protocols/utils`
    only. `indexed.cli` and `indexed.mcp` are **exempt** (UI chrome, `omit`ed in
    `pyproject.toml`). Units 2 (mcp half), 5 (R7), and the mcp items in unit 9 still
    ship tests, but they will **not** move the coverage number — do not chase coverage
    on cli/mcp code.
  - **`validate.sh` note:** the `spec` skill is *not vendored* in the cloud environment
    (`.agents/skills/` symlinks are dangling; skills install via `npx skills`). If the
    script is absent, run `npx skills install` or skip it and instead sanity-check the
    edited spec by eye. Do not block a unit on a missing validator.
- **Commit:** one line, ≤50 chars, imperative, `<type>(<scope>): <subject>`, cite the
  unit ID. **No body, no footer.** (Exact strings given per unit below — each is ≤50.)
- **Module edges (never break):** `core ↛ connectors`, `connectors ↛ core`;
  `config`/`utils`/`parsing`/`protocols` never import up. `check_imports.py` enforces.
- Lazy-load heavy ML imports **inside functions** (keeps startup <1s).
- Route all config through `ConfigService` (singleton; respect the priority chain).
- **COMPOUND:** the two spec Open Questions are resolved in this plan (see below); the
  spec `plan.md` has been updated to record the resolutions. Bump `updated:` on any spec
  you touch.

---

## Resolved decisions (were Open Questions in the spec)

| # | Question | Resolution | Rationale (from validation) |
|---|----------|-----------|-----------------------------|
| **OQ1** | R13: wire or delete `max_skipped_items_in_row`? | **WIRE.** Re-use `utils/batch.read_items_in_batches` + `utils/retry.execute_with_retry`. Sequence **after** unit 7 (R12 batch fix). | The utilities are alive, tested, and already the pattern in 3 of 4 reader variants; only the two async Cloud readers hand-roll loops. Deleting the param is a product-visible regression (single bad page aborts a whole large-space index). The Confluence async page loop today has **zero** retry — strictly worse than its sync sibling. |
| **OQ2** | R7: central `markup=False` seam vs per-site escaping? | **Escape-helper + `Text()` seam.** Add one user-data helper, convert the ~6 sinks, switch the logger sink to `Text(line, style=…)`. Do **not** set `Console(markup=False)` globally. | A global `markup=False` would break the app's *intentional* markup (`[dim]…`, `[{style}]…` in cards/init/storage_info/logger). `rich.markup.escape` is **already** used in `conflict_prompt.py`; `cards.py` already wraps values in `Text()` — established local patterns to mirror. |
| **R2 scope** | Guard `lifespan` only, or fix at the config root? | **Guard both MCP sites** (`mcp/server.py:lifespan` + `mcp/config.py:resolve_cli_context`). | Root-fixing `get_preference` would silence malformed-config errors in the **CLI** path too, changing fail-loud semantics. Requirement R2 is explicitly lifespan-scoped; the per-call MCP fallback (`resolve_cli_context`) shares the same unguarded call and must be guarded alongside it. |
| **R14 shape** | "Apply options to all supported formats." | **Add `InputFormat.IMAGE` only.** Leave Simple-pipeline formats alone. | Only `PDF`/`IMAGE` use the Pdf pipeline (which *has* `do_ocr`/`do_table_structure`). `DOCX/PPTX/HTML/XLSX` use `SimplePipeline` with base `PipelineOptions` that has **no** such fields — uniformly attaching Pdf options would crash. Real impact is `.png/.jpg/.jpeg/.tiff` silently ignoring caller `ocr=False`. |

---

## Parallel execution model

Dispatch **one fresh subagent per unit**. Each agent gets: this plan's unit section, the
verify gate, and "read the cited files at HEAD before editing." Review each unit's diff
before merging.

### Dependency graph & waves

```
WAVE 1 (all independent — run concurrently, disjoint files):
  1  config write-target + env-mapping         (config/store.py, config/service.py)
  2  MCP graceful config + missing-dir          (mcp/, core/…/services, disk_persister)
  3  connector crash guards (R4,R5)             (confluence + jira readers)
  4  cache-key parse settings (R6)              (files reader, cache decorator)
  5  Rich markup safety (R7)                    (cli/utils/*, utils/logger.py)
  6  config CLI correctness (R8,R9)             (config/commands, cli/knowledge/commands)
  7  parsing + batch bounds (R12,R14,.tsx)      (parsing/*, utils/batch.py)
  8a env_writer atomicity (R11)                 (config/env_writer.py)
  9  P3 backlog sweep + test infra (R15)        (mcp/, connectors/*, tests/…) — see note

WAVE 2 (after its deps land):
  8b cloud-reader skip/retry (R13)   depends on → 7 (batch fix) AND 3 (shares confluence reader file)
```

### File-conflict de-collision (so wave-1 agents never touch the same file)

The spec catalogue listed three P3 items in files owned by a P1/P2 unit. To keep wave-1
files disjoint, they are **reassigned to the owning unit**:

- `store.py:_env_to_mapping` scalar-vs-nested (P3) → **unit 1** (already edits `store.py`).
- `code_chunker.py` `.tsx` grammar (P3) → **unit 7** (already edits `code_chunker.py`;
  spec plan.md already lists it there).
- `utils/logger.py` markup swallow (P3) → **unit 5** (it is R7).

Unit 9 therefore owns every *other* P3 item. The only remaining shared file is
`confluence/async_confluence_cloud_reader.py` (unit 3's R4 + unit 8b's R13) — handled by
running **8b after 3** (8b is wave-2 anyway).

> If you run wave-1 agents in isolated git worktrees, the above guarantees zero merge
> conflicts within a wave. Merge unit 3 before starting unit 8b.

---

## Task format

Each unit below carries: **Requirements**, **Files** (modify / test), **Defect** (current
HEAD location + validated snippet), **Fix**, **Test-first steps** (write test → run → see
red → implement → run → green), **Verify**, **Commit**. No placeholders — locations and
test hooks are the validated, current ones.

---

## review-remediation/1 — Config write-target parity (+ env-mapping)

**Severity:** P1 (data loss) · **Requirements:** R1 (+ R15 env-mapping item) · **Deps:** none

**Files**
- modify: `src/indexed/config/store.py` — `_resolve_write_target` (write-target); `_env_to_mapping` (env order)
- modify: `src/indexed/config/service.py` — resolve mode once, thread to write
- test: `tests/unit/indexed/config/test_config_service_storage.py` (write-target); `tests/unit/indexed/config/test_store.py` (env-mapping)

**Defect (R1 — CONFIRMED, data loss).** Read baseline `ConfigService._disk_baseline`
(`service.py:161-174`) resolves mode via `self._workspace.resolve_storage_mode()` which
honors `get_preference()` (the stored `[workspace] mode`). Write target
`TomlStore._resolve_write_target` (`store.py:357-383`) calls the same cascade but
hardcodes `workspace_preference=None` at **`store.py:380`**:
```python
mode = resolve_storage_mode(
    mode_override=self._mode_override,
    workspace_preference=None,          # ← bug: ignores the stored preference
    workspace=self.workspace,
)
```
When `set_preference("local")` was called but no local `config.toml` exists (that setter
writes `[workspace] mode` into the **global** file only, never creates the local file),
the baseline reads mode `local` (empty local file) while the write resolves mode `global`.
`TomlStore.write` (`store.py:394-432`) then does a **full-file replace** (`out = dict(data)`
→ tmp → fsync → `os.replace`), overwriting the global file with only the one written key +
`_meta` and **destroying `[workspace]` and every other global key**.
- `_resolve_write_target` is also reached by `resolved_config_path()` (`store.py:385-392`),
  consumed by `config/commands/set.py:155` ("Location:" display) and
  `cli/knowledge/commands/_create_helpers.py:177` (create snapshot/restore) — so the fix
  must land in the resolver, not only in a new `write()` parameter, or those two stay wrong.
- **Not affected:** `.env` writes — `ConfigService._resolved_env_path` (`service.py:97-104`)
  resolves mode via the preference-honoring path and bypasses `TomlStore._env_path` entirely.

**Fix (R1).** Best shape: `ConfigService` resolves the mode **once** per `set`/`delete`
and passes that exact mode to both the baseline read and the write, so read-target and
write-target can never diverge. Minimal shape: make `_resolve_write_target` consult the
stored preference (mirror `WorkspaceManager.resolve_storage_mode`, i.e. pass
`workspace_preference=None if self._mode_override else <stored preference>`). Whichever
shape, also fix `resolved_config_path()` (same call) so the display and snapshot paths
agree with the real write.

**Defect (R15 env-mapping — CONFIRMED).** `store.py:_env_to_mapping` (function at
`store.py:443-471`): intermediate path segments get a type-conflict check, but the final
key at **`store.py:470`** (`cur[parts[-1].lower()] = v`) does not — `INDEXED__A__B=x`
(creates dict at `A`) followed by `INDEXED__A=y` silently overwrites the dict (order-dependent).
**Fix:** guard the final assignment the same way the intermediate segments are guarded
(don't clobber an existing nested dict with a scalar; log/skip or raise a clear error).

**Test-first steps**
1. `test_config_service_storage.py` — add `TestSetDeleteWriteTargetConsistency` beside the
   existing `test_resolve_storage_mode_respects_workspace_preference` (~lines 169-185, reuse
   its fixture): `set_preference("local")` (no local file), then `service.set("core.v1.search.max_docs", 5)`.
   Assert (a) the local `config.toml` now exists with the key, and (b) the global
   `config.toml` still contains `[workspace]` (mode="local"). **Run → RED** (global wiped today).
2. `test_store.py` — add a `_env_to_mapping` test: env `{"INDEXED__A__B": "x", "INDEXED__A": "y"}`
   in that order; assert it does not silently drop `A.B` (define expected behavior — raise or
   keep nested + warn). **Run → RED.**
3. Implement the resolve-once fix + the final-key guard. **Run both → GREEN.**
4. Full verify gate → commit.

**Verify:** `uv run pytest -q tests/unit/indexed/config/test_config_service_storage.py tests/unit/indexed/config/test_store.py`, then the full gate.

**Commit:** `fix(config): review-remediation/1 write target`

---

## review-remediation/2 — Graceful missing/broken config

**Severity:** P1 (crash) · **Requirements:** R2, R3 · **Deps:** none
*(R2 half and R3 half touch disjoint files — may be split into two agents/commits.)*

**Files**
- modify (R2): `src/indexed/mcp/server.py` — `lifespan`; `src/indexed/mcp/config.py` — `resolve_cli_context`
- modify (R3): `src/indexed/core/v1/engine/services/inspect_service.py` — `_discover_collections`; `src/indexed/core/v1/engine/services/search_service.py` — `_discover_collections` (+ staging filter)
- keep unchanged (R3): `src/indexed/core/v1/engine/persisters/disk_persister.py` — fail-loud is correct at that layer
- test: `tests/unit/indexed/mcp/test_server.py` (R2); `tests/unit/indexed/core/services/test_inspect_service.py` + `.../test_search_service.py` (R3)

**Defect (R2 — CONFIRMED, repro'd).** `mcp/server.py:lifespan` (44-56) calls
`resolve_collections_context()` at **line 49** with no try/except (contrast the guarded
`_get_config` at 35-41). Chain: `resolve_collections_context` (`cli/composition.py:121-150`)
→ `ConfigService.resolve_storage_mode` (`service.py:330-332`) → `WorkspaceManager.get_preference`
(`workspace.py:38-48`), which **always** reads the global `config.toml` via `tomllib.load`
(`store.py:137`) → `TOMLDecodeError` escapes `lifespan`, FastMCP never starts. `register_app_config`
(line 48) is I/O-free and safe. The **same** unguarded call sits in `mcp/config.py:resolve_cli_context`
(33-36), the MCP per-request fallback.
**Fix:** wrap both MCP sites in the `_get_config`-style fallback (log a warning, degrade to a
default global-mode context). Do **not** change `get_preference`/`read_for_mode` (keeps CLI fail-loud).

**Defect (R3 — CONFIRMED).** `disk_persister.read_folder_files` (157-167) uses
`os.walk(path, onerror=_raise_on_error)` and `_raise_on_error` (161-162) re-raises
unconditionally; on a missing top dir `os.walk` invokes `onerror` with the initial
`FileNotFoundError`. `InspectService._discover_collections` (100-123) catches `Exception`
and wraps it as `StorageError` (121-123) → `cli/errors.py` maps `StorageError`→exit 3 →
`app.py:224-241`. This hits **both** `indexed inspect` and `indexed index search` (no
`--collection`): the search CLI routes `search.py:131 status_svc(...)` → functional
`status()` (`inspect_service.py:355-395`) → `InspectService._discover_collections`
(`inspect_service.py:206-207`, `if collection_names is None`). `SearchService._discover_collections`
(`search_service.py:92-115`) is **dead for CLI** (search always passes `configs=[...]`) but
**is** the MCP `search` path (`tools.py:72 _run_search(query, None, …)` → configs=None).
**Fix:** in **each** `_discover_collections`, distinguish `ENOENT` (missing dir → return `[]`)
from other `OSError` (e.g. `EACCES` → keep raising `StorageError`). Leave `disk_persister`
fail-loud. Also add the staging-dir filter to `search_service._discover_collections` (it
lacks the `*.tmp-*` internal-dir exclusion the inspect path has).

**Test-first steps**
1. `test_server.py::TestLifespan` — add `test_lifespan_yields_despite_malformed_global_config`:
   write `"not [ valid toml"` to a temp global `config.toml`, `monkeypatch Path.home`, `reload()`,
   `async with lifespan(mcp) as state: assert "cli_context" in state`. **RED** (raises today).
2. `test_inspect_service.py` — beside `TestDiscoverCollectionsFailsLoud` (~215): construct
   `InspectService(collections_path=str(tmp_path/"does-not-exist"))` with a **real** missing path
   (not a mocked `read_folder_files`) and assert `_discover_collections() == []`. **RED.**
3. `test_search_service.py` — mirror the missing-dir test near its `TestDiscoverCollectionsFailsLoud`
   (~283), plus a staging-filter test (feed `["mycol.tmp-123/manifest.json", "real/manifest.json"]`,
   assert the `.tmp-` dir is excluded). **RED.**
4. Implement guards + staging filter. **GREEN.** The existing permission-`OSError` fail-loud
   tests (which mock a non-ENOENT error) stay green — verify they still pass.
5. Full gate → commit(s).

**Verify:** `uv run pytest -q tests/unit/indexed/mcp/test_server.py tests/unit/indexed/core/services/`, then full gate.

**Commit(s):** `fix(mcp): review-remediation/2 lifespan guard` and `fix(core): review-remediation/2 missing dir`

---

## review-remediation/3 — Connector crash guards (R4, R5)

**Severity:** P1 · **Requirements:** R4, R5 · **Deps:** none
*(Merge before starting 8b — shares the Confluence reader file.)*

**Files**
- modify: `src/indexed/connectors/confluence/async_confluence_cloud_reader.py` — both gather loops
- modify: `src/indexed/connectors/jira/unified_jira_document_reader.py` — `enhanced_jql` + `approximate_issue_count`
- test: `tests/unit/indexed/connectors/confluence/test_reader_attachments.py`; `tests/unit/indexed/connectors/jira/test_readers.py`

**Defect (R4 — CONFIRMED).** Comment-fetch (`async_confluence_cloud_reader.py:257-266`) and
attachment-fetch (`:357-368`) use `isinstance(result, Exception)` on
`asyncio.gather(..., return_exceptions=True)` results:
```python
for i, result in enumerate(results):
    if isinstance(result, Exception):        # ← misses CancelledError (a BaseException)
        logger.warning(...); comments_map[i] = []
    else:
        comments_map[i] = result             # ← stores CancelledError as the value
```
`asyncio.CancelledError` is a `BaseException` (not `Exception`), so it lands in `else` and
is stored; the converter (`unified_confluence_document_converter.py:114-116` comments,
`:188-190` attachments) then iterates it → `TypeError`. The Outline sibling
(`outline_document_reader.py:297-310`) already uses `BaseException` with an explanatory comment.
**Fix:** change **both** checks to `isinstance(result, BaseException)`; copy Outline's comment.
(Grep confirms these are the only two unfixed `return_exceptions=True` sites in `connectors/`.)

**Defect (R5 — CONFIRMED).** `unified_jira_document_reader.py:do_request` (322-336) returns
`enhanced_jql(...)` with no `or {}`; `:336` does `result.get("issues", [])`. Siblings
`jql()` (`:279-281`, `:381-389`) guard with `or {}`. `approximate_issue_count` (`:276-278`)
is **also** unguarded (`result.get("count", 0)`).
**Fix:** add `or {}` to the `enhanced_jql` result **and** the `approximate_issue_count` result.

**Test-first steps**
1. `test_reader_attachments.py` — the existing `test_fetch_all_attachments_async_handles_exceptions`
   (~548) uses `RuntimeError` (an `Exception`, already caught) so it does **not** exercise this.
   Add a test patching `_fetch_comments_for_page` with `AsyncMock(side_effect=asyncio.CancelledError())`,
   run `asyncio.run(reader._fetch_all_comments_async(pages))`, assert `comments_map[0] == []`.
   Mirror for attachments. **RED** (stores the `CancelledError` today).
2. `test_readers.py` — `FakeJiraCloud.enhanced_jql`/`approximate_issue_count` (~33-51) always
   return dicts. Subclass/monkeypatch `enhanced_jql` → `None`, run the listing, assert an empty
   page and **no** `AttributeError`. Mirror for `approximate_issue_count`. **RED.**
3. Implement both fixes. **GREEN.** Full gate → commit.

**Verify:** `uv run pytest -q tests/unit/indexed/connectors/confluence/test_reader_attachments.py tests/unit/indexed/connectors/jira/test_readers.py`, then full gate.

**Commit:** `fix(connectors): review-remediation/3 crash guards`

---

## review-remediation/4 — Cache-key parse settings (R6)

**Severity:** P1 (silent stale) · **Requirements:** R6 · **Deps:** none

**Files**
- modify: `src/indexed/connectors/files/files_document_reader.py` — `get_reader_details`
- verify (likely no change): `src/indexed/connectors/document_cache_reader_decorator.py` — `__build_cache_key`
- test: `tests/unit/indexed/connectors/files/test_reader_upgraded.py`

**Defect (R6 — CONFIRMED).** `document_cache_reader_decorator.__build_cache_key` (99-103)
hashes `get_reader_details()`. `files_document_reader.get_reader_details` (**164-172**)
returns 6 fields and **omits** `_ocr`/`_table_structure`/`_max_tokens` (stored at 86-88,
applied at parse via the lazy `parsing` property 104-108, and baked into the cached chunks):
```python
def get_reader_details(self) -> dict:
    return {"type": "localFiles", "basePath": self.base_path,
            "includePatterns": self.include_patterns, "failFast": self.fail_fast,
            "respectGitignore": self._respect_gitignore,
            "excludedDirs": list(self._excluded_dirs)}   # no ocr/table/max_tokens
```
Cache dir is global (`~/.indexed/data/caches`, keyed only by the sha256; `use_cache`
defaults True; `_clear_caches` gated on `force`, default False). So two runs over the same
path differing only in `max_chunk_tokens`/`ocr`/`table_structure` collide → stale,
differently-chunked documents served.
**Fix:** add `ocr`, `tableStructure`, `maxChunkTokens` (from `_ocr`/`_table_structure`/`_max_tokens`)
to the returned dict. Pure additive change; no other surface.

**Test-first steps**
1. `test_reader_upgraded.py` (has `test_get_reader_details` ~195-212, none touch these fields):
   build two `FilesDocumentReader`s with identical `base_path`/`include_patterns` but different
   `max_tokens` (and separately `ocr`), assert `r1.get_reader_details() != r2.get_reader_details()`.
   **RED** (equal dicts → same key today).
2. Add the three keys. **GREEN.** Confirm existing `get_reader_details` tests still pass. Full gate → commit.

**Verify:** `uv run pytest -q tests/unit/indexed/connectors/files/test_reader_upgraded.py tests/unit/indexed/connectors/test_cache_reader_decorator.py`, then full gate.

**Commit:** `fix(connectors): review-remediation/4 cache key`

---

## review-remediation/5 — Rich markup safety (R7)

**Severity:** P1 (crash on ordinary input) · **Requirements:** R7 · **Deps:** none
**Note:** cli/utils + logger — cli is coverage-exempt, but still ship tests (the logger is under `utils`, which IS coverage-gated).

**Files**
- add helper: `src/indexed/cli/utils/console.py` — a single `render_user_text(x) -> Text` / escape helper (do **not** set `Console(markup=False)`)
- modify: `src/indexed/cli/utils/progress_bar.py` (query/collection label); `src/indexed/cli/utils/components/key_value_panel.py` (grid cells 119/127); `src/indexed/cli/utils/components/cards.py` (title 86-89 — values already safe); `src/indexed/cli/utils/storage_info.py` (path 43-47/74); `src/indexed/cli/init.py` (model name 116-119); `src/indexed/utils/logger.py` (sink)
- test: new `tests/unit/indexed/cli/utils/test_markup_safety.py`; extend `tests/unit/utils/test_logger.py`

**Defect (R7 — CONFIRMED, systemic).** Shared `console = Console()` (`console.py:17`,
markup enabled). Unescaped user data reaches markup-parsed sinks:
- `progress_bar.py` — `build_search_phase_label` (`:235`) builds `Searching "…" for: "{query}"`,
  passed raw into `add_task(f"  {name}")` (107-110) rendered via `TextColumn("[progress.description]{task.description}")` (54). `search "list[int]"` → dropped `[int]` / `MarkupError`.
- `key_value_panel.py:119,127` — `grid.add_row(...)` cells raw (config values/paths).
- `cards.py:86-89` — **title** raw (`f"[dim]{title}[/dim]"`); **values** already `Text()`-wrapped (46-54) — the reference pattern.
- `storage_info.py:43-47,74` — path embedded in markup then `console.print(f"[...]{indicator}[/]")`.
- `init.py:116-119` — `m['name']` model name + `info['cache_dir']` raw in markup.
- `logger.py:151-165` (message) and `:174-181` (traceback) — custom sink `_make_console_sink`
  prints `f"[{style}]{line}[/{style}]"` (markup on); `catch=True` swallows the resulting
  `MarkupError`, dropping the real message/traceback. (Uses `highlight=False`, not `markup=False`.)

**Fix (OQ2).** Add one helper that returns a `Text` (never markup-parsed) or `escape()`s user
data, and apply it at each sink; keep the app's own style tags. For the logger sink, render
with `Text(line, style=…)` (style preserved, no markup parsing) instead of the f-string with
`[{style}]` tags — for **both** the message and the traceback branch. `rich.markup.escape` is
already imported in `conflict_prompt.py`; `cards.py` values show the `Text()` idiom.

**Test-first steps**
1. `test_markup_safety.py` — assert none of these raise and all render literally:
   `indexed index search "list[int]"` (progress label), `config list` with a value containing
   `[` (key_value_panel), a card title containing `[`, a storage path containing `[`.
   Use `CliRunner`/capture. **RED** (`MarkupError` today).
2. `test_logger.py` — log a message containing `list[int]` and log an exception whose traceback
   contains a bracketed repr; assert the record is emitted in full (not swallowed). **RED.**
3. Implement helper + convert sinks + logger `Text(...)`. **GREEN.** Full gate → commit.

**Verify:** `uv run pytest -q tests/unit/indexed/cli/utils/ tests/unit/utils/test_logger.py`, then full gate.

**Commit:** `fix(cli): review-remediation/5 markup safety`

---

## review-remediation/6 — Config CLI correctness (R8, R9)

**Severity:** P2 · **Requirements:** R8, R9 · **Deps:** none

**Files**
- modify (R8): `src/indexed/config/commands/_render.py` — `render_config_overview` gates (123, 160)
- modify (R9): `src/indexed/cli/knowledge/commands/_create_options.py` (bool → `Optional[bool]`); `src/indexed/cli/knowledge/commands/_create_commands.py` (guard `is not None`)
- test: `tests/unit/indexed/config/test_cli.py::TestList`; `tests/unit/indexed/knowledge/commands/test_create.py`

**Defect (R8 — CONFIRMED).** `_render.py`: Core Settings gate **`:123`**
`if core_sections and (show_defaults or section_filter == "core")`; logging/mcp/performance
gate **`:160`** `if rows and show_defaults`. Both discard manually-set rows that the per-key
predicate `should_show_key` (91-97, returns True for any non-default value) already keeps.
The Sources panel (100/111) has the correct pattern.
**Fix:** mirror Sources — gate entry on filter only (`if core_sections and (not section_filter
or section_filter == "core")`), compute rows via `should_show_key`, then `if rows:` render.
Do the same to the logging/mcp/performance gate.

**Defect (R9 — CONFIRMED).** `_create_commands.py` adds bool flags to `cli_overrides`
unconditionally: `respect_gitignore` (**:45**), `read_all_comments` (**:126**),
`include_attachments`/`ocr_enabled` (**:166-167**). Options are plain `bool` in
`_create_options.py` (`RespectGitignoreOpt` 104-110, `ReadAllCommentsOpt` 186-192,
`IncludeAttachmentsOpt` 233-239, `OcrOpt` 240-246), so Typer has no "unset" sentinel;
`validate_requirements` (`service.py:237-240`) checks `cli_overrides` before `config_data`,
so config.toml is always overridden by the Typer default. Field names verified against the
Pydantic models (`files/schema.py:61`, `confluence/schema.py:17`, `outline/schema.py:26,33`).
**Fix:** type these four options `Optional[bool] = typer.Option(None, "--flag/--no-flag")`
(tri-state confirmed in this uv env) and add to `cli_overrides` only `if x is not None:`.
⚠ **Guard on `is not None`, NOT truthiness** — `False` (`--no-respect-gitignore`) is a legit
explicit choice; the nearby `if path:`/`if jql:` (`Optional[str]`) pattern is **not**
transferable to bools.

**Test-first steps**
1. `test_cli.py::TestList` — set a manual non-default core value (e.g. mock `load_raw()` →
   `{"logging": {"level": "DEBUG"}}`), run `config list` **without** `--show-defaults`, assert
   `"DEBUG"` appears in stdout. **RED** (hidden today). (No existing test touches core/logging panels.)
2. `test_create.py::TestCreateFiles` — call the create path **without** passing `respect_gitignore`;
   assert `"respect_gitignore" not in cli_overrides` (once default is `None`). Mirror for
   Confluence `read_all_comments` and Outline `include_attachments`/`ocr_enabled`. **RED.**
3. Implement both. **GREEN.** Full gate → commit.

**Verify:** `uv run pytest -q tests/unit/indexed/config/test_cli.py tests/unit/indexed/knowledge/commands/test_create.py`, then full gate.

**Commit:** `fix(config): review-remediation/6 cli values`

---

## review-remediation/7 — Parsing + batch bounds (R12, R14, .tsx)

**Severity:** P2/P3 · **Requirements:** R12, R14, R15(.tsx) · **Deps:** none
**Blocks:** unit 8b (R13 re-wire needs the batch loop fixed first).

**Files**
- modify: `src/indexed/parsing/code_chunker.py` (token bound, accumulator guard, acc_start, `.tsx`); `src/indexed/parsing/plaintext_parser.py` (separator tokens); `src/indexed/parsing/docling_parser.py` (IMAGE format options); `src/indexed/utils/batch.py` (empty-page termination)
- test: `tests/unit/indexed/parsing/test_code_chunker.py`; `.../test_plaintext_parser.py`; `tests/unit/utils/test_batch.py`; new `tests/unit/indexed/parsing/test_docling_parser.py`

**Defect (R12 — CONFIRMED, several repro'd).**
- **R12.1** `code_chunker.py` bounds by `len(text) > self._max_chars` (**:178** node path,
  **:260** line-fallback), `_max_chars = _max_tokens*4` (100-102); it imports only
  `effective_max_tokens` (`:10`) and **never** calls `count_tokens` (grep: 0 hits). Dense
  code under the char bound can exceed the real token window → truncated at embed.
  **Fix:** import `count_tokens` from `._model_window` (`count_tokens(text: str) -> int`,
  already used by `plaintext_parser`) and bound emitted chunks by it.
- **R12.2** accumulator (194-198) has **no** size guard before flush (repro: ~8× over budget).
  **Fix:** guard the accumulator by the same `count_tokens` bound.
- **R12.3** `acc_start or child.start_point[0]` (**:171**, **:210**) drops a legitimate row-0
  `acc_start` (0 is falsy) → `start_line=2, end_line=1` for a file starting at row 0 (repro'd).
  **Fix:** `acc_start if acc_start is not None else …`.
- **R12.4** `plaintext_parser.py:155` counts `count_tokens(piece)` but emits `sep.join(buf)`
  (157/164) without counting separator tokens (repro: 118 tokens vs 50 budget). **Fix:** add
  the separator token cost. ⚠ the sibling `_bound_to_window` word-packing loop (~190-202,
  `" ".join(buf)`) has the **same** undercount — fix it too.
- **R12.5** `utils/batch.py`: `while are_there_more_items_to_read` (**:20**),
  `start_at = start_at + len(items)` (**:65**), `are_there_more = start_at < total` (**:66**).
  An empty non-raising page mid-sequence (`total > start_at`) never advances `start_at` → infinite
  loop (repro'd: 39.8 MB of logs). The `max_skipped_items_in_row` guard is exception-only.
  **Fix:** break (or raise) when `len(items) == 0` and `start_at` is unchanged.

**Defect (R14 — CONFIRMED, moved).** `docling_parser.py` `_ensure_converter` builds
`format_options={InputFormat.PDF: PdfFormatOption(...)}` (**57-61**) while `_supported_extensions`
covers all formats (63-67). Only `PDF`/`IMAGE` use the Pdf pipeline (has `do_ocr`/`do_table_structure`);
`DOCX/PPTX/HTML/XLSX` use `SimplePipeline` (base `PipelineOptions`, **no** such fields).
Real impact: `.png/.jpg/.jpeg/.tiff` (routed here via `router.py` `DOCLING_EXTENSIONS` 45-58)
silently ignore caller `ocr=False`/`table_structure=False`.
**Fix:** add an `InputFormat.IMAGE` entry to `format_options` using the same Pdf pipeline
options. Do **not** attach Pdf options to Simple-pipeline formats (would crash).

**Defect (.tsx — CONFIRMED).** `code_chunker.py:20` `".tsx": "typescript"`; `tree_sitter_typescript`
lacks a `language` attr so it falls to `language_typescript()`, never `language_tsx()` (the
package exposes both). **Fix:** route `.tsx` to the `tsx` grammar (`language_tsx()`).

**Test-first steps** (each RED first)
1. `test_code_chunker.py` — three new tests: (a) a dense node under `_max_chars` but over the
   token window is split (R12.1); (b) 400 tiny statements don't emit one oversized `accumulated`
   chunk (R12.2); (c) a file whose first lines are comments yields `start_line == 0` with
   `start_line <= end_line` (R12.3). Optional: `.tsx` uses the tsx grammar.
2. `test_plaintext_parser.py` — many small pieces joined by a multi-char separator stay within
   the token window (R12.4).
3. `test_batch.py` — an empty page with `total > start_at` mid-sequence **terminates** (use a
   call-count cap so the RED state can't hang the suite) (R12.5). Existing `test_handles_empty_result`
   only covers `total=0`.
4. new `test_docling_parser.py` — an image path with `ocr=False` has the option applied (R14).
5. Implement all. **GREEN.** Full gate → commit.

**Verify:** `uv run pytest -q tests/unit/indexed/parsing/ tests/unit/utils/test_batch.py`, then full gate.

**Commit:** `fix(parsing): review-remediation/7 token bounds`

---

## review-remediation/8a — Secret write atomicity (R11)

**Severity:** P2 · **Requirements:** R11 · **Deps:** none (wave 1)

**Files**
- modify: `src/indexed/config/env_writer.py` — `EnvFileWriter.write`
- test: `tests/unit/indexed/config/test_env_writer.py`

**Defect (R11 — CONFIRMED).** `env_writer.py:write` (32-59): non-atomic truncate at **:58**
(`open(env_path, "w")` + `writelines` — a crash between open and completion leaves an empty
`.env`, destroying stored secrets); and export-blind match at **:47**
(`stripped.startswith(f"{key}=")`/`f"{key} ="`) never matches `export KEY=…`, so updating an
`export`-prefixed key appends a **duplicate** binding (unbounded growth over repeated `config set`).
**Fix:** build lines in memory (already done), then tmp-write → `flush()` + `os.fsync()` →
`os.replace(tmp, env_path)`, unlink tmp on exception — mirror `TomlStore.write` (`store.py:420-432`).
Match keys with `re.match(rf"^(export\s+)?{re.escape(key)}\s*=", stripped)` and **preserve** the
`export ` prefix on rewrite.

**Test-first steps**
1. `test_env_writer.py::TestEnvFileWriterWrite` (has `test_write_updates_existing_key_in_place` ~38-50):
   add `test_write_updates_existing_export_key_in_place` — seed `export JIRA_TOKEN=old\n`, write
   `JIRA_TOKEN=new`, assert `text.count("JIRA_TOKEN") == 1`. **RED** (2 today). Add
   `test_write_is_atomic_on_failure` — seed `OTHER_KEY=keep\n`, make the write raise mid-way,
   assert the original content survives. **RED** (truncated today).
2. Implement atomic write + export-aware regex. **GREEN.** Full gate → commit.

**Verify:** `uv run pytest -q tests/unit/indexed/config/test_env_writer.py`, then full gate.

**Commit:** `fix(config): review-remediation/8 env atomic`

---

## review-remediation/8b — Cloud-reader skip/retry (R13)

**Severity:** P2 · **Requirements:** R13 · **Deps:** **unit 7** (batch loop fixed) **and unit 3** (shares the Confluence reader file). **Wave 2.**

**Files**
- modify: `src/indexed/connectors/jira/async_jira_cloud_reader.py` — `_read_issues_sync`
- modify: `src/indexed/connectors/confluence/async_confluence_cloud_reader.py` — `_read_pages_sync` (+ wrap `requests.get` in `execute_with_retry`)
- reuse: `src/indexed/utils/batch.py::read_items_in_batches`, `src/indexed/utils/retry.py::execute_with_retry`
- test: `tests/unit/indexed/connectors/jira/test_readers.py`; `tests/unit/indexed/connectors/confluence/test_readers*` (+ `tests/unit/indexed/connectors/test_http_retry.py` patterns)

**Defect (R13 — CONFIRMED, OQ1=WIRE).** `max_skipped_items_in_row` is stored but unused in
both async readers (`async_jira_cloud_reader.py:64`, `async_confluence_cloud_reader.py:100`).
Jira's `_read_issues_sync` (106-131) *does* retry per-request via `_post_with_retry` →
`execute_with_retry` (`:154`) but drops **skip-and-continue** (an exhausted-retry raise aborts
the whole read). Confluence's `_read_pages_sync` (**181-238**) calls raw `requests.get` with
**no retry at all**. The utilities are alive and used by the sync/server readers; both
`_read_*_sync` methods are synchronous, so `read_items_in_batches` (sync) can be called directly.
**Fix:** re-wire both `_read_*_sync` loops through `read_items_in_batches` (restores
skip-and-continue honoring `max_skipped_items_in_row`); wrap Confluence's page fetch in
`execute_with_retry` for parity with the sync sibling. **Requires unit 7's `batch.py` fix first**
(otherwise the empty-page infinite loop is imported here).

**Test-first steps**
1. `test_readers.py` (jira) — a page that raises a transient error is skipped-and-logged up to
   `max_skipped_items_in_row`, and the build continues with the remaining pages. **RED.**
2. Confluence reader test — a transient 5xx on one page is retried then skipped; the read does
   not abort with zero docs. **RED.**
3. Implement the re-wire (after unit 7 merged). **GREEN.** Full gate → commit.

**Verify:** `uv run pytest -q tests/unit/indexed/connectors/jira/ tests/unit/indexed/connectors/confluence/ tests/unit/utils/test_batch.py`, then full gate.

**Commit:** `fix(connectors): review-remediation/8 reader skip`

---

## review-remediation/9 — P3 backlog sweep + test hardening (R15)

**Severity:** P3 · **Requirements:** R15 · **Deps:** none (files disjoint from other units after de-collision)
Each item: fix + regression test, **or** convert to a tracked issue, **or** defer with rationale
recorded in the spec `plan.md` Progress notes. None silently dropped.

**Files & items** (all CONFIRMED-AT-HEAD)
- `src/indexed/mcp/tools.py:45` + `src/indexed/mcp/resources.py:96` — broaden `except IndexedError`
  to also envelope non-`IndexedError` (e.g. `AttributeError`) via `mcp_error_envelope`.
  Test: `tests/unit/indexed/mcp/test_error_handling.py` (**exists**).
- `src/indexed/mcp/tools.py:104-108` — kill the fabricated `DEFAULT_INDEXER` fallback that
  swallows any `svc_status` failure; surface not-found/corrupt instead. Test: same file.
- `src/indexed/connectors/_incremental.py:15,46` — `ORDER BY` split ignores quoted literals;
  make it quote-aware. Test: `tests/unit/indexed/connectors/test_incremental.py`.
- `src/indexed/connectors/_url_guard.py:61` — `_client_host` collapses IPv6 (`[::1]`→`[`);
  bracket-aware host parse. Test: `tests/unit/indexed/connectors/test_url_guard.py`.
- `src/indexed/connectors/files/change_tracker.py:435` — `_mtime_changes` `mtime > cutoff` with
  no hash fallback (misses timestamp-preserving edits). Add hash fallback. Test: `tests/unit/indexed/connectors/files/test_change_tracker.py`.
- `src/indexed/connectors/jira/unified_jira_document_converter.py:144-163` — `orderedList` rendered
  as `-` bullets (should be `1. 2. …`); confirm nested-list join separator. Test: `tests/unit/indexed/connectors/jira/test_converters.py`.
- `src/indexed/connectors/jira/connector.py:32` + `src/indexed/connectors/confluence/connector.py:40`
  — hard `rd["baseUrl"]` after a defensive `rd.get("query")`; use `rd.get("baseUrl")` + a mapped
  error. Test: `tests/unit/indexed/connectors/test_from_manifest.py`.
- **e2e hardening** — `tests/fixtures/connectors/stub_routes.py` (no auth-header assertion;
  attachment/redirect routes unregistered), `scripts/connector_stub.py` (`--first-level-comments`
  only → default `read_all_comments=True` untested; no offset), `tests/system/test_connectors_e2e_cli.py`
  (exit-0-only assertions ~163/184/221/242/280/301). Add: auth-header assertion (wrong/missing header
  fails), attachment/redirect coverage, a default-comment-mode test, an offset-aware stub.

> `.tsx` grammar and `logger` markup-swallow are **not** here — reassigned to units 7 and 5
> to keep files disjoint (see de-collision note). `store.py:_env_to_mapping` is in unit 1.

**Test-first steps.** For each fixed item, write the failing test first, then fix, then green.
For any item deferred, open a tracked issue and record the link + rationale in
`.spec/features/review-remediation/plan.md` Progress. Ship the e2e hardening as its own commit.

**Verify:** `uv run pytest -q tests/unit/indexed/mcp/ tests/unit/indexed/connectors/ tests/system/test_connectors_e2e_cli.py`, then full gate.

**Commit(s):** `fix: review-remediation/9 p3 backlog` and `test: review-remediation/9 e2e hardening`

---

## Requirements coverage

| Req | Unit(s) | Req | Unit(s) |
|---|---|---|---|
| R1 | 1 | R9 | 6 |
| R2 | 2 | R11 | 8a |
| R3 | 2 | R12 | 7 |
| R4 | 3 | R13 | 8b |
| R5 | 3 | R14 | 7 |
| R6 | 4 | R15 | 9 (+ `.tsx`→7, `env_to_mapping`→1, `logger`→5) |
| R7 | 5 | | |
| R8 | 6 | | |

All 15 requirements mapped. (R10 is intentionally absent — not assigned in the spec.)

## Self-review checklist (before handing a unit to an executor)

- [ ] Every requirement maps to a unit; no requirement unassigned.
- [ ] Each unit's cited file:line was re-read at HEAD before editing (anchors may have drifted).
- [ ] Each unit writes its regression test **first**, confirms RED, then implements to GREEN.
- [ ] `is not None` (not truthiness) used for the R9 bool guards and R12.3 `acc_start`.
- [ ] R14 adds `InputFormat.IMAGE` only — Simple-pipeline formats untouched.
- [ ] Unit 8b runs only after units 7 and 3 are merged.
- [ ] Full verify gate green before each commit; commit subject ≤50 chars, cites unit ID, no body.
- [ ] `.spec/features/review-remediation/plan.md` Progress table updated as units complete;
      deferrals in unit 9 recorded with issue links.
