---
type: feature-research
feature: core-v2
parent: product.md
updated: 2026-07-19
---

# core-v2 — Research

Discovery artifacts behind the core-v2 design. Compiled 2026-07-18 from three
repo deep-dives, a full review of the prior V2 attempt (PR #86 + split stack
#131–#136, incl. #132), and two LlamaIndex investigations (one with empirical
verification against `llama-index-core==0.14.23` in a clean py3.11 venv).
Full narrative + matrices: [`plans/indexed-v2.md`](../../../plans/indexed-v2.md).

## Question

Can a LlamaIndex-based v2 core ship behind the existing swap seam, coexist
safely with v1 collections, and deliver pluggable embeddings/stores/reranking —
and what did the previous attempt get right and wrong?

## Findings

### Finding: the swap seam exists, but its format premise does not survive contact

`core/v1/engine/__init__.py` exposes exactly 13 names (verified) and root
specs designate it "the v2 core-swap seam … same names over the same on-disk
format". The *names* part holds; the *format* part cannot: v1's layout
(`manifest.json` + `documents/<id>.json` + `indexes/{index_info,
index_document_mapping,reverse_index_document_mapping}.json` +
`indexes/<indexer>/indexer.faiss`) has no docstore and positional FAISS ids,
while LlamaIndex's `FaissVectorStore` has **no metadata filters** (`query()`
raises `ValueError`), **no delete** (`NotImplementedError`), positional
`str(ntotal)` ids, and `stores_text=False` (all verified in upstream source).
Every v2 goal (filters, deletes/upserts, pluggable stores) requires a new
persisted format.

### Finding: no on-disk version marker exists today

v1 manifests have no `version`/`schemaVersion` key anywhere (verified by grep
+ fixture inspection) — "absence of marker = v1" is therefore a sound and
backward-compatible detection rule, and matches what PR #86 chose.

### Finding: the app-layer blast radius is small and funnels through two seams

All runtime core access goes through the `core.v1.engine` facade names and
`cli/composition.py` (single wiring site; `resolve_collections_context` shared
by CLI+MCP). ~12 app modules hold lazy facade imports; no CLI/config/env
engine selector exists anywhere today (verified) — selection is net-new.
Config is migration-ready: `core.v1.*` namespaces, `[_meta] schema_version`,
`INDEXED__*` double-underscore env mapping, and tech-config.md already names
`core.v1.* → core.v2.*` as the anticipated path.

### Finding: the runtime contract is dicts, not the typed models

Only `Manifest` is model-enforced at runtime; documents/chunks/search results
move as plain camelCase dicts (`CollectionSearchResult` etc. are never
instantiated — verified). The v2 adapter must match the dict shapes actually
produced, and `mcp/formatting.py` + `search_render.py` define the search
result contract (`results[].matchedChunks[].{chunkNumber,score,content}`).

### Finding: PR #86 / split stack #131–#136 — what transfers

Closed unmerged (2026-06-21), targeted the deleted 7-package workspace; only
#131 landed. Worth keeping: boundary adapter (connectors never see
LlamaIndex), bypassing LlamaIndex node parsers (own Docling/tree-sitter
chunking), no `Settings` global, deterministic `{doc_id}__chunk_{i}` node ids,
manifest `"version"` marker, `EngineMismatchError` with actionable copy, MCP
lifespan-resolved engine, and the parity-capture methodology. Confirmed
defects to design out: collection deleted *before* replacement persisted;
load path hardcoding `FaissVectorStore.from_persist_dir` (defeats pluggable
stores); update ignoring the manifest (used session state); v2 shipped as
default with zero dogfooding; 5-level precedence letting flags override
on-disk reality; in-process FastMCP client + llama-index + torch segfault
(exit 139) — v2 MCP e2e must be out-of-process.

### Finding: LlamaIndex core facts (verified, 0.14.23)

MIT; py>=3.10; core pulls no torch/openai; ~30 MB marginal install for this
repo (torch/st already present); `import llama_index.core` ≈ 1.0–1.4 s warm —
must stay function-local. Retriever-only path needs NO LLM (proven with no
`OPENAI_API_KEY`); touching `Settings.llm`/`embed_model` or
`as_query_engine()` triggers OpenAI-by-default errors — pass components
explicitly, never touch `Settings`. `BaseEmbedding` abstract = 3 methods; no
dimension API (probe + record). Persist formats undocumented across versions
→ pin `>=0.14,<0.15`, record `llamaIndexCoreVersion` per collection;
integrations all pin `<0.15` → lockstep upgrades. `IS_TESTING=1` yields mock
components (useful in tests). Instrumentation module replaces callbacks; no
stable exception hierarchy → wrap at the service boundary.

### Finding: incremental update maps cleanly onto docstore upserts

`DocstoreStrategy.UPSERTS` (verified in source): per input doc, compare stored
hash for `ref_doc_id`; unchanged → skip; changed → `delete_ref_doc` +
`vector_store.delete(ref_doc_id)` + re-embed. Requires stable per-doc ids
(connectors already provide them) and a store with working `delete` — the
concrete reason FaissVectorStore is excluded from v2.

### Finding: store + provider matrices point at Simple-default, Qdrant-optional

