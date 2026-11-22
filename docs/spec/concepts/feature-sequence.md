---
type: concept
updated: 2026-11-22
---

# Feature Sequence

Binary whole-feature gates. A feature is DONE when shipped and its live surface
is the truth. Cross-feature order is a whole-feature gate, never a unit edge.

| # | Feature | Gate | Status | Live surface |
|---|---------|------|--------|--------------|
| 1 | Core indexing pipeline | read→convert→chunk→embed→index→persist works E2E | ✅ DONE | `src/indexed/core/v1/` |
| 2 | FAISS semantic search | L2 search + score mapping | ✅ DONE | `src/indexed/core/v1/engine/indexes/indexers/faiss_indexer.py` |
| 3 | Jira connectors (Cloud + Server/DC) | JQL-filtered indexing | ✅ DONE | `src/indexed/connectors/jira/` |
| 4 | Confluence connectors (Cloud + Server/DC) | CQL-filtered indexing | ✅ DONE | `.../connectors/confluence/` |
| 5 | File system connector | local files + parsing module | ✅ DONE | `.../connectors/files/`, `src/indexed/parsing/` |
| 6 | Outline Wiki connector | Cloud + self-hosted parity, attachments/OCR | ✅ DONE | `.../connectors/outline/`, tests `tests/unit/indexed_connectors/outline/` |
| 7 | MCP server (stdio/HTTP/SSE) | tools + resources exposed | ✅ DONE | `src/indexed/mcp/` |
| 8 | CLI commands | create/search/update/inspect/remove | ✅ DONE | `src/indexed/cli/knowledge/commands/` |
| 9 | Config & .env loading | single-source resolution, .env hierarchy, .gitignore guard | ✅ DONE | `src/indexed/config/`, [tech/config](../tech/config/README.md) |
| 10 | Architecture cleanup (pre-v2) | structural fixes on surviving infra | ◑ MOSTLY DONE | [Architectural Rules](../tech/architectural-rules.md); see below |
| 11 | Architecture audit remediation | graph fixed, CLI/MCP parity, hygiene, import-graph CI | ✅ DONE | `src/indexed/protocols/`; wiring since folded into `src/indexed/cli/composition.py` (Feature 13) and the graph checker into `scripts/check_imports.py` (Feature 14) |
| 12 | Critical bugs (non-core) | #123/#124 security + #114/#110 UX fixed, all gates green | ✅ DONE | `connectors/_url_guard.py`, `commands/create.py`, `commands/search.py` |
| 13 | Foundation (architecture & correctness) | every audited bug fixed behind a characterization harness; typed contracts + core-swap facade; read-mostly config; honest CLI/MCP failures — R1–R7 verified | ✅ DONE | `protocols/models.py`, `src/indexed/core/engine.py` (facade), `src/indexed/cli/composition.py`, connector `from_manifest` |
| 14 | Simplify (codebase reduction) | single package; dead code deleted; CLI/config chrome + process apparatus shrunk — R1,R3,R4,R5 verified, R2 partial (indexer deferred) | ✅ DONE | `src/indexed/` (one package, one wheel `indexed-sh`); `scripts/check_imports.py` + `scripts/check_sizes.py` |
| 15 | Review remediation (PR #155) | every confirmed PR #155 review defect fixed behind a regression test — R1–R15 verified | ✅ DONE | merged to `main` in PR #155; regression tests in `tests/` (feature folder wrapped up 2026-07-19) |
| 16 | Core v2 (LlamaIndex engine) | v2 engine + v1/v2 coexistence, routing, migration — R1–R13 verified | ✅ DONE | `src/indexed/core/v2/`, version-dispatching facade `src/indexed/core/engine.py` + `core/versioning.py`; tests `tests/unit/indexed/core/v2/`; migration `core/v2/migration.py` |
| 17 | Core v2 discoverability (issue #188) | `--engine`/rerank flags surfaced, clean engine error on all 4 surfaces, README + every command's `--help` — R1–R7 verified | ✅ DONE | `src/indexed/cli/knowledge/commands/{_create_options,_create_commands,create,_create_helpers,search}.py`, `core/engine.py`, `core/v2/{retrieval,services}`, `config/commands/set.py`, `cli/composition.py`, `README.md`, `cli/knowledge/cli.py` |
| 18 | Core v2 rendering fixes (`core-v2-rendering-fixes`, issue #187) | all 8 PR #162 review polish findings fixed behind regression tests — R1–R8 verified | ✅ DONE | `cli/app.py`, `cli/utils/components/{alerts,theme,cards}.py`, `cli/knowledge/commands/{update_service,search_render,_create_options,inspect}.py`, `connectors/files/schema.py`, `core/engine.py` |
| 19 | GitHub Projects/Issues connector | issues+PRs+Projects v2 indexed; incremental update | ◑ MOSTLY DONE | [features/github-connector/](../features/github-connector/product.md) · [#90](https://github.com/LennardZuendorf/indexed/issues/90) — chunk-hash reuse follow-up not yet planned |
| 20 | retrieval-eval | pinned code/docs/GitHub fixtures, measured dense/rerank evidence, validated reports | IN REVIEW | [features/retrieval-eval/](../features/retrieval-eval/product.md) · PR #265; paired public docs remain open |
| 21 | lsp-tier0 (issue #241) | `indexed lsp` over stdio: honest `initialize`, `workspace/symbol`, `textDocument/hover` with provenance, MethodNotFound for the rest | IN REVIEW | [features/lsp-tier0/](../features/lsp-tier0/product.md) · `src/indexed/lsp/`, `src/indexed/cli/lsp.py` |
| 22 | lsp-tier1 (issue #241) | navigation on the same server: `textDocument/definition` and bounded `textDocument/references` with the file-level degradation rule and one keyed query per request, plus honest `publishDiagnostics` (only "not in any collection" / "indexed version differs", never a fabricated warning) | IN PROGRESS | [features/lsp-tier1/](../features/lsp-tier1/product.md) · `src/indexed/lsp/{resolver,diagnostics}.py` · `tests/system/lsp_evidence/` |

| 23 | file-watcher (issue #67) | Foreground collection refresh, debounce and missing-source protection | IN REVIEW | [features/file-watcher/](../features/file-watcher/product.md) · `cli/knowledge/commands/{watch,watch_service}.py` |
| 24 | collection-registry (issue #346) | stable collection ids in the global store; local→global migration with dry run, resume and rollback; two projects read one on-disk copy | IN REVIEW | [features/collection-registry/](../features/collection-registry/product.md) · `config/collections_registry.py`, `cli/storage/`, `cli/composition.py` |
