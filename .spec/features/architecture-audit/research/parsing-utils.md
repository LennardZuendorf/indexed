---
type: feature-research
feature: architecture-audit
cluster: parsing-utils
parent: ../product.md
updated: 2026-06-29
---

# Research: indexed-parsing + utils

Discovery artifact from the 2026-06-29 monorepo architecture audit. Combined
cluster for `packages/indexed-parsing/` (~600 LOC, 6 modules) and
`packages/utils/` (~604 LOC, 6 modules).

**Related:** [product.md](../product.md) R5 (no import-time side effects).
[tech-parsing.md](../../../tech-parsing.md). Surviving infra per `.spec/plan.md`.

---

## Summary

Both packages respect downward-only imports and are **v2-ready foundation
layers** with minor cleanup only. `indexed-parsing` is clean, connector-agnostic,
and lazy-loads heavy deps correctly — highest ROI is deduplicating Docling
chunking and aligning router extensions with chunker support. `utils` exceeds
"thin foundation" scope: `logger.py` is 63% of the package, connector-only
helpers (`batch.py`, `retry.py`) and core-only helpers (`performance.py`) live
in a shared package, and core services call `setup_root_logger()` at import time
(violating explicit bootstrap).

---

## Findings

### indexed-parsing

| # | Finding | Priority | Path(s) |
|---|---------|----------|---------|
| 1 | Docling chunking duplicated in two parsers | **P1** | `docling_parser.py`, `plaintext_parser.py` |
| 2 | Router lists 24 CODE extensions; `CodeChunker` supports 10 | **P1** | `router.py` (`CODE_EXTENSIONS`), `code_chunker.py` |
| 3 | `DOCLING_FALLBACK` triggers full Docling init then plaintext anyway | **P2** | `router.py:15`, `router.py:109` |
| 4 | Package `__init__` eagerly imports all parsers | **P2** | `parsing/__init__.py` |
| 5 | `parse_bytes()` uses temp files for in-memory wiki bodies | **P2** | `parsing/__init__.py` (`ParsingModule`) |
| 6 | `ParsingModule` facade is the right shape | **KEEP** | `parsing/__init__.py` |
| 7 | Lazy heavy imports inside parsers (Docling, tree-sitter) | OK | Parser modules |
| 8 | No upward imports; connector-agnostic | OK | Package-wide |

### packages/utils

| # | Finding | Priority | Path(s) |
|---|---------|----------|---------|
| 1 | `logger.py` is 63% of package (~380 LOC) | **P2** | `logger.py` |
| 2 | `batch.py` + `retry.py` used only by connectors | **P1** | `batch.py`, `retry.py` |
| 3 | `performance.py` used only by core | **P1** | `performance.py` |
| 4 | `safe_getattr.py` — zero production usage | **P2** | `safe_getattr.py` |
| 5 | Core calls `setup_root_logger()` at import time | **P1** | `collection_service.py`, `inspect_service.py` (core) |
| 6 | `execute_with_retry` retries permanent HTTP errors (401/404) on sync paths | **P1** | `retry.py` |
| 7 | orjson/json shim duplicated in 3 core modules | **P2** | Core engine modules |
| 8 | `logger.py` mixes infra + Rich UI + domain policy (docling, transformers) | **P2** | `logger.py` |
| 9 | `emit_status` never called in production | **P2** | `logger.py` |
| 10 | Downward-only imports confirmed | OK | Package-wide |

---

## Refactoring Proposals

### Parsing — P1 (highest ROI)

1. **Single Docling pipeline:** Extract `_docling_chunks()` helper; route `.md`
   through `DoclingParser` (structure-aware) instead of duplicating in
   `plaintext_parser.py`.
2. **One extension registry:** `CODE_EXTENSIONS = frozenset(LANGUAGE_MAP.keys())`
   in `code_chunker.py`; import in `router.py`. Drop fake AST routes for
   unsupported languages.
3. **Remove `DOCLING_FALLBACK`:** Route unknown extensions directly to
   `PlaintextParser`; avoid Docling init for unsupported types.