SimpleVectorStore: in core, zero deps, JSON persist, **filters verified
working empirically**, delete, MMR; brute-force NumPy ≈ same O(N·d) class as
v1's IndexFlatL2 at <100k docs; plain-file persistence keeps the
CLI-writes/MCP-reads pattern safe. Qdrant embedded (path mode): richest
(filters, true delete, hybrid, async, cosine) but single-process-locked —
wrong default for CLI+MCP concurrency, right first optional backend. Chroma:
server-grade dep tree + nonstandard `exp(-distance)` scores — weakest fit.
LanceDB: heaviest deps. HuggingFace embeddings integration imports
sentence-transformers (→torch) at module top → ADOPT the native
`HuggingFaceEmbedding` but import the integration module function-locally to
avoid the module-top torch cost; it reuses v1's SentenceTransformer model +
shared HF cache (same vectors as v1) and `ty` types the integration source
directly (the "ships no py.typed" concern did not materialize). Scores are
store-dependent upstream
(cosine/exp(-d)/raw) — v2 pins cosine and converts v1 exactly via
`sim = 1 − d²/2` (v1 vectors are unit-normalized, verified).

### Finding: knowledge graphs need an LLM to be worth shipping

`PropertyGraphIndex` default extractors require an LLM; the LLM-free
`ImplicitPathExtractor` only materializes chunk-adjacency edges (verified) —
near-zero value over the existing index. Embedded Kuzu graph store pins an
engine unreleased since 2025-10 (at-risk). → KG is deferred, LLM-gated, a
future sibling feature.

## Approaches tried

| Approach | Result | Notes |
|---|---|---|
| v2 as byte-compatible drop-in behind `core.v1.engine` (root-spec premise) | ruled out | v1 format can't express v2 capabilities; LI FAISS integration can't even read it |
| Runtime engine router with flag-over-manifest precedence (PR #86/#134) | ruled out | caused the observed mismatch bug class; flags must not override on-disk reality |
| Adopt `FaissVectorStore` for v2 (PR #86) | ruled out | no delete/filters/stable ids — strictly weaker than v1's own FAISS layer |
| Adopt native `HuggingFaceEmbedding` (function-local import) | **chosen** | reuses v1's model + shared HF cache (1:1 vectors); function-local import avoids the module-top torch cost; `ty` types the integration source directly |
| Version-dispatching facade + manifest-authoritative routing + new v2 format | **chosen** | see [tech.md](tech.md); ADRs in `plans/indexed-v2.md` |

## Decision

Build v2 as an additive engine under `core/v2/` on `llama-index-core`
(retriever-only, explicit components, lazy imports), persisting a
version-marked new format (StorageContext + engine-metadata manifest); raise
the swap seam to a version-dispatching `indexed.core.engine` facade where the
manifest is authoritative for existing collections and selectors
(flag > env > config > default v1) apply to creation only; keep v1 frozen;
migrate v1→v2 only on explicit request, offline by default. Default store
SimpleVectorStore, Qdrant embedded optional; local embeddings default, remote
providers opt-in via extras; rerank opt-in; KG/hybrid deferred to siblings.

## v1-vs-v2 parity capture (core-v2/8, measured 2026-07-19)

The evidence base for the later default-flip gate. Measured on all-MiniLM-L6-v2
(cached, offline) with `tests/benchmarks/test_e2e_performance.py` (perf) and
dedicated probes (disk/relevance); numbers are from this repo on the CI-class
runner and will vary by machine — the RATIOS are the durable signal.

| Dimension | v1 | v2 | v2/v1 | Budget | Verdict |
|---|---|---|---|---|---|
| Warm create (full CLI) | 8.57 s | 9.78 s | **1.14×** | ≤1.5× | PASS |
| Warm search (full CLI) | 5.89 s | 7.36 s | **1.25×** | ≤2.0× | PASS |
| Collection disk (repo-docs corpus) | 46.8 KiB | 180.0 KiB | **3.85×** | (no budget) | noted |
| Top-hit agreement (needle queries) | — | — | **3/3** | ~1:1 | PASS |

**Perf (R12).** Both budgets hold with margin. Ratios are measured
OUT-OF-PROCESS (a fresh `indexed` process per invocation, both engines loading
the same disk-cached model) — the realistic steady state for a CLI tool and the
fair basis for the tech.md budget, which is about the search-algorithm cost
(brute-force NumPy vs FAISS FlatL2, same O(N·d)). An *in-process* `CliRunner`
loop instead hands v1 a cross-invocation process-global embed-model cache that
v2's per-call `HuggingFaceEmbedding` does not share, inflating the warm-search
ratio to ~5× — an artifact of a missing v2 embed-model cache, NOT the retrieval
cost. **Follow-up (non-blocking):** a v2 process-global embed-model cache
(analogous to v1's `model_manager`) would close that in-process gap and is the
one clear perf win before or after the default flip; it does not affect the
real per-process CLI number.

**Disk.** v2 collections are ~3.8× larger on the same corpus: v2's
`storage/docstore.json` stores every chunk's full node text (the upsert basis)
plus `index_store.json` and a JSON `default__vector_store.json`, whereas v1
keeps a compact binary FAISS index alongside `documents/<id>.json`. This is the
expected cost of the docstore-upsert model (working `delete()`/incremental
update, tech.md § Update semantics) and is well within local-disk budgets at the
<100k-doc target scale; it is a data point for the flip, not a regression.

**Relevance (R4).** Top-hit agreement is 3/3 on the needle queries and 1:1 in
the cloud parity nets (`test_lifecycle_cloud_v2.py`: jira/confluence/outline all
return the SAME needle document v1 does). Expected — v2 uses v1's exact model
and unit-normalized vectors (cosine vs squared-L2 induce the same ranking), so
recall is identical; the two engines are relevance-interchangeable.

**Conclusion.** On perf, disk, and relevance v2 is at parity or within budget
for a default flip; the only open perf item (in-process embed-model reuse) is an
optimization, not a blocker. The flip remains a separate gated decision (plan.md
Open Question 1); this capture is its evidence base.
