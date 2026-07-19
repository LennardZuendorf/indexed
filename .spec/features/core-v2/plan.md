---
type: feature-plan
feature: core-v2
sibling: tech.md
parent: ../../plan.md
updated: 2026-07-19
units:
  - id: "core-v2/1"
    title: "Engine detection + version-dispatching facade (v1-only behavior)"
    status: done
    requires: []
  - id: "core-v2/2"
    title: "v2 engine MVP: create/search/inspect/status/clear"
    status: planned
    requires: ["core-v2/1"]
  - id: "core-v2/3"
    title: "v2 incremental update + lifecycle characterization net"
    status: planned
    requires: ["core-v2/2"]
  - id: "core-v2/4"
    title: "Migration command (dry-run, backup, rollback, validation)"
    status: planned
    requires: ["core-v2/3"]
  - id: "core-v2/6"
    title: "Reranking + unified relevance in CLI/MCP formatters"
    status: planned
    requires: ["core-v2/2"]
  - id: "core-v2/8"
    title: "Cloud-connector parity nets, benchmarks, parity report"
    status: planned
    requires: ["core-v2/3"]
---

# Feature: Core V2 (LlamaIndex engine) — Implementation Plan

Six units. Unit 1 is a pure refactor (routing seam with only v1 behind it,
zero behavior change) so every later unit lands behind an already-tested
dispatch layer. Units 6/8 are parallelizable after their listed dependencies.
The default engine stays v1 throughout; flipping it is a separate root-plan
gate after this feature is DONE.

**Descoped 2026-07-18 (maintainer):** the feature is local-only and
self-contained — remote embedding providers (was core-v2/5) and the Qdrant
embedded store (was core-v2/7) are future work behind the seams this feature
ships (provider config, store-identity dispatch). IDs core-v2/5 and core-v2/7
are retired, never reused.

> For agentic workers: execute units in Seq order via
> superpowers:executing-plans; cite unit IDs in commits
> (`feat(core): core-v2/1 ...`).

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Starts when Review Remediation (Feature 15) is `DONE`
(root [plan.md](../../plan.md) Feature Sequence) — confirmed merged to main.

---

## Problem Frame

