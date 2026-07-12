---
type: feature-product
feature: review-remediation
sibling: tech.md
parent: ../../product.md
updated: 2026-07-12
---

# Feature: Review Remediation — Product

Remediation of the defects surfaced by the extra-high-effort code review of
PR #155 (`chore: architecture cleanup and tech debt reduction`). The review ran
14 finder passes + 8 adversarial verifiers + a gap sweep over the changed
`src/indexed/` surface; every requirement below traces to a defect **confirmed
or plausible against real code at HEAD** (many with live repros). This feature
fixes them behind tests. Users are indexed CLI/MCP operators; the output is a
correct, crash-free create/search/config/connector path.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | Fixes at the confirmed defect sites in `src/indexed/config/`, `src/indexed/core/v1/engine/`, `src/indexed/connectors/`, `src/indexed/parsing/`, `src/indexed/mcp/`, `src/indexed/cli/`, `src/indexed/utils/`; regression tests per fix; test-infra hardening under `tests/system/`, `tests/fixtures/connectors/`, `scripts/connector_stub.py` |
| **Does not own** | The v2 core/connectors rewrite; new features; the deferred indexer-factory simplification (Feature 14 note); pure style/formatting; the CodeQL false positives already triaged in the PR |

---

## Requirements

Severity tiers: **P1** = data loss / crash on a common path / silent wrong
output; **P2** = crash or wrong output on a narrower trigger; **P3** =
diagnosability, fidelity, test-coverage. Fix P1 first.

### Requirement: Config writes never truncate the untargeted file (P1)

The system MUST resolve the write target of `config set`/`config delete` with the
**same** workspace-mode resolution used to read the pre-write baseline, so a write
can never land in a different `config.toml` than the one whose contents were
merged.

#### Scenario: local preference set, no local file yet

- **Given** the stored workspace preference is `local` but `./.indexed/config.toml` does not exist
- **When** the user runs `indexed config set core.v1.search.max_docs 5` (no `--local`)
- **Then** the command MUST NOT overwrite `~/.indexed/config.toml` with only the one key, and existing global config (including the `[workspace]` block) MUST survive.

### Requirement: MCP server starts despite malformed config (P1)

The system MUST NOT crash `indexed-mcp run` on a malformed `config.toml`; lifespan
config resolution MUST degrade to defaults the same way `_get_config()` already does.

#### Scenario: syntactically invalid global config

- **Given** `~/.indexed/config.toml` contains a TOML syntax error
- **When** the user runs `indexed-mcp run`
- **Then** the server MUST start (falling back to defaults) instead of raising `TOMLDecodeError` out of `lifespan()`.

### Requirement: Missing collections dir is empty, not an error (P1)

The system MUST treat a non-existent collections directory (fresh install) as
"no collections" and MUST reserve the fail-loud path for genuine I/O errors
(e.g. `EACCES`), distinguishing `ENOENT` from real failures.

#### Scenario: fresh global install

- **Given** a fresh install where `~/.indexed/data/collections/` was never created and `indexed init` was not run
- **When** the user runs `indexed inspect` or `indexed index search "q"` (no `--collection`)
- **Then** the command MUST report an empty/no-collections result with exit 0, not exit non-zero with "Could not scan collections directory".

### Requirement: Confluence async fetch tolerates task cancellation (P1)

The system MUST check `isinstance(result, BaseException)` (not `Exception`) when
handling `asyncio.gather(return_exceptions=True)` results in the Confluence cloud
reader's comment and attachment fetch, matching the outline reader's fix, so a
`CancelledError` is never stored into the document as data.

#### Scenario: a fetch subtask is cancelled

- **Given** a comment- or attachment-fetch subtask is cancelled (timeout/shutdown) during indexing
- **When** the gather result is processed and later iterated by the converter
- **Then** the reader MUST route the `CancelledError` to the failure branch (log + default to `[]`), never store it as the `comments`/`attachments` value where `for x in …` would raise `TypeError`.

### Requirement: Jira Cloud listing guards a None response (P1)

The system MUST guard the `enhanced_jql()` result against `None` before
subscripting, consistent with the `jql()` sibling call sites' `or {}` fallback.

#### Scenario: empty-body response from the search API

- **Given** `enhanced_jql()` returns `None` (empty-body 200/204)
- **When** the Jira Cloud reader lists issues
- **Then** it MUST treat it as an empty page, not raise `AttributeError: 'NoneType' object has no attribute 'get'` and abort the whole listing.

### Requirement: Document cache invalidates on parse-setting change (P1)

The system MUST include the parse-affecting settings (OCR, table-structure,
max-chunk-tokens) in the document cache key, so re-parsing with changed settings
never serves stale, differently-chunked cached documents.

#### Scenario: recreate with a different chunk size

- **Given** a collection cached over a source path with `max_chunk_tokens=512`, then config changed to `2048`
- **When** the user re-creates the collection without `--force`
- **Then** the reader MUST re-parse (cache miss on the changed setting), not serve the old 512-token cached documents.

### Requirement: User-controlled strings never break Rich rendering (P1)

The system MUST NOT let user-controlled strings (search query, collection name,
config values, file paths, tracebacks) be parsed as Rich markup; escape them or
disable markup on the sinks that render them.

#### Scenario: search query containing brackets

