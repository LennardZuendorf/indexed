---
type: feature-research
feature: architecture-audit
cluster: connectors
parent: ../product.md
updated: 2026-06-29
---

# Research: indexed-connectors

Discovery artifact from the 2026-06-29 monorepo architecture audit. Covers
`packages/indexed-connectors/` (~5,865 LOC, 34 modules).

**Related:** [product.md](../product.md) R1 (injection not import), R4/R5
(config bootstrap). [tech-connectors.md](../../../tech-connectors.md) § Connector
Protocol. Target pattern: `outline/`.

---

## Summary

`indexed-connectors` delivers five source adapters (files, Jira, Confluence,
Outline) and is **surviving v0.1 infra** with significant consolidation debt.
The Outline connector is the target pattern — single unified reader/converter,
`ConnectorMetadata`, `sources.*` namespace, no deprecated wrappers — while Jira
and Confluence carry dual Cloud/Server class splits, three reader implementations
each, and ~343 LOC of explicitly deprecated shims (~600 LOC including legacy
Server readers still on the hot path). Import-time `ConfigService.register()` in
subpackage `__init__.py` files creates dual namespaces (`connectors.*` vs
`sources.*`), HTTP retry logic is duplicated four ways, and `execute_with_retry`
retries all exceptions including 401 auth failures. Seven modules exceed or
critically approach the 400L cap.

---

## Current Architecture

```
packages/indexed-connectors/src/connectors/
  __init__.py                          re-exports connectors + registry
  registry.py                          CONNECTOR_REGISTRY, CONFIG_REGISTRY, NAMESPACE_REGISTRY
  document_cache_reader_decorator.py   read-cache wrapper (used by create factory)
  files/
    connector.py reader.py converter.py schema.py change_tracker.py v1_adapter.py
  jira/
    connector.py                       JiraConnector + JiraCloudConnector (376L)
    unified_jira_document_reader.py    target unified reader (388L)
    unified_jira_document_converter.py
    jira_document_reader.py            DEPRECATED Server wrapper (121L)
    jira_cloud_document_reader.py      DEPRECATED Cloud wrapper (104L)
    async_jira_cloud_reader.py         async variant with inline retry (255L)
    jira_*_document_converter.py       DEPRECATED converters (31L each)
  confluence/
    connector.py                       ConfluenceConnector + ConfluenceCloudConnector (422L)
    confluence_document_reader.py      Server reader, uses execute_with_retry (341L)
    confluence_cloud_document_reader.py Cloud reader (293L)
    async_confluence_cloud_reader.py   async variant (356L)
    confluence_*_document_converter.py   DEPRECATED + unified converter
  outline/                             ★ TARGET PATTERN
    connector.py reader.py converter.py schema.py
```

**Target pattern (Outline):**

- One connector class for Cloud + self-hosted (URL differs, API identical).
- Reader owns inline `_post_with_retry` tuned to Outline rate limits.
- `ConnectorMetadata` + `config_spec()` + `from_config()` with `sources.outline`.
- No deprecated wrapper layer; no duplicate async reader.

**Legacy pattern (Jira / Confluence):**

- Separate `*Connector` and `*CloudConnector` classes with overlapping config.
- Three reader stacks: unified, deprecated wrapper, async cloud — only unified
  should remain.
- Server readers (`confluence_document_reader.py`) still full implementations,
  not thin delegators.

---

## Spec Compliance Gaps