The v1 facade was built as a swap seam, but the swap premise ("same names over
the same on-disk format") cannot hold for v2's goals: pluggable stores and
providers require a new persisted format, and LlamaIndex's FAISS integration
cannot express v1's layout (see [research.md](research.md)). So the seam is
raised one level: a version-dispatching facade routes per collection via an
on-disk version marker, v1 stays frozen, and v2 is additive. Units are ordered
to keep the tree green at every commit: seam first, engine second, update +
harness third, then migration and capabilities.

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Engine-versioned collections](product.md#requirement-engine-versioned-collections-r1) | core-v2/1, core-v2/2 |
| R2 | [Safe per-collection routing](product.md#requirement-safe-per-collection-routing-r2) | core-v2/1 |
| R3 | [Explicit engine selection](product.md#requirement-explicit-engine-selection-for-new-collections-r3) | core-v2/1 |
| R4 | [Surface parity](product.md#requirement-surface-parity-r4) | core-v2/2, core-v2/3, core-v2/8 |
| R5 | [Incremental update parity](product.md#requirement-incremental-update-parity-r5) | core-v2/3 |
| R6 | [v1 remains untouched](product.md#requirement-v1-remains-untouched-r6) | core-v2/1 (guarded by every unit) |
| R7 | [Migration on explicit request](product.md#requirement-migration-on-explicit-request-r7) | core-v2/4 |
| R8 | [Local, self-contained embeddings](product.md#requirement-local-self-contained-embeddings-r8) | core-v2/2 |
| R9 | [Recorded, dispatched store identity](product.md#requirement-recorded-dispatched-store-identity-r9) | core-v2/2 |
| R10 | [Optional reranking](product.md#requirement-optional-reranking-r10) | core-v2/6 |
| R11 | [Unified relevance semantics](product.md#requirement-unified-relevance-semantics-r11) | core-v2/2, core-v2/6 |
| R12 | [Performance and privacy budgets](product.md#requirement-performance-and-privacy-budgets-hold-r12) | core-v2/2, core-v2/8 |
| R13 | [Engine-aware diagnostics](product.md#requirement-engine-aware-diagnostics-r13) | core-v2/2 |

---

## Key Technical Decisions

1. **Manifest-authoritative routing; selectors create-only.** Kills the
   accidental-cross-engine-write class outright ([tech.md](tech.md) § Engine
   routing contract). Supersedes PR #86's flag-over-manifest precedence.
2. **New version-marked v2 format; v1 format frozen.** The "same disk format"
   drop-in premise is formally superseded ([research.md](research.md)
   § Decision).
3. **SimpleVectorStore only, store identity dispatched from the manifest;
   FAISS excluded from v2.** Working `delete()` + filters + no process lock
   beat raw speed at <100k docs ([tech.md](tech.md) § Update semantics).
   Additional stores are future work behind this seam.
4. **Retriever-only LlamaIndex usage, explicit components, all imports lazy.**
   No `Settings`, no `as_query_engine()`, no OpenAI-by-default trap.
5. **Offline migration by default** — re-embed from stored v1 chunk text;
   source access optional.
6. **Native HuggingFaceEmbedding with v1's model.** Same SentenceTransformer
   + HF cache as v1 → 1:1 relevance, zero re-download; integration module
   imported function-locally (module-top torch import upstream).

---

## Global Constraints

- Full verify gate before every commit: `uv run ruff check . --fix && uv run
  ruff format`; `uv run ty check src/indexed` (0 diagnostics); `uv run pytest
  -q --cov=src/indexed` (>85%); `python scripts/check_imports.py`;
  `bash .agents/skills/spec/scripts/validate.sh` when `.spec/` touched.
- No LlamaIndex import at module top anywhere; `import llama_index.core` is
  ~1s+ (verified) — function-local only.
- `core/v2/**` imports only `protocols`/`config`/`utils` (+ third-party).
- v1 byte-stability: `tests/characterization/` and
  `tests/system/test_read_mostly_config.py` must stay green untouched.
- Model-dependent tests gate on `model_available()`; v2 MCP e2e runs
  out-of-process (in-process FastMCP + llama-index segfault, verified).

---

## Unit IDs

Units are `core-v2/n`, assigned once, never renumbered. Seq = execution order.

---

### core-v2/1 — Engine detection + version-dispatching facade (v1-only)

**Goal:** All app-layer core access goes through `indexed.core.engine` with
per-collection version detection, selector-chain resolution, and mismatch
errors — while only v1 exists behind it (v2 requests fail with "not yet
available"). Zero behavior change for every existing workflow.

**Requirements:** R1, R2, R3, R6

**Dependencies:** —

**Files:**

```
src/indexed/core/versioning.py         # NEW detect_engine_version + literals
src/indexed/core/errors.py             # NEW EngineMismatchError, UnknownEngineVersionError
src/indexed/core/engine.py             # NEW dispatching facade (14 names + engine=)
src/indexed/cli/composition.py         # CliContext.engine, resolve_engine_selector, [core] engine spec
src/indexed/cli/app.py                 # global --engine; lazy imports -> indexed.core.engine
src/indexed/cli/knowledge/commands/*   # retarget facade imports; create --engine
src/indexed/mcp/{server,tools,resources}.py  # retarget; lifespan engine
```

**Test scenarios:**

- Unmarked collection routes to v1 for every op; `--engine v2` on it raises
  `EngineMismatchError` with the documented message (R2 scenario).
- Selector precedence: flag > `INDEXED__CORE__ENGINE` > `[core] engine` >
  default "1" (R3 scenarios).
- Manifest `"version": "3"` → `UnknownEngineVersionError`, collection untouched.
- Full existing suite green with zero test-body edits outside patch targets
  (facade patch point moves from `core.v1.engine` to `indexed.core.engine`).

**Verification:** `uv run pytest -q --cov=src/indexed` green;
`tests/characterization/` green; new unit tests for versioning/selector/errors.

---

### core-v2/2 — v2 engine MVP: create/search/inspect/status/clear

**Goal:** A v2 collection can be created, searched, inspected, and removed via
the normal commands with `--engine v2`: native HuggingFaceEmbedding with v1's
model, SimpleVectorStore + docstore persistence, version-marked manifest,
cosine scores, engine-aware inspect output. Fully local, self-contained.

**Requirements:** R1, R4, R8, R9, R11 (v2 side), R12, R13

**Dependencies:** core-v2/1

**Files:**

```
pyproject.toml                          # + llama-index-core>=0.14,<0.15
                                        #   + llama-index-embeddings-huggingface (+ uv.lock)
src/indexed/core/v2/{__init__,config_models,manifest,adapter,ingestion,retrieval,stores}.py
src/indexed/core/v2/embedding/local.py
src/indexed/core/v2/services/*.py
src/indexed/cli/composition.py          # register core.v2.* specs
```

**Test scenarios:**

- Create files-source v2 collection → manifest carries `version:"2"` + engine
  block; needle doc is top hit for its query; different query ranks a
  different doc first (known-hit pattern, not "no error").
- HuggingFaceEmbedding path produces vectors matching v1's
  sentence-transformers output (cosine ≈ 1.0 on samples) — 1:1 relevance
  parity — and reuses the existing model cache (no download when cached).
- No network syscalls in default create/search (fully local).
- `indexed --help` < 1 s with llama-index installed (import-laziness probe).
- Inspect shows engine/model/store for both engines (R13 scenario).
- Store recorded in manifest; load path dispatches on it (probe with a fake
  second store id → clear error, not silent FAISS/simple fallback).

**Verification:** new `tests/unit/indexed/core/v2/` + system create/search
test; full gate green; startup benchmark unchanged.

---

### core-v2/3 — v2 incremental update + lifecycle characterization net

**Goal:** `indexed index update` on a v2 collection re-embeds only new/changed
docs, honors `ConnectorRun.deletions`, and the full v2 files lifecycle
(create→search→update→inspect→remove) is regression-guarded like v1's.

**Requirements:** R4, R5

**Dependencies:** core-v2/2

**Files:**

```
src/indexed/core/v2/ingestion.py        # docstore-hash upserts; deletions; build-aside swap
src/indexed/core/v2/services/collection_service.py
tests/characterization/test_lifecycle_files_v2.py   # NEW, mirrors v1 net
```

**Test scenarios:**

- Modified + added + deleted source docs → exactly the changed set
  re-embedded (assert via docstore hashes/embed-call counting), deleted doc
  unfindable, unchanged doc's node ids stable (R5 scenario).
- Update failure mid-run leaves the prior v2 collection fully searchable
  (build-aside swap; PR #86 delete-before-persist regression test).
- Empty-body document batch is a no-op, not a crash (v1 invariant carried over).

**Verification:** new characterization net green alongside v1's; full gate.

---

### core-v2/4 — Migration command

**Goal:** `indexed index migrate <name>` converts v1→v2 offline from stored
chunks with dry-run, automatic `<name>.v1-backup`, post-migration validation
(counts + probe search), rollback on failure; `--from-source` re-reads via
`from_manifest`; `--purge-backup` cleans up.

**Requirements:** R7

**Dependencies:** core-v2/3

**Files:**

```
src/indexed/cli/knowledge/commands/migrate.py   # NEW thin command
src/indexed/core/v2/migration.py                # NEW service (offline + from-source paths)
src/indexed/cli/_app_setup.py                   # register command
skills/index-update/SKILL.md                    # document migrate flow
```

**Test scenarios:** the three R7 scenarios (dry-run changes nothing; failure
leaves v1 intact + no partial v2; offline migration without credentials), plus
post-migration search parity spot-check (same needle query top hit) and
rollback restores byte-identical v1 dir.

**Verification:** system test over a real v1 fixture collection; full gate.

---

### core-v2/6 — Reranking + unified relevance in formatters

**Goal:** Opt-in `SentenceTransformerRerank` stage for v2 search; CLI/MCP
formatters rank merged multi-engine results on cosine (v1 scores mapped
`sim = 1 - d²/2`) while preserving each engine's raw score field.

**Requirements:** R10, R11

**Dependencies:** core-v2/2

**Files:**

```
src/indexed/core/v2/retrieval.py        # postprocessor wiring
src/indexed/mcp/formatting.py           # scoreKind-aware ranking + relevance field
src/indexed/cli/knowledge/commands/search_render.py
```

**Test scenarios:** rerank disabled → no CrossEncoder import (lazy probe);
enabled → order changes on a crafted fixture and `top_n` respected; mixed
v1+v2 search ranks a known-better v2 hit above a worse v1 hit (R11 scenario);
v1-only output byte-identical to pre-feature (R6 guard).

**Verification:** formatter unit tests + mixed-engine system test; full gate.

---

### core-v2/8 — Cloud-connector parity nets, benchmarks, parity report

**Goal:** v2 lifecycle nets for jira/confluence/outline (stubbed HTTP, real
engine), v2 rows in `tests/benchmarks` with budget thresholds wired into the
CI benchmark action, and a written v1-vs-v2 parity capture (perf, disk,
relevance) as the evidence base for the later default-flip decision.

**Requirements:** R4, R12

**Dependencies:** core-v2/3

**Files:**

```
tests/characterization/test_lifecycle_cloud_v2.py
tests/benchmarks/test_e2e_performance.py    # v2 benchmark cases
.github/workflows/python-benchmark.yml      # threshold-map entries
.spec/features/core-v2/research.md          # parity capture appended
```

**Test scenarios:** per-connector known-hit lifecycle on v2; benchmark rows
within the tech.md budget (create ≤1.5×, warm search ≤2×); MCP v2 e2e
out-of-process (stdio) smoke.

**Verification:** benchmark CI comment shows v2 rows within tolerance; parity
numbers recorded; full gate.

---

## Dependencies

| Unit | Blocks | Blocked by |
|---|---|---|
| core-v2/1 | 2 | — |
| core-v2/2 | 3, 6 | core-v2/1 |
| core-v2/3 | 4, 8 | core-v2/2 |
| core-v2/4 | — | core-v2/3 |
| core-v2/6 | — | core-v2/2 |
| core-v2/8 | — | core-v2/3 |

---

## Spec vs Implementation

| Gap | Tracked in | Notes |
|---|---|---|
| Root specs still state "v2 over the same on-disk format" | compound step | Superseded by this feature's ADR; root tech.md § Core Facade updated at COMPOUND via the merge block in [tech.md](tech.md) |
| `.spec/tech-config.md` names `ConfigService.instance()` and `[core.v1.vector_store]` (stale vs code) | compound step | Fix while promoting the `[core] engine` key |
| `manifest.indexers[]` multi-indexer plumbing deferred "to the v2 rewrite" (root plan) | core-v2/2 | v2 manifest replaces it with the `engine` block; v1 plumbing stays as-is |

---

## Open Questions

1. **Where the default-flip gate lives** — proposed as a new root-plan
   Feature Sequence row ("core-v2 default flip") created at COMPOUND, gated on
   the core-v2/8 parity report (flip criteria approved 2026-07-18).
