---
type: feature-research
feature: core-v2
parent: product.md
updated: 2026-07-18
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

`core/v1/engine/__init__.py` exposes exactly 14 names (verified) and root
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
sentence-transformers (→torch) at module top and ships no `py.typed` →
implement our own `BaseEmbedding` adapter over sentence-transformers direct
(same vectors as v1, lazy, typed). Scores are store-dependent upstream
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
| Adopt `HuggingFaceEmbedding` wrapper | ruled out | module-top torch import + no py.typed; own BaseEmbedding adapter instead |
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