| Finding | Priority | Path |
|---------|----------|------|
| Import-time config registration (violates R5 explicit bootstrap) | **P0** | `jira/__init__.py:8–16`, `files/__init__.py:12`, `confluence/__init__.py:22–23` |
| Dual config namespaces `connectors.*` vs `sources.*` | **P0** | `__init__.py` files register `connectors.*`; `registry.NAMESPACE_REGISTRY` + connector `from_config()` use `sources.*` |
| HTTP retry retries 401 and all exceptions | **P1** | `utils/retry.py:16` (`except Exception`); used by Jira/Confluence readers |
| Four distinct retry implementations | **P1** | `utils/retry.execute_with_retry`, `outline_document_reader._post_with_retry`, `async_jira_cloud_reader._post_with_retry`, `async_confluence_cloud_reader` inline sleep |
| Deprecated wrapper classes still exported | **P1** | `jira/jira_document_reader.py`, `jira_cloud_document_reader.py`, `jira_*_converter.py`, `confluence_*_converter.py` |
| Jira Cloud dual readers (unified + async + deprecated) | **P1** | `unified_jira_document_reader.py`, `async_jira_cloud_reader.py`, deprecated wrappers |
| Confluence three readers (Server + Cloud + async) | **P1** | `confluence_document_reader.py`, `confluence_cloud_document_reader.py`, `async_confluence_cloud_reader.py` |
| Modules over 400L limit (7 flagged) | **P1** | See table below |
| `confluence/connector.py` duplicates Jira connector boilerplate | **P2** | `confluence/connector.py` (422L), `jira/connector.py` (376L) |
| Protocols imported from core engine package | **P1** | All connectors import `core.v1.connectors.*` (resolved by R2 protocols extraction) |

**Seven modules over/at 400L limit (connectors package):**

| Lines | Path |
|-------|------|
| 537 | `outline/outline_document_reader.py` |
| 422 | `confluence/connector.py` |
| 391 | `files/change_tracker.py` |
| 388 | `jira/unified_jira_document_reader.py` |
| 376 | `jira/connector.py` |
| 356 | `confluence/async_confluence_cloud_reader.py` |
| 341 | `confluence/confluence_document_reader.py` |

---

## DRY/KISS Violations

1. **Import-time registration** — each subpackage `__init__.py` calls
   `ConfigService.instance().register(...)` at import with `try/except pass`,
   racing app bootstrap and registering stale `connectors.*` paths.
2. **Dual namespace drift** — `files/__init__.py` registers `connectors.files`;
   `FileSystemConnector.from_config()` uses `sources.files`; registry maps
   `localFiles` → `sources.files`.
3. **HTTP retry ×4** — shared `execute_with_retry` (blind retry), Outline's
   purpose-built `_post_with_retry`, and inline loops in async Jira/Confluence
   readers with slightly different backoff and status-code handling.
4. **401 retry bug** — `execute_with_retry` catches all `Exception`; auth failures
   (401/403) are retried instead of failing fast.
5. **Jira/Confluence class doubling** — `JiraConnector` + `JiraCloudConnector`,
   `ConfluenceConnector` + `ConfluenceCloudConnector` where Outline proves one
   class suffices (URL/runtime auth detection).
6. **~343 LOC deprecated shims** — wrapper readers/converters emit
   `DeprecationWarning` and delegate to unified classes; audit total ~600 LOC
   when legacy Server readers on hot path are included.
7. **v1 dict adapter** — `files/v1_adapter.py` bridges parsing output to legacy
   dict contract; necessary until v2, but only files connector should own it.

---

## Refactoring Opportunities

### P0 — Explicit bootstrap; single namespace (R4/R5)

1. Remove all `ConfigService.register()` calls from connector `__init__.py` files.
2. App `bootstrap.py` registers each connector config once under `sources.*`.
3. Delete `connectors.*` namespace registrations; migrate any remaining callers.
4. Align `NAMESPACE_REGISTRY`, `from_config()`, and CLI credential helpers on
   `sources.*` only.

### P1 — Consolidate Jira/Confluence to Outline pattern

1. Collapse `JiraConnector` + `JiraCloudConnector` → single `JiraConnector`
   (URL-based Cloud vs Server detection like Outline).
2. Same for Confluence.
3. Delete deprecated wrapper modules; export unified classes only.
4. Retire `async_*_cloud_reader.py` if unified reader covers concurrency needs,
   or merge async path into unified reader.

### P1 — Unified HTTP retry policy

1. Extend `utils/retry` (or new `utils/http_retry.py`) with:
   - Retry only transient statuses (429, 502, 503, 504) and connection errors.
   - **No retry** on 401, 403, 404.
   - Shared Retry-After / exponential backoff.
2. Replace inline `_post_with_retry` in Outline, async Jira, async Confluence,
   and `execute_with_retry` call sites.

### P1 — File-size compliance

