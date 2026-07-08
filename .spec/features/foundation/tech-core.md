---
type: feature-tech
feature: foundation
sibling: product.md
parent: ../../tech.md
updated: 2026-07-08
---

# Feature: Foundation — Engine (core) architecture detail

The engine side of the architecture + correctness work: replace stringly-typed
dict contracts with typed models at the creator/searcher/service seams, fix the
chunk→embed recall path (R4), make FAISS persistence durable on every mutation
path (R5), guard the zero-chunk batch (R5), and put a real facade over
creator/searcher/services with two required injected callables (R2). All of this
lands in the CURRENT layout (`packages/indexed-core/src/core/v1/engine/…`); the
workspace collapse is a separate feature. Design every contract so it does **not**
depend on the dead generality (indexer registry, multi-indexer lists, 500k
batching) that Feature `simplify` deletes.

**Overview:** [tech.md](tech.md)
**Requirements:** [product.md](product.md)

Requirement anchors touched here: R1
[typed data contracts](product.md#requirement-typed-data-contracts), R2
[core swap seam](product.md#requirement-core-swap-seam), R4
[search recall correctness](product.md#requirement-search-recall-correctness), R5
[storage durability](product.md#requirement-storage-durability).

---

## Files (engine surface this detail owns)

```
packages/indexed-core/src/core/v1/
  engine/core/
    documents_collection_creator.py   read→convert→chunk→embed→index→persist   ~508 LOC
    documents_collection_searcher.py  load index + map ids→docs, cached          ~135 LOC
  engine/services/
    models.py           CollectionStatus/Info dataclasses + re-exports           ~88 LOC
    collection_service.py  create/update/clear orchestration + DI                ~192 LOC
    search_service.py      SearchService (cache) + _filter_by_score + SearchArgs  ~377 LOC
    inspect_service.py     status/inspect over manifest dicts                     ~422 LOC
  engine/factories/
    create_collection_factory.py  builds creator (CREATE)                         ~88 LOC
    update_collection_factory.py  builds updater (UPDATE) + _UpdatingCollectionCreator
    search_collection_factory.py  builds searcher
    _types.py             ManifestConnectorFactory / LocalFilesUpdateFactory aliases
  engine/indexes/
    indexer_factory.py    create_indexer / load_indexer                          ~98 LOC
    indexer_registry.py   name↔config, prefixes, list_* (DEAD generality)        ~164 LOC
    indexers/faiss_indexer.py   IndexIDMap(IndexFlatL2), embed+add/remove/search  ~51 LOC
    embeddings/sentence_embeder.py  lazy model, embed / embed_batch               ~69 LOC
  engine/persisters/disk_persister.py  atomic text + faiss write, _safe_join      ~111 LOC
  config_models.py        CoreV1*Config + get_default_*_path                      ~183 LOC
packages/indexed-parsing/src/parsing/
  code_chunker.py         tree-sitter AST chunker                                 ~282 LOC
  plaintext_parser.py     markdown(Docling)/generic paragraph split              ~173 LOC
  docling_parser.py       rich formats via Docling                               ~130 LOC
  router.py               extension → ParsingStrategy                            ~108 LOC
```

Target new modules (introduced by foundation/7 + foundation/8): the typed models
and corrected `protocols.py` live in the **`protocols` leaf package**
(`packages/indexed-protocols/src/protocols/`), which creator/searcher/services
import instead of `dict["stringKey"]` — the leaf is the only import-legal home
since connectors/config/protocols may not import `core` (see tech.md §1 and §5).
The `core` facade over the three services stays under `core/v1/`. Exact package
locations collapse into the single package in Feature `simplify`.

---

## Contract / API

### 1. Typed models applied at the engine seams (R1)

The engine currently moves three untyped dict shapes across disk. Every model
below must **serialize back byte-stable** so existing collections on disk keep
loading — round-trip is the compatibility boundary for the v2 swap (R2). Use
`model_config = ConfigDict(populate_by_name=True)` + `Field(alias=…)` and dump
with `by_alias=True`, matching the current writer (`_json_dumps(..., indent=True)`
→ `orjson.OPT_INDENT_2`, 2-space indent; the fallback path uses
`json.dumps(indent=2, ensure_ascii=False)`).

**Manifest** — current on-disk shape is the dict built verbatim in
`documents_collection_creator.py:494-504`:

```python
# CURRENT — __create_manifest_content(), documents_collection_creator.py:494
return {
    "collectionName": self.collection_name,
    "updatedTime": update_time.isoformat(),
    "lastModifiedDocumentTime": last_modified_document_time.isoformat(),
    "numberOfDocuments": number_of_documents,
    "numberOfChunks": number_of_chunks,
    "reader": self.document_reader.get_reader_details(),   # per-source dict, has "type"
    "indexers": [{"name": indexer.get_name()} for indexer in self.document_indexers],
}
```

The update path mutates this dict in place with camelCase string keys
(`documents_collection_creator.py:154,160-164,488-491`) and the existing-manifest
branch does `{**existing_manifest, "updatedTime": …}` (`:485-492`). Target:

```python
# TARGET — models.py
class Manifest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    collection_name: str            = Field(alias="collectionName")
    updated_time: str               = Field(alias="updatedTime")   # keep isoformat str, not datetime, to round-trip byte-exact
    last_modified_document_time: str = Field(alias="lastModifiedDocumentTime")
    number_of_documents: int        = Field(alias="numberOfDocuments")
    number_of_chunks: int           = Field(alias="numberOfChunks")
    reader: ReaderDetails                       # extra="allow"; carries "type" + per-source fields
    indexers: list[IndexerRef]                  # [{"name": …}] — SEE dead-generality note below
```

- Keep `updated_time` / `*_time` as ISO **strings**, not `datetime`. The current
  code writes `update_time.isoformat()` (tz-aware, `+00:00`) but the
  deletions-only branch writes `update_time.isoformat()` too while
  `lastModifiedDocumentTime` comes from `datetime.fromisoformat(doc["modifiedTime"])`
  which may be naive. Parsing to `datetime` and re-serializing would normalize
  offsets and break byte-stability; store the raw string.
- `reader` uses `extra="allow"` so per-source keys (`baseUrl`, `basePath`,
  `query`, `spaceKey`, …) survive untouched — mitigates "manifest model vs.
  in-the-wild collections" (round-trip test against a fixture manifest per source).
- **Where the engine stops using `dict["stringKey"]`:**
  `documents_collection_creator.__update_collection` (`:132-193`) parses the
  manifest into `Manifest`, mutates typed fields, and dumps by alias;
  `search_service._get_default_indexer` (`:120-127`, `manifest["indexers"][0]["name"]`),
  `inspect_service` (`manifest.get("reader", {}).get("type")` `:183,285`;
  `idx["name"] for idx in manifest.get("indexers", [])` `:196,304`), and
  `update_collection_factory` (`manifest["reader"]["type"]` `:84`,
  `manifest["indexers"]` `:99-102`) all read the typed model instead. A field
  rename becomes a mypy error, not a `KeyError` at runtime (R1).

**ConvertedDocument + Chunk** — current on-disk shape is what `V1FormatAdapter.
converter_output` emits (`connectors/files/v1_adapter.py:92-107`) and what the
creator reads back at `documents_collection_creator.py:307-333`:

```python
# CURRENT — one converted document per <id>.json on disk
{
    "id": rel_path,                     # e.g. "utils/retry.py"
    "url": "file:///abs/path",
    "modifiedTime": "2026-06-01T12:00:00",
    "text": "utils/retry.py\n\n<full contextualized text>",
    "chunks": [
        {"indexedData": "utils/retry.py"},                       # chunk 0 = path (v1 convention)
        {"indexedData": "<contextualized chunk text>", "metadata": {...}},
        ...
    ],
}
```

The creator indexes `converted_document["chunks"][n]["indexedData"]` as the embed
input (`:324`) and stores the doc-level map value
`{"documentId", "documentUrl", "documentPath", "chunkNumber"}` (`:328-333`); the
searcher reads those exact keys back (`documents_collection_searcher.py:76-100,
115`). Target:

```python
# TARGET — models.py
class Chunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    indexed_data: str = Field(alias="indexedData")
    metadata: dict | None = None            # omit-when-None to match current writer (chunk 0 has no metadata key)

class ConvertedDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    url: str
    modified_time: str = Field(alias="modifiedTime")
    text: str
    chunks: list[Chunk]
```

Byte-stability caveat: chunk 0 is `{"indexedData": rel_path}` with **no**
`metadata` key; later chunks add `metadata` only when truthy (`v1_adapter.py:92-97`).
Use `model_dump(by_alias=True, exclude_none=True)` so the absent key stays absent.
The creator's per-index mapping value and the searcher result dict likewise become
small models (`IndexMapEntry`, `DocumentMatch`, `MatchedChunk`) — see §4.

**SearchResult** — current searcher return is a dict with camelCase keys
(`documents_collection_searcher.py:53-57`); the service wraps errors as
`{"error": str(e)}` (`search_service.py:295`). Target per collection:

```python
# TARGET — models.py
class MatchedChunk(BaseModel):
    chunk_number: int = Field(alias="chunkNumber")
    score: float
    content: str | dict | None = None       # present only when include_matched_chunks

class DocumentMatch(BaseModel):
    id: str; url: str; path: str
    matched_chunks: list[MatchedChunk] = Field(alias="matchedChunks")

class CollectionSearchResult(BaseModel):
    collection_name: str = Field(alias="collectionName")
    indexer_name: str    = Field(alias="indexerName")
    results: list[DocumentMatch] = Field(default_factory=list)
    error: str | None = None
```

### 2. Corrected protocols (R1, R2) — what the engine actually calls

`protocols.DocumentReader` today declares only `read_documents()`
(`protocols/connectors.py:15`), which **no engine code calls**. The creator calls
`get_number_of_documents()` (`:202`), `read_all_documents()` (`:225`),
`get_reader_details()` (`:500`); the converter is called as `convert(document)`
returning an iterator of the ConvertedDocument dicts (`:226`). All those call
sites are `Any`-typed, so mypy is blind. Target:

```python
# TARGET — protocols.py
@runtime_checkable
class DocumentReader(Protocol):
    def get_number_of_documents(self) -> int: ...
    def read_all_documents(self) -> Iterator[Any]: ...
    def get_reader_details(self) -> dict: ...

class DocumentConverter(Protocol):
    def convert(self, doc: Any) -> Iterator[ConvertedDocument]: ...
```

`DocumentCollectionCreator.__init__` (`documents_collection_creator.py:41-63`) and
`DocumentCollectionSearcher.__init__` get these annotations, so a reader missing
`get_reader_details` is a mypy error, not a runtime `AttributeError`.

### 3. Facade over creator/searcher/services (R2)

Today the app reaches the engine through three service modules
(`collection_service`, `search_service`, `inspect_service`) plus three factories,
with **four** injected `Callable | None` params guarded by `missing_wiring_error`
(`collection_service.py:26,76-77,107-108`;
`create_collection_factory.py:27,63`; `update_collection_factory.py:37-38,88-89,
144-145`). Target facade (single import point for cli/mcp), reducing to **two
required** callables:

```python
# TARGET — core facade
def create(configs, *, connector_factory, paths, use_cache=True, force=False, progress=None) -> None
def update(names,   *, manifest_factory, paths, progress=None) -> None
def search(query,   *, collections=None, paths, **filters) -> dict[str, CollectionSearchResult]
def inspect(name,   *, paths) -> CollectionInfo
def remove(names,   *, paths) -> None
```

- `connector_factory` (create-time) and `manifest_factory` (update-time) are the
  ONLY two seams; both are required positionals/keywords — no `| None`, no
  `missing_wiring_error`. `cli/composition.py` is the single binder (owned by
  tech-config-app / foundation/8).
- The `localFiles` special-case in `update_collection_factory.py:87-97` and the
  private-attribute wiring it implies are removed: each connector's
  `from_manifest(...)` returns `(reader, converter, deletions, post_run)`, so the
  updater calls one path for every source. Detail on the connector side lives in
  [tech-connectors.md](tech-connectors.md); engine-side, the factory stops
  branching on `manifest["reader"]["type"]`.
- `_UpdatingCollectionCreator` (`update_collection_factory.py:121-136`) — the
  post-run-hook wrapper — is a `simplify` deletion; foundation keeps it but the
  facade contract must not assume it (the `post_run` callable rides in the
  `from_manifest` tuple).

### 4. Search recall + score contract (R4)

```python
# TARGET — DocumentCollectionSearcher.search signature (unchanged) but new internals
def search(self, text, max_number_of_chunks=15, max_number_of_documents=None, ...):
    # fetch >= max_chunks neighbors; group to docs; STOP at max_docs docs
    # but keep collecting chunks until max_chunks OR docs exhausted
```

- **`max_chunks` independent of `max_docs`.** Today `max_chunks` defaults to
  `max_docs * 3` (`search_service.py:230-231`) and the searcher fetches exactly
  that many FAISS neighbors then truncates docs with `results[:max_docs]`
  (`documents_collection_searcher.py:41,50-51`). One many-chunk doc (any code
  file) fills top-k and starves other docs. Fetch neighbors sized to satisfy BOTH
  limits (e.g. over-fetch, group, then take `max_docs` docs while retaining up to
  `max_chunks` matched chunks); `max_chunks` is a hard cap, not a derived value.
- **Backfill after `_filter_by_score`.** `_filter_by_score` runs *after* the
  `max_docs` truncation (`search_service.py:273-284` calls searcher which already
  truncated; filter at `:129-167`), so a threshold that drops the single returned
  doc yields fewer than `max_docs` with no backfill. Apply the score filter to the
  full candidate set, THEN take `max_docs`, so filtered slots are backfilled from
  the next-best surviving docs.
- **Score is squared L2 in [0, 4], lower = better.** `FaissIndexer` is
  `IndexIDMap(IndexFlatL2)` (`faiss_indexer.py:19-21`); `IndexFlatL2.search`
  returns **squared** L2 distances, and embeddings are unit-normalized (research
  "Cleared": ranking correct, squared-L2 monotonic with cosine), so the range is
  [0, 4]. The searcher passes `float(scores[0][result_number])` straight through
  (`documents_collection_searcher.py:116`). Correct the docstrings that call it
  "raw L2" / "distance" — package `CLAUDE.md` says "raw L2 distance"; it is
  squared. `_filter_by_score` keeps `score <= threshold`
  (`search_service.py:156-160`), which is the correct direction (lower=better).
- **`score_threshold` scale/range/description (bug #6).**
  `config_models.py:106` constrains `score_threshold` to `ge=0.0, le=1.0` with
  description "Minimum similarity score threshold". Squared-L2 lives in [0, 4] and
  lower is better, so a sane threshold like `1.5` is unconfigurable and the
  service docstring's own `score_threshold=1.5` example (`search_service.py:218`)
  fails validation. Fix: widen to `ge=0.0, le=4.0`, rewrite the description to
  "Maximum squared-L2 distance (lower = closer; range 0-4)". No inversion of the
  comparison is needed — only the bound + wording.

### 5. Chunker contract (R4)

The chunkers are told `max_tokens` but the parameter is silently dropped, and the
embedder window is half the target chunk, so most of every large doc is
unsearchable.

- **`HierarchicalChunker(max_tokens=…, include_metadata=…)` silently drops both
  kwargs** (`plaintext_parser.py:48-51`, `docling_parser.py:61-64`). Its real
  fields are `delim, serializer_provider, code_chunking_strategy,
  always_emit_headings, merge_list_items` — no size bound. A headingless body of
  any size becomes one chunk. Replace with a token-aware / size-bounded chunker
  (Docling's `HybridChunker`, which the `DoclingParser` docstring already claims
  but the code does not use — `docling_parser.py:16`) or a post-split that
  enforces the invariant below. `include_metadata` is not a `HybridChunker` kwarg
  either; drop it and read `ch.meta` as the code already does (`:91-98`).
- **Chunk-size invariant.** Every emitted chunk's tokenized length under the
  embedder's tokenizer MUST be `<= embedder.max_seq_length`. For the default
  `all-MiniLM-L6-v2`, `SentenceTransformer.max_seq_length == 256`
  (set on the model in `sentence_embeder.py` via the lazy `model` property,
  `:18-21`); chunkers currently target `max_tokens=512` (constructors:
  `code_chunker.py:96`, `plaintext_parser.py:20`, `docling_parser.py:24`) —
  exactly 2× the window (bug #4). Source the max-token bound FROM the embedder
  (`self.model.max_seq_length`) rather than a hardcoded 512, and add a guard in
  the embed path so an over-long chunk is split, not silently truncated at 256.
  Note `config_models.CoreV1IndexingConfig.chunk_size` default is also 512
  (`:16-17`); reconcile it to the embedder window or wire it through (today it is
  a dead config section — see [tech-config-app.md](tech-config-app.md)).
- **`code_chunker` must slice the byte buffer, not the decoded str (bug #2).**
  `chunk_file` does `source = path.read_bytes()` then
  `source_text = source.decode(errors="replace")` and slices
  `source_text[child.start_byte:child.end_byte]` (`code_chunker.py:115-117,148`).
  tree-sitter's `start_byte`/`end_byte` are **byte** offsets; indexing them into a
  decoded `str` shifts every slice after the first non-ASCII byte → wrong/empty
  chunks (reproduced). Target: slice `source[child.start_byte:child.end_byte]`
  (bytes) and `.decode("utf-8", errors="replace")` per node; keep line numbers
  from `child.start_point[0]` / `end_point[0]` which are already correct.
- **Plaintext splitter must break structured text (bug #3).**
  `_split_paragraphs` only splits on `"\n\n"` (`plaintext_parser.py:138`);
  CSV/JSON/YAML/log/XML with no blank lines stay one giant chunk → truncated at
  256. Add a size-bounded fallback split (by line, then by hard character/token
  budget) so a blank-line-free file still yields window-sized chunks. All
  `PLAINTEXT_EXTENSIONS` (`router.py:61-84`) route here.

### 6. Storage durability (R5)

**FAISS index persistence on every mutation path.** `save_faiss_index` is called
in exactly one place — `__add_documents_to_index` (`documents_collection_creator.py:
369-374`). Enumerate the mutation paths and require the save on ALL of them:

| Path | Code | Persists `indexer.faiss` today? |
|---|---|---|
| CREATE (add) | `__index_documents_for_new_collection` → `__add_documents_to_index` `:252-259` | YES (`:371`) |
| UPDATE remove-then-add | `__index_documents_for_existing_collection` `:261-279` | YES (via add `:277`) |
| UPDATE deletions-only | `__update_collection` `:158-169` | **NO** — mutates in-memory index + writes mapping JSONs only |
| UPDATE explicit-deletions | `__remove_explicit_deletions` `:408-436` | **NO** — `remove_ids` on in-memory index, saves mapping JSONs only |

The deletions-only and explicit-deletions branches call `remove_ids` on the
in-memory FAISS index (`faiss_indexer.remove_ids` `:32-33`) and save the mapping
JSONs, but never write the `.faiss` file. On next load the on-disk vectors outlive
their mapping keys → `KeyError` at `documents_collection_searcher.py:76`
(`index_document_mapping[str(index_id)]`) for any query whose top-k hits an orphan
→ the whole collection returns `{"error": …}` (bug #7, reproduced end-to-end; the
post-run hook saves ChangeTracker state so it never self-heals). Fix: call
`persister.save_faiss_index(indexer.get_faiss_index(), …)` after `remove_ids` in
both branches (`:164` region and `:429-431` region). Note `load_indexer` reads the
index memory-mapped (`indexer_factory.py:79`, `IO_FLAG_MMAP`); mutate-then-resave
on an mmap'd index works (research "Cleared").

**Safe rebuild on create (bug #8).** `__create_collection` first calls
`self.persister.remove_folder(self.collection_name)` (`documents_collection_creator.py:77`)
before building anything. A failing re-create (bad path, zero docs, embed crash)
destroys the existing collection despite the atomic-write persister. Target:
build into an aside directory (`<name>.tmp-<pid>`) and swap by rename on success —
`os.replace` on the folder (or write into a temp dir then rename), mirroring the
per-file `tmp → fsync → os.replace` the persister already does
(`disk_persister.py:21-33,47-49`). The unconditional `remove_folder(name)` at
`:77` is replaced by build-aside + rename-swap; only remove the OLD folder after
the new one is in place. (The existing zero-docs guard already re-removes the
folder at `:88` — that path also becomes "discard the aside dir", leaving the
prior collection intact.)

**Non-transactional 4-file commit.** A successful add writes four artifacts with
no ordering guarantee: `indexer.faiss` (`:371`), `index_info.json` (`:379`),
`index_document_mapping.json` (`:380`), `reverse_index_document_mapping.json`
(`:381-383`), plus `manifest.json` later (`:467`). Each individual file write is
atomic (persister), but a crash between them leaves the FAISS vectors and the
mapping JSONs inconsistent — the same orphan-key failure as bug #7. Order the
commit so the mapping JSONs (which the searcher keys into) are written BEFORE (or
transactionally with) the `.faiss` file, and write `manifest.json` LAST as the
commit marker. A fuller fix (staging dir + single rename for the whole
`indexes/` set) is compatible with the safe-rebuild aside directory above; at
minimum guard the order so a partial write can't produce mapping keys without
matching vectors or vice-versa.

**Zero-chunk batch guard (bug #9, R5).** A document with no chunks (Outline
empty-body docs; any converter that yields `chunks: []`) drives an empty
`items_to_index` into the embedder. Both embed paths crash:
`SentenceEmbedder.embed_batch` with a progress callback does
`np.vstack([])` on an empty list (`sentence_embeder.py:44-58`); without a callback
`self.model.encode([])` returns shape `(0,)`, which then unpacks wrong at
`faiss_indexer.py:26-30` (`add_with_ids` on a `(0,)` array). In CREATE this fires
*after* the folder was deleted (compounding bug #8). Guard: in `embed_batch` /
`embed`, return an empty `(0, dim)` array for empty input; in
`FaissIndexer.index_texts` (`:26-30`), no-op when `ids`/`texts` are empty (mirror
the existing empty-`remove_ids` no-op noted as "Cleared"). Batch-vs-single embed
is already consistent (research "Cleared": max diff 1.3e-7) — do NOT touch the
encode call semantics, only the empty-input boundary.

### 7. Engine → services upward import (R2)

`documents_collection_creator.py:28` imports **upward** from
`core.v1.engine.services.models`:

```python
# CURRENT — the cycle
from core.v1.engine.services.models import (
    ProgressUpdate, ProgressCallback, PhasedProgressCallback,
)
```

Core (`engine/core/…`) importing from `engine/services/…` is the cycle that
forced the lazy import in `collection_service.py:111-115` and the `_types.py` leaf
module. `services/models.py` in turn re-exports these from `protocols.models`
(`services/models.py:4-9,79-87`). Fix: point the creator (and searcher) at the
protocol/model home directly — the progress types move into the typed `models.py`
(a `Progress` protocol + a phase-name enum replacing the magic strings
`"Preparing"`/`"Scanning Files"`/`"Fetching Documents"`/`"Generating Embeddings"`
threaded through `documents_collection_creator.py:110-248,342-351`). No engine
`core/` module imports `engine/services/` after this; the lazy import in
`collection_service` and `_types.py`'s cycle-avoidance reason disappear (the
module itself is a `simplify` deletion).

---

## Dead generality — design contracts to NOT depend on it

These exist to approximate a plugin surface that has exactly one implementation.
Feature `simplify` **deletes** them; foundation must not build the typed contracts
or facade on top of them.

- **Indexer registry / factory / naming scheme.**
  `indexer_registry.py` (164 LOC: `INDEXER_CONFIGS`, `INDEXER_PREFIX`,
  `build_indexer_name`, `list_available_indexers`, `is_auto_indexer`,
  `extract_model_name`) + `indexer_factory.py` exist to map a long name string
  (`indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2`) to one config. There
  is exactly one indexer (`faiss_indexer.py`). The `Manifest.indexers` model keeps
  the `[{"name": …}]` on-disk shape for byte-compat, but do NOT thread the
  registry's naming machinery into the typed contract — the model stores the name
  string opaquely; `simplify` collapses the whole scheme to a constant.
- **Multi-indexer lists / loops.** The creator holds `document_indexers` as a list
  and loops it (`documents_collection_creator.py:58,353-356,369-374,405-406`);
  `manifest["indexers"]` is a list; services read `[0]`
  (`search_service.py:124`, `inspect_service.py:196,304`,
  `update_collection_factory.py:99-102`). Only ever one element. Typed models keep
  a `list` for byte-compat but the facade signatures and search/inspect contracts
  should treat "the indexer" as singular (take `[0]`); do not expose multi-indexer
  fan-out in the new contracts.
- **`indexing_batch_size=500_000`** (`documents_collection_creator.py:49,298-300,
  390-392,450-451`) — a batch size larger than any real collection, so
  `__batch_items` always returns a single batch. The typed creator contract should
  not surface a batch-size knob; embedding is already internally batched by
  `SentenceEmbedder.embed_batch` (`sentence_embeder.py:26-65`). (Separately note:
  `FaissIndexer.index_texts` hardcodes `batch_size=64` at `:28`, ignoring both the
  embedder default 128 and `CoreV1EmbeddingConfig.batch_size` — a config-wiring
  bug tracked in [tech-config-app.md](tech-config-app.md), not a contract to
  preserve.)
- **`SearchArgs` DTO** (`search_service.py:368-377`) — zero usages; delete-list,
  do not reference from the search contract.

<!-- merge -->
## Engine contract rules (post-foundation)

- The three on-disk shapes (manifest, converted document + chunk, per-collection
  search result) are typed Pydantic models with camelCase aliases; the engine
  reads/writes them by model, never by `dict["stringKey"]`. `model_dump(by_alias=
  True, exclude_none=True)` is the byte-compatibility boundary for the v2 core swap.
- Reader/converter protocols declare the methods the engine actually calls
  (`get_number_of_documents` / `read_all_documents` / `get_reader_details` /
  `convert`), annotated on the creator/searcher so a mismatch is a mypy error.
- Chunk-size invariant: every chunk tokenizes to `<= embedder.max_seq_length`
  (256 for all-MiniLM-L6-v2), sourced from the embedder, not a hardcoded 512.
- FAISS is persisted on every mutating path (create, add, remove-then-add,
  deletions-only, explicit-deletions); create builds aside and rename-swaps so a
  failure never destroys the prior collection.
- One indexer, no registry/factory/naming machinery in the contracts; batch size
  is internal to the embedder.
<!-- /merge -->

## Open Questions

1. **Full-index staging vs. per-file guard for the 4-file commit.** The safe
   minimum (order writes, manifest last) closes bug #7's crash window loosely; a
   staging-dir + single rename for the whole `indexes/` set is airtight and
   composes with the safe-rebuild aside directory, at the cost of more I/O on
   incremental updates (which rewrite the whole mapping JSON anyway). Decide in
   foundation/3 whether deletions-only updates justify full staging or just the
   added `save_faiss_index` + ordering.
