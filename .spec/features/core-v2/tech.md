---
type: feature-tech
feature: core-v2
sibling: product.md
parent: ../../tech.md
updated: 2026-07-19
---

# Feature: Core V2 (LlamaIndex engine) — Architecture

v2 is a second engine implementation under `src/indexed/core/`, built on
`llama-index-core` with explicit component injection (no `Settings` global),
persisting a new version-marked on-disk format. A thin version-dispatching
facade (`indexed.core.engine`) replaces the app layer's direct
`core.v1.engine` imports and routes per collection. v1 stays frozen and serves
unmarked collections. Connectors and parsing are consumed unchanged through
`indexed.protocols`; an adapter converts converted-document dicts into
LlamaIndex `TextNode`s at the engine boundary.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)
**Research:** [research.md](research.md)

---

## Files

```
src/indexed/core/engine.py                  # NEW version-dispatching facade: same 14 names as
                                            # core.v1.engine + engine= kwarg; per-collection routing
src/indexed/core/versioning.py              # NEW detect_engine_version(collection_path) -> "1"|"2";
                                            # EngineVersion literal; UnknownEngineVersionError
src/indexed/core/errors.py                  # NEW CoreError subtree: EngineMismatchError,
                                            # UnknownEngineVersionError (inherit IndexedError)
src/indexed/core/v1/**                      # FROZEN — no behavior change
src/indexed/core/v2/__init__.py             # lazy __getattr__ facade (mirror of v1 pattern)
src/indexed/core/v2/config_models.py        # CoreV2EmbeddingConfig / StorageConfig / SearchConfig
src/indexed/core/v2/manifest.py             # V2 manifest model (version="2", engine block) + IO
src/indexed/core/v2/embedding/local.py      # lazy factory for the native HuggingFaceEmbedding
                                            # (v1's model + shared HF cache; function-local import)
src/indexed/core/v2/stores.py               # simple-store construction + LOAD dispatch on
                                            # manifest.engine.vectorStore (fail-loud on unknown)
src/indexed/core/v2/adapter.py              # ConvertedDocument dict -> TextNode[] (deterministic ids)
src/indexed/core/v2/ingestion.py            # create/update via docstore-hash upserts; build-aside +
                                            # atomic rename-swap (reuse DiskPersister semantics)
src/indexed/core/v2/retrieval.py            # retriever-only search + optional rerank postprocessor
src/indexed/core/v2/services/*.py           # collection/search/inspect services matching v1 contracts
src/indexed/cli/composition.py              # + register core.v2.* specs; CliContext.engine;
                                            # resolve_engine_selector(flag/env/config/default)
src/indexed/cli/app.py                      # + global --engine option; lazy imports retarget
                                            # indexed.core.engine
src/indexed/cli/knowledge/commands/*.py     # retarget facade imports; create gains --engine;
                                            # migrate.py (NEW command)
src/indexed/mcp/server.py                   # lifespan resolves default engine once into state
src/indexed/mcp/tools.py|resources.py       # retarget facade imports (per-collection routing inside)
pyproject.toml                              # + llama-index-core>=0.14,<0.15
                                            #   + llama-index-embeddings-huggingface (<0.15)
```

---

## Contract / API

### Version-dispatching facade (`indexed.core.engine`)

Re-exports the exact 14-name surface of `core.v1.engine` (verified:
`SourceConfig`, `CollectionStatus`, `CollectionInfo`, `PhasedProgressCallback`,
`create`, `update`, `clear`, `collection_exists`, `search`, `SearchService`,
`status`, `inspect`, `InspectService`) with identical signatures plus:

```python
# create-only: engine chosen by selector chain (R3); recorded in the manifest
def create(configs, *, engine: str | None = None, ..., connector_factory, ...) -> None

# all collection-touching ops: engine resolved FROM the collection (R2);
# an explicit conflicting `engine` raises EngineMismatchError
def search(query, ..., engine: str | None = None) -> Dict[str, Any]
def update(configs, ..., engine: str | None = None, manifest_factory) -> None
```

