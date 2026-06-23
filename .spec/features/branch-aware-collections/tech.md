---
type: feature-tech
feature: branch-aware-collections
sibling: product.md
parent: ../../tech.md
updated: 2026-06-23
---

# Feature: Branch-Aware Collections — Architecture

Introduces a per-branch storage layout under each collection and a shared,
content-hash-keyed embedding store. Branch resolution reuses the git plumbing
already in `ChangeTracker`; the collection creator routes index/document writes
into a branch-scoped subtree and consults the embedding store before calling the
embedder. Legacy single-index collections are migrated lazily to the default
branch on first access.

**Parent:** [../../tech.md](../../tech.md) / **Requirements:** [product.md](product.md) / **Plan:** [plan.md](plan.md)

## Files

```
packages/indexed-connectors/src/connectors/files/change_tracker.py
  + IndexState.last_indexed_branch field; _current_git_branch() via
    `git rev-parse --abbrev-ref HEAD`; populate in build_state().        (~25 LOC)

packages/indexed-config/src/indexed_config/storage.py
  + branch path helpers: get_branch_root(), get_embeddings_store_path(),
    sanitize_branch(); document new layout in module docstring.          (~40 LOC)

packages/indexed-core/src/core/v1/engine/core/branch_resolver.py  [NEW]
  + BranchResolver: resolve active branch (git → fallback "default"),
    sanitize, expose store/variant paths.                                (~80 LOC)

packages/indexed-core/src/core/v1/engine/core/embedding_store.py  [NEW]
  + EmbeddingStore: content_hash → vector, persisted via DiskPersister;
    get_or_embed() reuses cached vectors, embeds misses in one batch.    (~120 LOC)

packages/indexed-core/src/core/v1/engine/core/documents_collection_creator.py
  ~ route index/document paths through a branch segment; call
    EmbeddingStore before indexer.index_texts; write schemaVersion +
    branch into manifest.                                                 (~60 LOC)

packages/indexed-core/src/core/v1/engine/core/documents_collection_searcher.py
  ~ resolve active branch, load matching variant, migrate legacy on read. (~40 LOC)

packages/indexed-core/src/core/v1/engine/core/migration.py  [NEW]
  + migrate_legacy_collection(): flat indexes/+documents/ under
    branches/default/; stamp schemaVersion=2.                            (~70 LOC)

tests/  + resolver, store, migration, creator/searcher routing.         (~250 LOC)
```

## Contract / API

```python
# change_tracker.py — extend persisted state
@dataclass
class IndexState:
    last_indexed_commit: str | None = None
    file_hashes: dict[str, str] | None = None
    last_indexed_at: str | None = None
    indexed_file_count: int = 0
    last_indexed_branch: str | None = None        # NEW

# branch_resolver.py
DEFAULT_BRANCH = "default"

class BranchResolver:
    def __init__(self, source_path: str) -> None: ...
    def active_branch(self) -> str:
        """`git rev-parse --abbrev-ref HEAD`; 'default' if non-git/detached/HEAD."""
    @staticmethod
    def sanitize(branch: str) -> str:
        """Filesystem-safe segment, e.g. 'feature/x' -> 'feature__x'."""

# embedding_store.py
class EmbeddingStore:
    def __init__(self, persister, collection_name: str) -> None: ...
    def get_or_embed(
        self,
        items: list[tuple[str, str]],   # (content_hash, contextualized_text)
        embed_batch,                    # callable[[list[str]], np.ndarray]
    ) -> dict[str, "np.ndarray"]:
        """Return hash -> vector, embedding only cache misses, then persist."""

# storage.py — new path helpers (root = resolved storage root)
def get_branch_root(root: Path, collection: str, branch: str) -> Path: ...
def get_embeddings_store_path(root: Path, collection: str) -> Path: ...
```

## Implementation Detail

**New on-disk layout** (under `data/collections/<name>/`):

```
manifest.json                      # + schemaVersion, branches[], activeBranch
embeddings/store.json              # content_hash -> vector (shared, all branches)
branches/<branch>/
  documents/*.json
  indexes/index_info.json
  indexes/index_document_mapping.json
  indexes/reverse_index_document_mapping.json
  indexes/indexer_FAISS_*/indexer.faiss
state.json                         # ChangeTracker state, now branch-tagged
```

`<branch>` is `BranchResolver.sanitize(active_branch())`. Non-git sources and
detached HEAD both yield `default`, reproducing today's single-variant behavior.

**Branch resolution:** `BranchResolver.active_branch()` runs
`git rev-parse --abbrev-ref HEAD` (cwd = source path), mirroring the existing
`_current_git_commit`/`_git_toplevel` calls in `change_tracker.py`. Output `HEAD`
(detached) or a non-zero exit (no git) maps to `DEFAULT_BRANCH`. `ChangeTracker`
also records `last_indexed_branch` in `build_state()` so updates know which
variant the persisted hashes belong to.

**Embedding reuse:** `documents_collection_creator.py` currently calls
`indexer.index_texts(index_item_ids, items_to_index)` with the
`chunk["indexedData"]` (contextualized text). The new flow first asks
`EmbeddingStore.get_or_embed([(content_hash, text), ...], embed_batch)`; the store
loads `embeddings/store.json`, returns hits, embeds only the misses in a single
batch (default 128 per `tech-core.md`), persists the union atomically, then the
creator hands precomputed vectors to the indexer. Because the store is keyed on
`ParsedChunk.content_hash` (xxhash of chunk text, see
`packages/indexed-parsing/src/parsing/schema.py`), a chunk identical across
`main` and a feature branch is embedded exactly once.

**Search:** `documents_collection_searcher.py` resolves the active branch via
`BranchResolver`, then loads the variant under `branches/<branch>/indexes/`.
Searcher caching (per `tech-core.md`) is keyed by `(collection, branch)`.

**Migration:** on first read of a collection whose `manifest.schemaVersion` is
absent/`1`, `migration.migrate_legacy_collection()` moves the flat `documents/`
and `indexes/` into `branches/default/` and stamps `schemaVersion=2`; the default
branch re-embeds on its next update if no `embeddings/store.json` backfill is
feasible. All moves go through `DiskPersister` atomic rename semantics, so the
migration is idempotent and never re-indexes on its own.

## Performance Budget

- Branch resolution: one `git rev-parse` (bounded by the same 5 s timeout as the
  sibling git calls in `change_tracker.py`).
- Branch switch with fully-cached embeddings: zero embedder calls — cost is the
  FAISS index build from cached vectors only.
- Search latency unchanged (<1 s for 10k–100k docs), per `tech-core.md`.
