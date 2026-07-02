---
type: feature-plan
feature: architecture-audit
sibling: tech.md
parent: ../../plan.md
updated: 2026-06-29
---

# Feature: Architecture Audit — Implementation Plan

Remediates structural debt found in the 2026-06-29 monorepo audit in four phases:
fix the dependency graph (protocols package, drop core→connectors), unify app
bootstrap and storage-path resolution, clean config/retry/dead-code hygiene, then
lock the result with import-graph CI and a characterization baseline. Each unit
is a small, verifiable slice; phases gate on the prior phase completing.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)
**Research:** [research/app.md](research/app.md) · [research/core.md](research/core.md) · [research/connectors.md](research/connectors.md) · [research/config.md](research/config.md) · [research/parsing-utils.md](research/parsing-utils.md) · [research/systemic.md](research/systemic.md)

**Feature gate:** Starts now — depends only on shipped v0.1.0 infra (all `DONE` in
root [plan.md](../../plan.md)). Does not block on v2 engine rewrite or issue #119.

---

## Problem Frame

The audit found upward imports (core→connectors), protocols living in the engine
package, triple connector instantiation paths, divergent CLI/MCP storage resolution,
import-time config registration and logging, a legacy config merge path, and
speculative dead code. These violate [tech.md](../../tech.md) § Architectural Rules
and block a clean v2 scaffold. Units are ordered so the graph is fixed before
behavior moves (bootstrap, context), hygiene before service consolidation, and CI
validation last so regressions are caught immediately.

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Downward-only dependency graph](product.md#requirement-downward-only-dependency-graph) | architecture-audit/1, architecture-audit/2, architecture-audit/12 |
| R2 | [Protocols in lowest shared package](product.md#requirement-protocols-in-lowest-shared-package) | architecture-audit/1 |
| R3 | [CLI and MCP storage path parity](product.md#requirement-cli-and-mcp-storage-path-parity) | architecture-audit/4 |
| R4 | [Single-source config resolution everywhere](product.md#requirement-single-source-config-resolution-everywhere) | architecture-audit/5, architecture-audit/6 |
| R5 | [Explicit app bootstrap](product.md#requirement-explicit-app-bootstrap) | architecture-audit/3, architecture-audit/5, architecture-audit/9 |
| R6 | [IndexedError at app boundaries](product.md#requirement-indexederror-at-app-boundaries) | architecture-audit/11 |
| R7 | [Connector registry single path](product.md#requirement-connector-registry-single-path) | architecture-audit/3, architecture-audit/10 |
| R8 | [HTTP retry policy consistent](product.md#requirement-http-retry-policy-consistent) | architecture-audit/7 |
| R9 | [Delete speculative/unused code](product.md#requirement-delete-speculativeunused-code) | architecture-audit/8 |
| R10 | [File size compliance on touched modules](product.md#requirement-file-size-compliance-on-touched-modules) | architecture-audit/3, architecture-audit/4, architecture-audit/10, architecture-audit/11 |
| R11 | [v2 scaffold prerequisites](product.md#requirement-v2-scaffold-prerequisites) | architecture-audit/1, architecture-audit/12 |

Every unit below cites the R-IDs it satisfies.

---

## Key Technical Decisions

1. **New `indexed-protocols` package.** Lowest layer for `BaseConnector`,
   `ConnectorMetadata`, `SourceConfig`, and progress types — both core and
   connectors depend on it; neither depends on the other. See [tech.md](tech.md)
   § Target dependency graph.
2. **App is the composition root.** `bootstrap.py` registers config specs and
   wires the connector registry once; core services receive connectors via
   injection, never import `connectors.*`.
3. **`resolve_collections_context()` is the single storage-path API.** CLI and MCP
   both call it; no ad-hoc `resolve_preferred_collections_path()` heuristics or
   hardcoded `localFiles` defaults in MCP tools.
4. **`read_for_mode()` only; delete merge path.** `TomlStore.read()` merge
   behaviour is removed; all callers go through resolved mode + `read_for_mode()`.
5. **Transient-only HTTP retry.** One policy in `utils/retry.py` (or
   `connectors/http.py` wrapper); retries only on 429/502/503/504 and network
   errors, not on 4xx client failures.
6. **R10 on every touched file.** New/changed modules stay within limits from
   [tech.md](../../tech.md) § File Size Limits (CLI ≤150, service ≤300, module ≤400).

---

## Unit IDs

Units are `architecture-audit/n`, assigned once and never renumbered. Cite in
commits (`refactor(core): architecture-audit/2 ...`).

**Phase 0 — graph:** /1 → /2 → /3 → /4
**Phase 1 — hygiene:** /5 → /6 → /7 → /8
**Phase 2 — services:** /9 → /10 → /11
**Phase 3 — validation:** /12

---

### architecture-audit/1 — indexed-protocols package + move protocols

**Goal:** Create `packages/indexed-protocols/` and relocate shared connector
protocols and DTOs from core so both core and connectors can import them without
creating an upward edge.

**Requirements:** R1, R2, R11

**Dependencies:** —

**Files:**

```
packages/indexed-protocols/pyproject.toml              # NEW workspace member
packages/indexed-protocols/src/protocols/__init__.py   # NEW public exports
packages/indexed-protocols/src/protocols/base.py       # BaseConnector, DocumentReader, DocumentConverter
packages/indexed-protocols/src/protocols/metadata.py   # ConnectorMetadata
packages/indexed-protocols/src/protocols/models.py     # SourceConfig, ProgressUpdate, ProgressCallback
pyproject.toml                                         # add workspace member + uv sources
packages/indexed-core/src/core/v1/connectors/          # re-export or delete after move
packages/indexed-connectors/src/connectors/            # update imports to protocols.*
tests/unit/indexed_protocols/                            # NEW protocol conformance tests
```

**Test scenarios:**

- `BaseConnector` remains `@runtime_checkable`; existing connector classes still
  satisfy the protocol after import path change.
- `SourceConfig` validates the same literal types (`jira`, `localFiles`, etc.).
- `indexed-core` and `indexed-connectors` both resolve `indexed-protocols` from
  the workspace without adding a core↔connectors dependency.

**Verification:** `uv sync --all-groups && uv run pytest tests/unit/indexed_protocols/ -q && uv run mypy src/`

---

### architecture-audit/2 — Remove core→connectors dep, fix pyproject

**Goal:** Drop `indexed-connectors` from `indexed-core` dependencies; core imports
only `protocols` and receives concrete connectors via injection from the app layer.

**Requirements:** R1

**Dependencies:** architecture-audit/1

**Files:**

```
packages/indexed-core/pyproject.toml                           # remove indexed-connectors dep
packages/indexed-core/src/core/v1/engine/services/collection_service.py  # remove connectors.* imports
packages/indexed-core/src/core/v1/engine/factories/update_collection_factory.py
apps/indexed/pyproject.toml                                    # ensure connectors dep stays on app
tests/unit/indexed_core/test_import_isolation.py               # NEW — core must not import connectors
```

**Test scenarios:**

- `grep -r "from connectors" packages/indexed-core/` returns zero hits (except
  comments/strings in migration notes, if any).
- `collection_service` module imports without `indexed-connectors` installed in
  an isolated check (protocols-only stub).
- Full test suite still passes with connectors wired at app boundary.

**Verification:** `uv run pytest tests/unit/indexed_core/test_import_isolation.py -q && uv run mypy src/`

---

### architecture-audit/3 — App bootstrap + connector registry only

**Goal:** Add explicit `bootstrap.py` that registers all config specs and exposes
the connector registry; remove import-time registration from library packages.

**Requirements:** R5, R7, R10

**Dependencies:** architecture-audit/2

**Files:**

```
apps/indexed/src/indexed/bootstrap.py                # NEW register_config(), get_connector_registry()
apps/indexed/src/indexed/app.py                      # call bootstrap in callback / entry
apps/indexed/src/indexed/mcp/server.py               # call bootstrap in lifespan
packages/indexed-connectors/src/connectors/registry.py  # build_connector_from_config() entry
tests/unit/indexed/test_bootstrap.py                 # NEW
```

**Test scenarios:**

- Importing `core.v1` or `indexed_config` alone does not register config specs.
- `bootstrap.register_config(ConfigService.instance())` registers MCP, core v1,
  and source specs exactly once (idempotent).
- `get_connector_class("jiraCloud")` resolves via registry after bootstrap; unknown
  type raises `ValueError` with available types listed.

**Verification:** `uv run pytest tests/unit/indexed/test_bootstrap.py -q && uv run indexed --help`

---

### architecture-audit/4 — resolve_collections_context CLI+MCP

**Goal:** Introduce `resolve_collections_context()` as the single API for storage
mode, collections path, and caches path; wire CLI commands and MCP tools to use it.

**Requirements:** R3, R10

**Dependencies:** architecture-audit/3

**Files:**

```
apps/indexed/src/indexed/runtime.py                    # NEW resolve_collections_context()
apps/indexed/src/indexed/app.py                        # pass ctx into context helper
apps/indexed/src/indexed/knowledge/commands/search.py  # replace resolve_preferred_collections_path
apps/indexed/src/indexed/knowledge/commands/inspect.py
apps/indexed/src/indexed/knowledge/commands/_create_helpers.py
apps/indexed/src/indexed/mcp/tools.py                  # pass collections_path; drop hardcoded localFiles
apps/indexed/src/indexed/utils/storage_info.py         # delegate to runtime helper
tests/unit/indexed/test_runtime_context.py             # NEW CLI vs MCP parity tests
tests/system/test_mcp_storage_parity.py                # NEW — MCP uses same path as CLI --local
```

**Test scenarios:**

- Given `--local`, both CLI search and MCP `search()` read from `./.indexed/data/collections`.
- Given global mode, both surfaces use `~/.indexed/data/collections`.
- MCP `search_collection` no longer hardcodes `localFiles` source type; uses manifest
  metadata or omits type filter.
- `ctx.obj["mode_override"]` from CLI flag flows into context resolution (fixes
  display-only `--local` bug).

**Verification:** `uv run pytest tests/unit/indexed/test_runtime_context.py tests/system/test_mcp_storage_parity.py -q`

---

### architecture-audit/5 — Remove import-time config registration

**Goal:** Delete import-time `ConfigService.register()` calls from `core.v1.__init__`,
MCP `_get_*_config()` helpers, and any package `__init__.py`; all registration
goes through `bootstrap.register_config()`.

**Requirements:** R4, R5

**Dependencies:** architecture-audit/4

**Files:**

```
packages/indexed-core/src/core/v1/__init__.py        # remove try/register block
apps/indexed/src/indexed/mcp/server.py               # remove _get_mcp_config register side effects
apps/indexed/src/indexed/mcp/config.py
apps/indexed/src/indexed/bootstrap.py                # owns all register() calls
tests/unit/indexed/test_bootstrap.py                 # extend — import core.v1 is side-effect free
```

**Test scenarios:**

- `import core.v1` does not mutate `ConfigService.instance()._registry`.
- MCP lifespan loads config from pre-registered specs after bootstrap, not inline
  register-on-read.
- `indexed init` and `indexed index search` still resolve config after bootstrap.

**Verification:** `uv run pytest tests/unit/indexed/test_bootstrap.py tests/unit/indexed_config/ -q && uv run mypy src/`

---

### architecture-audit/6 — Unify config read_for_mode (drop merge path)

**Goal:** Route all config reads through `TomlStore.read_for_mode(resolved_mode)`;
remove or deprecate the global/local merge path in `TomlStore.read()`.

**Requirements:** R4

**Dependencies:** architecture-audit/5

**Files:**

```
packages/indexed-config/src/indexed_config/store.py       # remove merge branch from read()
packages/indexed-config/src/indexed_config/service.py     # bind() always uses read_for_mode
packages/indexed-config/src/indexed_config/workspace.py     # single mode resolution entry
tests/unit/indexed_config/test_toml_store.py                # drop merge tests; add no-merge guard
tests/unit/indexed_config/test_service.py
```

**Test scenarios:**

- `read_for_mode("local")` returns only `./.indexed/config.toml` values (global
  TOML keys absent unless env-overridden).
- `ConfigService.instance(mode_override="local")` after first global call respects
  override (singleton mode fix).
- No production caller invokes `TomlStore.read()` merge path; grep confirms zero
  external `store.read()` without mode.

**Verification:** `uv run pytest tests/unit/indexed_config/ -q && uv run mypy src/`

---

### architecture-audit/7 — Consolidate HTTP retry

**Goal:** Single transient-only retry policy shared by Jira and Confluence readers;
stop retrying permanent 4xx errors.

**Requirements:** R8

**Dependencies:** architecture-audit/6

**Files:**

```
packages/utils/src/utils/retry.py                                    # add is_transient_http_error()
packages/indexed-connectors/src/connectors/http.py                   # NEW optional thin wrapper
packages/indexed-connectors/src/connectors/jira/unified_jira_document_reader.py
packages/indexed-connectors/src/connectors/confluence/confluence_document_reader.py
packages/indexed-connectors/src/connectors/confluence/confluence_cloud_document_reader.py
tests/unit/utils/test_retry.py                                       # transient vs permanent cases
tests/unit/indexed_connectors/test_http_retry.py                       # NEW reader integration mocks
```

**Test scenarios:**

- 401/403/404 failures fail fast without retry (mocked HTTP client).
- 429/503 failures retry with backoff; honour `Retry-After` when present.
- Network timeout (`ConnectionError`) retries; validation error (`ValueError`) does not.

**Verification:** `uv run pytest tests/unit/utils/test_retry.py tests/unit/indexed_connectors/test_http_retry.py -q`

---

### architecture-audit/8 — Delete speculative code (FaissAutoIndexer, wrappers, dead DTOs)

**Goal:** Remove unused engine variants, deprecated Jira/Confluence wrapper classes,
registry dict wrappers, and dead DTOs identified in the audit.

**Requirements:** R9, R10

**Dependencies:** architecture-audit/7

**Files:**

```
packages/indexed-core/src/core/v1/engine/indexes/indexers/faiss_auto_indexer.py  # DELETE
packages/indexed-core/src/core/v1/engine/indexes/indexer_factory.py              # FaissIndexer only
packages/indexed-connectors/src/connectors/jira/jira_document_reader.py          # DELETE deprecated
packages/indexed-connectors/src/connectors/jira/jira_cloud_document_reader.py
packages/indexed-connectors/src/connectors/jira/jira_document_converter.py
packages/indexed-connectors/src/connectors/jira/jira_cloud_document_converter.py
packages/indexed-connectors/src/connectors/confluence/confluence_document_converter.py
packages/indexed-connectors/src/connectors/confluence/confluence_cloud_document_converter.py
packages/indexed-connectors/src/connectors/jira/__init__.py                      # drop re-exports
packages/indexed-connectors/src/connectors/confluence/__init__.py
tests/                                                                             # remove/adjust imports of deleted symbols
```

**Test scenarios:**

- Indexer factory always returns `FaissIndexer`; no code path references
  `FaissAutoIndexer`.
- Jira/Confluence connectors instantiate unified reader/converter only; importing
  deleted wrapper modules fails (module not found).
- Full suite passes; coverage remains >85%.

**Verification:** `uv run pytest -q --cov=src && uv run ruff check . --fix && uv run ruff format`

---

### architecture-audit/9 — Remove core import-time logging

**Goal:** Remove `setup_root_logger()` call at `collection_service` module import;
logging is configured once by the app via `bootstrap_logging()`.

**Requirements:** R5

**Dependencies:** architecture-audit/8

**Files:**

```
packages/indexed-core/src/core/v1/engine/services/collection_service.py  # remove setup_root_logger()
apps/indexed/src/indexed/bootstrap.py                                      # ensure logging init order
apps/indexed/src/indexed/app.py
tests/system/test_logging_no_leak.py                                       # still passes at default level
tests/unit/indexed_core/test_collection_service_logging.py                 # NEW — import has no sink setup
```

**Test scenarios:**

- Importing `collection_service` does not add loguru handlers.
- CLI `--quiet` suppresses warnings; `--debug` shows them (existing system test).
- Library callers (tests) can import core services without duplicate log lines.

**Verification:** `uv run pytest tests/system/test_logging_no_leak.py tests/unit/indexed_core/test_collection_service_logging.py -q`

---

### architecture-audit/10 — Merge connector builders to registry

**Goal:** Replace `collection_service._build_connector_from_config()` and duplicate
factory logic with a single `build_connector_from_config()` on the connector registry.

**Requirements:** R7, R10

**Dependencies:** architecture-audit/9

**Files:**

```
packages/indexed-connectors/src/connectors/registry.py                   # build_connector_from_config()
packages/indexed-core/src/core/v1/engine/services/collection_service.py  # delegate to injected builder
packages/indexed-core/src/core/v1/engine/factories/update_collection_factory.py
apps/indexed/src/indexed/bootstrap.py                                    # inject registry builder
tests/unit/indexed_connectors/test_registry_build.py                     # NEW — all source types
tests/unit/indexed/services/test_collection_service.py                   # update to mock registry
```

**Test scenarios:**

- One code path builds connectors for `jira`, `jiraCloud`, `confluence`,
  `confluenceCloud`, `localFiles`, `outline`.
- `config_service.set()` namespace mapping matches `NAMESPACE_REGISTRY` (no drift).
- Update factory uses the same builder as create (no duplicated elif chains).

**Verification:** `uv run pytest tests/unit/indexed_connectors/test_registry_build.py tests/unit/indexed/services/test_collection_service.py -q`

---

### architecture-audit/11 — IndexedError handlers CLI/MCP

**Goal:** CLI catches `IndexedError` subtypes for user-friendly messages and exit
codes; MCP tools return structured error dicts from `IndexedError`, not bare
`Exception` strings.

**Requirements:** R6, R10

**Dependencies:** architecture-audit/10

**Files:**

```
apps/indexed/src/indexed/errors.py                     # map subtypes → exit codes / messages
apps/indexed/src/indexed/app.py                        # typer exception handler
apps/indexed/src/indexed/mcp/tools.py                  # catch IndexedError → structured dict
apps/indexed/src/indexed/mcp/resources.py
apps/indexed/src/indexed/mcp/formatting.py             # error envelope helper
tests/unit/indexed/test_cli_error_handler.py           # NEW
tests/unit/indexed/mcp/test_error_handling.py          # NEW
```

**Test scenarios:**

- `ConfigurationError` in CLI prints actionable message, exit code ≠ 0, no traceback
  at default verbosity.
- MCP `search()` given missing collection returns `{"error": "...", "type": "StorageError"}`
  not a generic `"str(e)"` from unexpected exceptions.
- Unexpected `RuntimeError` still propagates with full traceback (CLI `--debug`).

**Verification:** `uv run pytest tests/unit/indexed/test_cli_error_handler.py tests/unit/indexed/mcp/test_error_handling.py -q && uv run mypy src/`

---

### architecture-audit/12 — Import-graph CI check + characterization test baseline

**Goal:** Add CI enforcement of the target dependency graph and a characterization
test suite that locks current CLI/MCP behaviour before v2 work begins.

**Requirements:** R1, R11

**Dependencies:** architecture-audit/11

**Files:**

```
scripts/check_import_graph.py                          # NEW — forbidden import rules
.github/workflows/python-ci.yml                        # run check_import_graph.py
tests/characterization/test_cli_smoke.py               # NEW baseline
tests/characterization/test_mcp_smoke.py
tests/characterization/test_import_graph.py
.spec/features/architecture-audit/tech.md              # document allowed edges (cross-ref)
```

**Test scenarios:**

- Script fails if `core` imports `connectors`, `connectors` imports `core`, or
  `indexed_config` imports anything above infra.
- Characterization: `indexed index search "test" --collection …` exit code and
  output shape unchanged on fixture collection in `tmp_path`.
- Characterization: MCP `list_collections` tool returns expected keys on fixture.
- CI workflow step fails on violation (local run matches CI).

**Verification:** `uv run python scripts/check_import_graph.py && uv run pytest tests/characterization/ -q && uv run pytest -q --cov=src`

---

## Dependencies

| Unit | Blocks | Blocked by |
|---|---|---|
| architecture-audit/1 | /2 | — |
| architecture-audit/2 | /3 | /1 |
| architecture-audit/3 | /4 | /2 |
| architecture-audit/4 | /5 | /3 |
| architecture-audit/5 | /6 | /4 |
| architecture-audit/6 | /7 | /5 |
| architecture-audit/7 | /8 | /6 |
| architecture-audit/8 | /9 | /7 |
| architecture-audit/9 | /10 | /8 |
| architecture-audit/10 | /11 | /9 |
| architecture-audit/11 | /12 | /10 |
| architecture-audit/12 | — | /11 |

Same-feature dependencies only. Cross-feature order is a whole-feature gate in the
root [plan.md](../../plan.md) Feature Sequence, not a unit edge here.

---

## Progress

| Unit | Status |
|---|---|
| architecture-audit/1 | NOT STARTED |
| architecture-audit/2 | NOT STARTED |
| architecture-audit/3 | NOT STARTED |
| architecture-audit/4 | NOT STARTED |
| architecture-audit/5 | NOT STARTED |
| architecture-audit/6 | NOT STARTED |
| architecture-audit/7 | NOT STARTED |
| architecture-audit/8 | NOT STARTED |
| architecture-audit/9 | NOT STARTED |
| architecture-audit/10 | NOT STARTED |
| architecture-audit/11 | NOT STARTED |
| architecture-audit/12 | NOT STARTED |