Routing rule (normative): **manifest wins for existing collections; the
selector chain only chooses the engine for new collections.** Precedence for
create: `--engine` flag > `INDEXED__CORE__ENGINE` > `[core] engine` in
config.toml > built-in default `"1"`.

### Engine detection (`indexed.core.versioning`)

```python
def detect_engine_version(collection_path: Path) -> Literal["1", "2"]
# manifest.json absent/unreadable -> collection-level IndexedError (existing behavior)
# manifest "version" key absent    -> "1"   (all pre-v2 collections)
# "version": "2"                   -> "2"
# anything else                    -> UnknownEngineVersionError (fail loud, R1)
```

### V2 manifest (`manifest.json`, new format — same filename, superset shape)

```jsonc
{
  "version": "2",
  "collectionName": "...",
  "createdTime": "...", "updatedTime": "...", "lastModifiedDocumentTime": "...",
  "numberOfDocuments": 0, "numberOfChunks": 0,
  "reader": { "type": "localFiles", ... },          // same block as v1 (from_manifest compat)
  "engine": {
    "embedding": { "provider": "local", "model": "sentence-transformers/all-MiniLM-L6-v2",
                    "dimension": 384 },
    "vectorStore": "simple",                        // "simple" (more stores: future work)
    "scoreKind": "cosine",                          // higher-is-better
    "llamaIndexCoreVersion": "0.14.23",             // rebuild-on-mismatch guard
    "indexedVersion": "0.0.5"
  }
}
```

Keeping `reader` identical to v1 lets the existing `manifest_factory` /
`from_manifest` dispatch work unchanged for v2 updates.

### V2 on-disk layout

```
<collections_path>/<name>/
├── manifest.json            # version-marked (above)
└── storage/                 # LlamaIndex StorageContext.persist() output:
    ├── docstore.json        #   node text + ref_doc hashes (upsert basis)
    ├── index_store.json
    └── default__vector_store.json   # SimpleVectorStore JSON (or absent for qdrant;
                                     #  qdrant data under storage/qdrant/)
```

