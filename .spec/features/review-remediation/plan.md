---
type: feature-plan
feature: review-remediation
sibling: tech.md
parent: ../../plan.md
updated: 2026-07-12
---

# Feature: Review Remediation — Implementation Plan

Fix the confirmed PR #155 review defects behind regression tests. Units are
grouped by defect cluster and are **mostly independent** (touch disjoint files),
so they can be tackled in parallel in the cloud. Sequence is by severity: P1 data
loss / crash / silent-wrong first, then P2, then the P3 backlog. Each unit is a
green commit that runs the full verify gate.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Starts now — Feature 14 (Simplify) is `DONE`. Depends on no other
feature's units; every fix site already exists on `chore/architecture-cleanup`.

---

## Problem Frame

An extra-high-effort review of PR #155 (14 finders + 8 adversarial verifiers +
gap sweep) confirmed a set of defects the refactor introduced or left latent:
three P1 crashes/data-loss on common paths (config truncation, MCP won't start on
bad config, fresh-install inspect/search crash), three P1 silent-wrong/crash
connector+cache defects, a systemic Rich-markup crash on ordinary input, plus P2
config/parsing/atomicity bugs and a P3 correctness+coverage tail. These are point
fixes on stable surface — the value is fixing each behind a test so the next
refactor can't silently reintroduce it. Units are ordered by blast radius, not by
file.

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Config writes never truncate the untargeted file](product.md#requirement-config-writes-never-truncate-the-untargeted-file-p1) | review-remediation/1 |
| R2 | [MCP server starts despite malformed config](product.md#requirement-mcp-server-starts-despite-malformed-config-p1) | review-remediation/2 |
| R3 | [Missing collections dir is empty, not an error](product.md#requirement-missing-collections-dir-is-empty-not-an-error-p1) | review-remediation/2 |
| R4 | [Confluence async fetch tolerates task cancellation](product.md#requirement-confluence-async-fetch-tolerates-task-cancellation-p1) | review-remediation/3 |
| R5 | [Jira Cloud listing guards a None response](product.md#requirement-jira-cloud-listing-guards-a-none-response-p1) | review-remediation/3 |
| R6 | [Document cache invalidates on parse-setting change](product.md#requirement-document-cache-invalidates-on-parse-setting-change-p1) | review-remediation/4 |
| R7 | [User-controlled strings never break Rich rendering](product.md#requirement-user-controlled-strings-never-break-rich-rendering-p1) | review-remediation/5 |
| R8 | [config list shows manually-set values](product.md#requirement-config-list-shows-manually-set-values-p2) | review-remediation/6 |
| R9 | [config.toml boolean values take effect](product.md#requirement-configtoml-boolean-values-take-effect-p2) | review-remediation/6 |
| R11 | [Secret file writes are atomic](product.md#requirement-secret-file-writes-are-atomic-p2) | review-remediation/8 |
| R12 | [Chunkers never exceed the token window](product.md#requirement-chunkers-never-exceed-the-token-window-p2) | review-remediation/7 |
| R13 | [Cloud readers tolerate transient errors and bad pages](product.md#requirement-cloud-readers-tolerate-transient-errors-and-bad-pages-p2) | review-remediation/7, review-remediation/8 |
| R14 | [docling applies parse options to all formats](product.md#requirement-docling-applies-parse-options-to-all-formats-p3) | review-remediation/7 |
| R15 | [Lower-severity correctness and coverage backlog](product.md#requirement-lower-severity-correctness-and-coverage-backlog-p3) | review-remediation/9 |

R12 covers `utils/batch.py` (the batch infinite-loop) as well as the chunkers.

---

## Key Technical Decisions

1. **Single fix point for fresh-install (R3).** The CLI crash for both `inspect` and
   `search` flows through `InspectService._discover_collections`; fix ENOENT there, not in
   the dead-for-CLI `SearchService._discover_collections`. Also add the staging-dir filter
   to the search-service discover for the MCP/functional path (P3).
2. **Fix R7 at altitude, not per-print.** Prefer a shared `Text()`/`markup=False` render seam
   + one user-data escaping helper over scattering `escape()` at ~8 call sites. Promote to
   root tech.md only if it lands as a seam.
3. **R13 wire-or-delete is a decision, not a default.** Resolve Open Question 1 before coding
   unit 8's reader half — re-wire skip/retry (restores documented tolerance) or delete the
   dead param.
4. **Every unit ships a red→green regression test.** The defects were confirmed with concrete
   triggers; encode each trigger as the test.

---

## Unit IDs

Units are `review-remediation/n`, assigned once and never renumbered. Seq is execution
order; most units are independent (disjoint files) and can run in parallel. Cite IDs in
commits (`fix(config): review-remediation/1 …`).

---

### review-remediation/1 — Config write-target parity

**Severity:** P1 · **Goal:** `config set`/`config delete` write to the same file its baseline was read from.

**Requirements:** R1

**Dependencies:** —

**Files:**

```
src/indexed/config/store.py       # _resolve_write_target: use the stored workspace preference
src/indexed/config/service.py     # thread resolved mode from _disk_baseline if needed
```

**Test scenarios:**

- Stored preference `local`, no local file; `config set` a key; existing global keys + `[workspace]` survive.
- Mirror: preference `global` with a local file present; write targets the intended file.

**Verification:** new regression test in `tests/unit/indexed/config/`; full config suite green.

---

### review-remediation/2 — Graceful missing/broken config

**Severity:** P1 · **Goal:** MCP starts on malformed config; `inspect`/`search` treat a missing collections dir as empty.

**Requirements:** R2, R3

**Dependencies:** —

**Files:**

```
src/indexed/mcp/server.py                                # guard lifespan config load like _get_config
src/indexed/core/v1/engine/services/inspect_service.py   # ENOENT -> empty, other OSError -> StorageError
src/indexed/core/v1/engine/persisters/disk_persister.py  # distinguish ENOENT in _raise_on_error / read_folder_files
```

**Test scenarios:**

- Malformed global `config.toml` → `indexed-mcp run` lifespan yields (defaults), no `TOMLDecodeError`.
- Fresh install, missing `~/.indexed/data/collections/` → `indexed inspect` and `indexed index search "q"` exit 0 with empty result.
- A permission (`EACCES`) error still raises `StorageError` (fail-loud preserved).

**Verification:** system tests for both entrypoints; existing fail-loud unit test still green.

---

### review-remediation/3 — Connector crash guards

**Severity:** P1 · **Goal:** Confluence async fetch tolerates `CancelledError`; Jira `enhanced_jql` None is safe.

**Requirements:** R4, R5

**Dependencies:** —

**Files:**

```
src/indexed/connectors/confluence/async_confluence_cloud_reader.py  # isinstance(..., BaseException) at both gather loops
src/indexed/connectors/jira/unified_jira_document_reader.py         # enhanced_jql(...) or {}; audit approximate_issue_count
```

**Test scenarios:**

- Confluence gather returns a `CancelledError` → routed to failure branch, `comments`/`attachments` default to `[]`, converter does not raise `TypeError`.
- `enhanced_jql` returns `None` → empty page, no `AttributeError`, listing continues.

**Verification:** unit tests in `tests/unit/indexed/connectors/{confluence,jira}/`.

---

### review-remediation/4 — Cache-key parse settings

**Severity:** P1 · **Goal:** Changing OCR/table/max-chunk-tokens invalidates the document cache.

**Requirements:** R6

**Dependencies:** —

**Files:**

```
src/indexed/connectors/files/files_document_reader.py         # get_reader_details includes ocr/table/max_tokens
src/indexed/connectors/document_cache_reader_decorator.py     # (verify key input covers them)
```

**Test scenarios:**

- Two readers over the same path differing only in `max_tokens` → distinct `__build_cache_key`.
- Re-create without `--force` after a chunk-size change → cache miss, re-parse.

**Verification:** unit test on `get_reader_details`/`__build_cache_key`; cache decorator tests green.

---

### review-remediation/5 — Rich markup safety

**Severity:** P1 · **Goal:** No user-controlled string can raise `MarkupError` or be silently mangled.

**Requirements:** R7

**Dependencies:** —

**Files:**

```
src/indexed/cli/utils/progress_bar.py                 # query/collection via Text()/escape
src/indexed/cli/utils/components/key_value_panel.py    # wrap cells in Text()
src/indexed/cli/utils/storage_info.py                  # path via Text()/escape
src/indexed/cli/init.py                                # model name via Text()/escape
src/indexed/utils/logger.py                            # rich sink markup=False
src/indexed/cli/utils/console.py                       # (optional) central render seam
```

**Test scenarios:**

- `indexed index search "list[int]"` and `"proj[/status]"` render literally, no `MarkupError`.
- `config list` with a value containing `[` renders literally.
- A traceback containing bracketed reprs is shown in full (logger does not swallow).

**Verification:** unit tests per sink; a shared test asserting bracketed input never raises.

---

### review-remediation/6 — Config CLI correctness

**Severity:** P2 · **Goal:** `config list` shows manually-set values; config.toml bools take effect.

**Requirements:** R8, R9

**Dependencies:** —

**Files:**

```
src/indexed/config/commands/_render.py                        # render panel when it has non-default rows
src/indexed/cli/knowledge/commands/_create_options.py         # Optional[bool] defaults None
src/indexed/cli/knowledge/commands/_create_commands.py        # add to cli_overrides only when not None
```

**Test scenarios:**

- `config set core.v1.indexing.chunk_size 256` then plain `config list` shows it.
- `[sources.files] respect_gitignore = false` + no flag → honored on `create`.

**Verification:** unit tests in `tests/unit/indexed/config/` and `.../knowledge/commands/`.

---

### review-remediation/7 — Parsing + batch bounds

**Severity:** P2/P3 · **Goal:** Chunks fit the real token window; batch loop can't spin; docling options apply to all formats.

**Requirements:** R12, R14, R13 (batch half)

**Dependencies:** —

**Files:**

```
src/indexed/parsing/code_chunker.py       # count_tokens bound; guard accumulator; acc_start is-not-None; .tsx grammar (P3)
src/indexed/parsing/plaintext_parser.py    # count join separators
src/indexed/parsing/docling_parser.py      # format_options for all supported formats
src/indexed/utils/batch.py                 # break/guard on empty non-advancing page
```

**Test scenarios:**

- Dense code node over the token window is split, not truncated at embed.
- Leading-row-0 accumulated chunk reports `start_line == 0`.
- `read_batch_func` returns empty items with `total > start_at` → loop terminates.
- Non-PDF path with `ocr=True` receives the OCR option.

**Verification:** parsing unit tests; `tests/unit/utils/test_batch.py` extended.

---

### review-remediation/8 — Secret atomicity + cloud reader tolerance

**Severity:** P2 · **Goal:** `.env` writes atomically; cloud readers tolerate transient errors / bad pages (or drop the dead param).

**Requirements:** R11, R13

**Dependencies:** review-remediation/7 (batch loop fix, if re-wiring `read_items_in_batches`)

**Files:**

```
src/indexed/config/env_writer.py                              # atomic tmp->replace; export-prefix match (P3)
src/indexed/connectors/jira/async_jira_cloud_reader.py        # wire-or-delete skip/retry
src/indexed/connectors/confluence/async_confluence_cloud_reader.py  # wire-or-delete skip/retry
```

**Test scenarios:**

- Kill-sim between truncate and write leaves `.env` intact; updating an `export KEY=` line replaces in place.
- (If re-wired) one transient-error page is skipped-and-logged; build continues. (If deleted) dead param removed, docstring/signature updated.

**Verification:** env_writer unit test; connector reader tests; resolve Open Question 1 first.

---

### review-remediation/9 — P3 backlog sweep + test hardening

**Severity:** P3 · **Goal:** Fix, ticket, or explicitly defer every P3 catalogue item; close the false-green e2e gaps.

**Requirements:** R15

**Dependencies:** —

**Files:**

```
src/indexed/mcp/tools.py, src/indexed/mcp/resources.py        # broaden error handling; kill fabricated fallback
src/indexed/config/store.py                                   # _env_to_mapping scalar-vs-nested order
src/indexed/connectors/_incremental.py                        # quote-aware order-by split
src/indexed/connectors/_url_guard.py                          # IPv6 bracket-aware host parse
src/indexed/connectors/files/change_tracker.py                # mtime hash fallback
src/indexed/connectors/jira/unified_jira_document_converter.py# ordered/nested list joins
src/indexed/connectors/{jira,confluence}/connector.py         # rd.get("baseUrl") + mapped error
scripts/connector_stub.py, tests/fixtures/connectors/stub_routes.py, tests/system/test_connectors_e2e_cli.py  # auth-header assert, attachment/redirect + default-comment coverage, offset-aware stub
```

**Test scenarios:**

- Each fixed item gets a regression test; each deferred item gets a tracked issue link recorded here.
- e2e stub asserts the auth header; a wrong/missing header fails the test.

**Verification:** per-item tests; `bash .agents/skills/spec/scripts/validate.sh` clean; document deferrals in Progress notes.

---

## Progress

| Unit | Seq | Status |
|---|---|---|
| review-remediation/1 | 1 | NOT STARTED |
| review-remediation/2 | 2 | NOT STARTED |
| review-remediation/3 | 3 | NOT STARTED |
| review-remediation/4 | 4 | NOT STARTED |
| review-remediation/5 | 5 | NOT STARTED |
| review-remediation/6 | 6 | NOT STARTED |
| review-remediation/7 | 7 | NOT STARTED |
| review-remediation/8 | 8 | NOT STARTED |
| review-remediation/9 | 9 | NOT STARTED |

---

## Open Questions

1. **R13 wire-or-delete** (see tech.md Open Question 1) — re-wire `max_skipped_items_in_row`
   skip/retry, or delete the dead param and accept fail-fast? Blocks unit 8's reader half.
2. **R7 scope** — central render seam vs per-site escaping. Recommendation: seam for the logger
   + one user-data helper, then convert call sites in unit 5.