### Parsing — P2

1. Lazy-import parsers inside `ParsingModule.__init__` or per-route — not at
   package `__init__`.
2. Add `parse_text(content, filename_hint)` for in-memory wiki bodies (Outline,
   Confluence) — skip temp files in `parse_bytes()`.

### Utils — P1

1. **Remove import-time logging** from core services; single bootstrap in
   `apps/indexed/app.py` callback and MCP startup (architecture-audit/9).
2. **Move connector-only helpers** to `connectors/_shared/` or
   `connectors/http.py`: `batch.py`, `retry.py`.
3. **Move core-only helper** to `core/v1/observability.py`: `performance.py`.
4. **Fix retry policy:** Add `retryable` predicate; sync paths match async
   (transient-only: 429, 5xx). Align with R8.

### Utils — P2

1. **Delete `safe_getattr.py`** — test-only usage.
2. **Add `utils/json_io.py`** — consolidate orjson/json shim from 3 core modules.
3. **Split `logger.py`:** bootstrap bridge (infra) vs app sinks (Rich UI); move
   domain log-level policy to app layer.
4. Wire `emit_status` or move pub/sub to app — delete if unused after audit.

---

## Delete / Merge / Keep / Defer

| Component | Path(s) | Action | Rationale | When |
|-----------|---------|--------|-----------|------|
| Docling chunk duplication | `docling_parser.py`, `plaintext_parser.py` | **MERGE** | Single `_docling_chunks()` helper | Quick win |
| Fake CODE routes (14 unsupported ext) | `router.py` | **DELETE** | Router/chunker mismatch causes silent plaintext fallback | Quick win |
| `DOCLING_FALLBACK` strategy | `router.py` | **DELETE** | YAGNI — init Docling then plaintext anyway | Quick win |
| `safe_getattr.py` | `utils/safe_getattr.py` | **DELETE** | Zero production usage | Quick win |
| `batch.py` | `utils/batch.py` | **MERGE → connectors** | Connector-only | Phase 1 |
| `retry.py` | `utils/retry.py` | **MERGE → connectors/http.py** | Connector-only; fix transient policy | Phase 1 (architecture-audit/7) |
| `performance.py` | `utils/performance.py` | **MERGE → core** | Core-only observability | Phase 1 |
| orjson/json shims (×3) | core engine modules | **MERGE → utils/json_io.py** | DRY | Phase 1 |
| Import-time `setup_root_logger()` | core services | **DELETE pattern** | Violates explicit bootstrap | Phase 1 (architecture-audit/9) |
| `ParsingModule` facade | `parsing/__init__.py` | **KEEP** | Right abstraction; survives v2 | — |
| `FileRouter` | `router.py` | **KEEP** | Clean strategy routing | — |
| `DoclingParser`, `CodeChunker`, `PlaintextParser` | parsing modules | **KEEP** | Core parsing stack | — |
| `logger.py` (slimmed) | `utils/logger.py` | **KEEP** | Shared logging infra after split | v2 |
| `parse_text()` API | `ParsingModule` | **DEFER** | Wiki in-memory bodies | v2 connectors |
| Package-level lazy imports | `parsing/__init__.py` | **DEFER** | Startup perf polish | Phase 1 |
| `emit_status` pub/sub | `logger.py` | **DEFER** | Wire or delete after usage audit | Phase 2 |

---

## Essential Files

### indexed-parsing

- `parsing/__init__.py` — `ParsingModule` facade
- `parsing/router.py` — extension → strategy
- `parsing/docling_parser.py` — PDF/DOCX/PPTX/HTML/images
- `parsing/code_chunker.py` — tree-sitter AST chunking (source of truth for CODE ext)
- `parsing/plaintext_parser.py` — markdown + fallback text
- `parsing/schema.py` — `ParsedDocument`, `ParsedChunk`

### utils (post-cleanup target)

- `utils/logger.py` — logging bootstrap bridge (slimmed)
- `utils/json_io.py` — (new) orjson/json shim
- Retain only truly cross-package helpers; relocate connector/core-specific code