| Module | Action |
|--------|--------|
| `outline_document_reader.py` (537L) | Split: API client vs pagination vs attachment/OCR |
| `confluence/connector.py` (422L) | Extract shared connector base or config builder |
| `unified_jira_document_reader.py` (388L) | Split query/pagination from auth/client |
| `change_tracker.py` (391L) | Split strategies (git/hash/mtime) into submodules |

### P2 — Registry as sole lookup

Ensure app uses `get_connector_class()` / `ConnectorMetadata` exclusively;
remove parallel type switches in core `collection_service` (see [core.md](core.md)).

### P2 — Protocols package migration (R2)

After protocols extract, connectors import from `indexed-protocols` instead of
`core.v1.connectors` — no behavioural change, enables core decoupling.

---

## Delete vs Keep vs Defer

| Component | Path(s) | Action | Rationale | When |
|-----------|---------|--------|-----------|------|
| Import-time registration | `jira/__init__.py`, `files/__init__.py`, `confluence/__init__.py` | **DELETE** | Violates R5; use app bootstrap | Phase 1 |
| `connectors.*` config paths | subpackage `__init__.py` | **DELETE** | Namespace drift vs `sources.*` | Phase 1 |
| Deprecated Jira readers/converters | `jira_document_reader.py`, `jira_cloud_document_reader.py`, `jira_*_converter.py` | **DELETE** | Unified replacements exist | Quick win |
| Deprecated Confluence converters | `confluence_document_converter.py`, `confluence_cloud_document_converter.py` | **DELETE** | Unified converter exists | Quick win |
| `async_jira_cloud_reader.py` | `jira/` | **MERGE or DELETE** | Duplicate of unified + inline retry | Phase 1 |
| `async_confluence_cloud_reader.py` | `confluence/` | **MERGE or DELETE** | Same | Phase 1 |
| Legacy Server readers | `confluence_document_reader.py` | **MERGE → unified** | Full impl, not thin wrapper | Phase 1 |
| `registry.py` | `connectors/` | **KEEP** | Dynamic lookup; move registration to app | — |
| `document_cache_reader_decorator.py` | `connectors/` | **KEEP** | Used by create pipeline | — |
| Outline connector stack | `outline/` | **KEEP** (split reader) | Target pattern for all sources | — |
| `files/v1_adapter.py` | `files/` | **KEEP** | v1 dict contract bridge until v2 | v2 |
| `files/change_tracker.py` | `files/` | **KEEP** (split) | Incremental indexing works | — |
| `unified_jira_document_reader.py` | `jira/` | **KEEP** (split) | Correct direction | — |
| Dual Cloud/Server connector classes | `jira/connector.py`, `confluence/connector.py` | **MERGE** | Follow Outline single-class model | Phase 1–2 |

---

## Essential Files

- `registry.py` — connector type → class/config/namespace lookup
- `document_cache_reader_decorator.py` — read-cache for create/update
- **Outline (target pattern)**
  - `outline/connector.py` — unified Cloud/self-hosted connector
  - `outline/outline_document_reader.py` — REST client (split target)
  - `outline/outline_document_converter.py` — parsing delegation
  - `outline/schema.py` — `OutlineConfig`, `OUTLINE_CLOUD_URL`
- **Files**
  - `files/connector.py` — local filesystem connector
  - `files/files_document_reader.py` — directory walk + gitignore
  - `files/files_document_converter.py` — chunk via parsing
  - `files/change_tracker.py` — incremental strategies (split target)
  - `files/v1_adapter.py` — ParsedDocument → v1 dict bridge
  - `files/schema.py` — `FileSystemConfig` / `LocalFilesConfig`
- **Jira (consolidation target)**
  - `jira/connector.py` — collapse Cloud/Server classes
  - `jira/unified_jira_document_reader.py` — keep; delete deprecated/async variants
  - `jira/unified_jira_document_converter.py`
  - `jira/schema.py` — `JiraConfig`, `JiraCloudConfig` (merge configs)
- **Confluence (consolidation target)**
  - `confluence/connector.py` — collapse Cloud/Server classes
  - `confluence/unified_confluence_document_converter.py`
  - `confluence/confluence_cloud_document_reader.py` — merge into unified reader
  - `confluence/confluence_document_reader.py` — merge into unified reader
  - `confluence/schema.py`