- **Given** the user runs `indexed index search "list[int]"` (or `"proj[/status]"`)
- **When** the progress UI renders the query
- **Then** it MUST render the literal query (no dropped `[int]`, no `MarkupError`).

#### Scenario: config value containing brackets

- **Given** a stored config value like `project = ABC AND status[/done]`
- **When** the user runs `indexed config list`
- **Then** the value panel MUST render it literally, not raise `MarkupError`.

### Requirement: `config list` shows manually-set values (P2)

The system MUST display a non-default value set via `config set` in a plain
`config list`, regardless of `--show-defaults`.

#### Scenario: set then list

- **Given** the user ran `indexed config set core.v1.indexing.chunk_size 256`
- **When** they run plain `indexed config list`
- **Then** the Core Settings panel MUST show `chunk_size = 256`, not hide it behind `--show-defaults`.

### Requirement: config.toml boolean values take effect (P2)

The system MUST let a boolean value in `config.toml` (`respect_gitignore`,
`include_attachments`, `ocr`, `read_all_comments`) take effect when the user did
not pass the corresponding CLI flag — CLI overrides MUST reflect only
user-supplied flags.

#### Scenario: gitignore disabled in config

- **Given** `[sources.files] respect_gitignore = false` in config.toml and no `--respect-gitignore/--no-respect-gitignore` flag passed
- **When** the user runs `indexed index create files …`
- **Then** gitignore MUST be honored as `false`, not forced back to the Typer default `true`.

### Requirement: Secret file writes are atomic (P2)

The system MUST write `.env` atomically (temp-write → replace), matching the
atomic `config.toml` write, so a crash mid-write cannot destroy stored secrets.

#### Scenario: crash during credential save

- **Given** a `config set sources.jira.api_token …` writing `.env`
- **When** the process is killed between truncation and completion
- **Then** the previously stored secrets MUST survive (no empty/half-written `.env`).

### Requirement: Chunkers never exceed the token window (P2)

The system MUST bound emitted chunks by the real tokenizer (`count_tokens`), not a
`chars ≈ tokens*4` heuristic, and MUST bound the between-nodes accumulator, so no
chunk is silently truncated at embed time. Chunk `start_line` metadata MUST be
correct for text beginning at row 0.

#### Scenario: dense code under the char limit

- **Given** a code node under `max_tokens*4` chars but over the real token window
- **When** the chunker emits it
- **Then** it MUST be split to fit the token window, not emitted whole and truncated at embed.

### Requirement: Batch pagination cannot loop forever (P2)

The system MUST terminate the batch loop when a page returns zero items without
advancing the offset (empty non-raising page with `total > start_at`).

#### Scenario: empty page mid-range

- **Given** `read_batch_func` returns `items=[]` with `total > start_at` without raising
- **When** the batch loop runs
- **Then** it MUST break (or advance/guard) rather than re-issue the identical request indefinitely.

### Requirement: Cloud readers tolerate transient errors and bad pages (P2)

The system MUST either wire `max_skipped_items_in_row` to a real skip-and-continue
+ retry path in the Jira/Confluence async cloud readers, or remove the dead
parameter — a transient 5xx/429 or one bad page MUST NOT silently abort the whole
index build while the constructor implies tolerance.

#### Scenario: one bad page in a large space

- **Given** a large Jira/Confluence space where one page triggers a transient error
- **When** `read_all_documents()` runs
- **Then** the reader MUST skip-and-log up to the configured tolerance and continue, not abort with zero documents.

### Requirement: docling applies parse options to all formats (P3)

The system MUST apply the requested `do_ocr`/`do_table_structure` options to every
format it parses, not only `InputFormat.PDF`.

#### Scenario: OCR requested on a docx

- **Given** `ocr=True` and a `.docx`/`.pptx` input
- **When** docling parses it
- **Then** the OCR/table options MUST be applied, not silently limited to PDF.

### Requirement: Lower-severity correctness and coverage backlog (P3)

The system SHOULD address the narrower-trigger and diagnosability defects and the
false-green test gaps catalogued in [tech.md](tech.md) § Lower-Severity Backlog:
MCP handlers catching only `IndexedError`; `search_collection`'s fabricated
`DEFAULT_INDEXER` fallback; env `INDEXED__A` scalar-vs-nested order-dependence;
`_incremental` splitting on `order by` inside quoted literals; `_url_guard` IPv6
host collapse; `change_tracker` mtime-only miss; logger swallowing bracketed
tracebacks; `.tsx` using the plain TypeScript grammar; `env_writer` `export KEY=`
duplication; Jira ADF nested/ordered-list join fidelity; `*_from_manifest` hard
`baseUrl` `KeyError`; and connector e2e gaps (no auth-header assertion, attachment
/redirect paths unexercised, default comment-mode untested, stub ignores offset).

#### Scenario: catalogue is addressed or explicitly deferred

- **Given** the P3 catalogue in tech.md
- **When** this feature wraps up
- **Then** each item MUST be fixed, converted to a tracked issue, or explicitly deferred with rationale — none silently dropped.

---

## Non-Goals

- The v2 core/connectors rewrite (separate horizon; do not fold fixes into a rewrite).
- New features or behavior changes beyond making the documented behavior correct.
- Re-litigating the CodeQL false positives already triaged in PR #155.
- The deferred indexer-factory/registry simplification (Feature 14 decision stands).