Writes build aside into a staging dir and atomically rename-swap (same
durability contract as v1's `DiskPersister.replace_folder`); the prior
collection is never deleted before the replacement is durably written (fixes
the PR #86 delete-before-persist defect).

### Adapter (`core/v2/adapter.py`)

```python
def to_nodes(doc: dict, collection: str) -> list[TextNode]
# node id      = f"{doc['id']}::chunk_{i}"        (deterministic, stable)
# node.ref_doc_id -> doc["id"]                     (upsert/delete key)
# node.text    = chunk["indexedData"]
# node.metadata = {"source_id", "url", "modified_time", "chunk_number",
#                  "collection", **(chunk.get("metadata") or {})}
```

Connectors/parsing never import LlamaIndex; pre-chunked content bypasses
LlamaIndex node parsers entirely (transformations = [embed_model] only).

### Update semantics (R5)

Docstore hash upserts keyed on `ref_doc_id` (LlamaIndex `DocstoreStrategy`
semantics, verified): unchanged hash → skip; changed → delete + re-embed;
`ConnectorRun.deletions` → `delete_ref_doc`. Requires a store with working
`delete()` — satisfied by SimpleVectorStore and Qdrant; this is why
`FaissVectorStore` is excluded (its `delete()` raises `NotImplementedError`,
verified upstream).

### Search + scores (R11)

Retriever-only path (`as_retriever().retrieve()`), never `as_query_engine()`
(avoids the LLM/OpenAI default trap — verified LLM-free empirically).
v2 `score` = cosine similarity, higher-better. Cross-engine merged views
convert v1's squared-L2 to cosine exactly: `sim = 1 - d²/2` (valid because v1
embeddings are unit-normalized). `core.v2.search.score_threshold` keeps
results with `sim >= threshold` (range 0–1); v1 threshold semantics unchanged.
Optional rerank: `SentenceTransformerRerank` from llama-index-core (lazy
`CrossEncoder` import verified) with a configurable cross-encoder model.

**Interim per-collection sort fix (core-v2/2d):** v2's per-collection result
dict carries an additive `"scoreKind": "cosine"` field (v1's never had this
key). The CLI (`search_render.py`) and MCP (`mcp/formatting.py`) formatters
use it to sort each collection's OWN chunks best-first regardless of engine
(cosine descending vs v1's squared-L2 ascending) — this fixes a real R4 bug
(a v2 collection's worst chunk was showing as the top result) without
attempting cross-engine value comparability, which stays core-v2/6's job
(the `sim = 1 - d²/2` conversion above). A v1 collection carries no
`scoreKind` key, so its sort key and output are byte-identical to before
(R6).

### Config (`[core.v2.*]` + engine selector)

```toml
[core]
engine = "1"                       # default engine for NEW collections only

[core.v2.embedding]
model_name = "sentence-transformers/all-MiniLM-L6-v2"   # v1's model — 1:1 parity
batch_size = 32

[core.v2.search]
max_docs = 10
score_threshold = 0.0              # min cosine similarity, 0 disables

[core.v2.rerank]
enabled = false
model   = "cross-encoder/ms-marco-MiniLM-L-6-v2"
top_n   = 10
```

No `[core.v2.storage]` key yet — the manifest's `vectorStore` field is the
seam; a config knob arrives with the second store (no phantom generality).
No provider/credential keys — v2 is local-only this feature.

Registered explicitly in `composition.register_app_config` (never at import
time). Env overrides follow the existing mapping: `INDEXED__CORE__ENGINE`,
`INDEXED__CORE__V2__EMBEDDING__MODEL_NAME`, etc.

### Errors

`EngineMismatchError` / `UnknownEngineVersionError` inherit `IndexedError`
(CLI exit codes + MCP envelopes work unchanged). Mismatch message pattern:
`"Collection 'X' is a v1 collection. Re-run without --engine, use --engine v1,
or migrate it: indexed index migrate X"`. All LlamaIndex exceptions are
wrapped at the v2 service boundary into `IndexedError` subtypes (upstream has
no stable exception hierarchy — verified).

### Migration (R7)

`indexed index migrate <name> [--dry-run] [--from-source] [--purge-backup]`:
default reads stored v1 `documents/<id>.json` chunk texts (`indexedData`) and
re-embeds offline (no source access; v1 chunks are ≤256 tokens, within any
target model's window); `--from-source` re-reads via `from_manifest`. Builds
the v2 collection aside, validates (counts + probe search), then swaps; the v1
directory is preserved as `<name>.v1-backup` until `--purge-backup` (rollback
= rename back).

<!-- merge -->
### Engine routing contract (cross-cutting)

Core is consumed only through the version-dispatching facade
`indexed.core.engine` (same 14 names as the former `core.v1.engine` surface).
For existing collections the on-disk manifest `version` marker is
authoritative for engine choice — explicit selectors may only confirm it or
fail with `EngineMismatchError`; selectors (flag > env > config > default)
choose the engine for new collections only. Collections without a `version`
key are v1; unknown versions fail loud. No code above the facade may import
`core.v1.*` or `core.v2.*` directly.
<!-- /merge -->

---

## Implementation Detail

- **Laziness:** `import llama_index.core` costs ~1.0–1.4 s (verified
  empirically on 0.14.23) — every LlamaIndex import lives inside function
  bodies, exactly like torch today. The facade keeps the v1 lazy-`__getattr__`
  pattern; `indexed.core.engine` imports v1/v2 submodules only on dispatch.
- **No global state:** embed model, transformations, and postprocessors are
  passed explicitly per call; `Settings` is never read or written; retrieval
  path verified to never resolve `Settings.llm`.
- **Embeddings (native, 1:1 with v1):** `HuggingFaceEmbedding(model_name=
  "sentence-transformers/all-MiniLM-L6-v2")` from
  `llama-index-embeddings-huggingface` — the same `SentenceTransformer` class
  and HF cache as v1, so vectors match v1 exactly and no re-download occurs
  (maintainer decision: native support over an own adapter). Its one verified
  caveat is handled: the integration imports sentence-transformers at module
  top → the integration module itself is imported function-locally. `ty`
  analyzes the integration's source directly and needs no ignores (core-v2/2b
  finding — the "ships no py.typed" concern did not materialize in practice).
  `normalize=True` is the integration default (matches v1's unit-normalized
  vectors — verified in tests).
- **Dimension discovery:** LlamaIndex has no dimension API (verified) — v2
  embeds a probe string once at create and records `dimension` in the
  manifest (provider-agnostic, future-proof).
- **Dependency pinning:** exactly two new deps — `llama-index-core>=0.14,<0.15`
  and `llama-index-embeddings-huggingface` (pins `<0.15` upstream); ~30 MB
  marginal (torch/sentence-transformers already present). No optional extras
  this feature; future providers/stores (ollama, qdrant, …) arrive as extras
  later. Core minor bumps are a coordinated lockstep upgrade gated on the
  characterization suite. Persisted formats are treated as version-bound:
  `engine.llamaIndexCoreVersion` in the manifest triggers a clear
  rebuild-on-mismatch message if incompatibility is ever detected.
- **Concurrency:** the `simple` store is plain files + atomic swap — safe
  for the CLI-writes-while-MCP-reads pattern (a key reason it is the store).
- **MCP:** default engine resolved once in lifespan state (mirrors the
  verified PR #86 pattern); per-collection routing still applies per call.
  v2 MCP e2e tests must run out-of-process (in-process FastMCP client +
  llama-index + torch segfaulted — verified finding from PR #86).
- **Import gate:** `core/v2/**` obeys the existing edges (imports only
  `protocols`/`config`/`utils` + third-party). The generic `core` bucket rule
  in `scripts/check_imports.py` cannot see the `v1`/`v2` split, so core-v2/2d
  added an explicit `core/v2 ↛ core.v1` edge (with a negative self-test) on
  top of it — a file under `core/v2/**` may not import `indexed.core.v1.*`.
- **Disk read-cache (deferred residual, core-v2/2c/2d):** v1's create-time read
  cache (`CacheReaderDecorator` in `connectors`, backed by `core.v1`'s
  `DiskPersister`) lives in layers `core/v2` may not import, and it is a pure
  read-optimization that never changes the documents produced or the on-disk
  collection. v2 create therefore reads directly from the connector every time
  (`use_cache`/`caches_path`/`cache_decorator_factory` are accepted for
  signature parity and discarded); the produced collection is identical either
  way, only cross-create read caching is not yet wired. Follow-up: a v2-local
  persister, or a `utils`-level consolidation of `DiskPersister` shared by both
  engines — tracked for a future core-v2 unit, not blocking.

## Performance Budget

- CLI startup (`indexed --help`): <1 s (unchanged; enforced by lazy imports).
- v2 create: ≤1.5× v1 wall-time on the benchmark corpus (PR #86 measured
  +29% with FaissVectorStore; budget allows headroom for SimpleVectorStore).
- v2 warm search: ≤2× v1 at <100k chunks (brute-force NumPy vs FAISS FlatL2 is
  the same O(N·d); budget covers overhead), enforced via
  `tests/benchmarks` + the CI benchmark action.
- Wheel/install: no new mandatory heavy deps — llama-index-core adds ~30 MB
  marginal (torch/sentence-transformers already present; verified).

## Open Questions

1. **`[core] engine` registration shape** — a one-field model registered at
   path `core` coexisting with `core.v1.*`/`core.v2.*` subtables needs a
   registry check (TOML allows it; verify `ConfigRegistry`/`bind()` handles a
   scalar-bearing parent path).
2. **`nest-asyncio` interaction with FastMCP** — llama-index-core depends on
   it; behavior under FastMCP's event loop is unverified. Probe early in
   core-v2/2 (a failing probe moves MCP v2 search to a worker thread).
