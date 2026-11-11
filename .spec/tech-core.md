---
type: branch
scope: core
parent: tech.md
covers: engine components, embedding strategy, FAISS indexing, persistence, search performance
updated: 2026-11-11
---

# Tech Branch: Core Engine (`src/indexed/core/`)

Indexing & search engine. Receives connectors via dependency injection; never
imports concrete connectors, CLI, or MCP (see [tech.md](tech.md) § Architectural Rules).

**Parent: [tech.md](tech.md).** Pipelines (cross-component): [tech.md](tech.md) § Data Flow.

---

## Engine Components

| Component | Role |
|-----------|------|
| **DocumentCollectionCreator** | Orchestrates read → convert → chunk → embed → index → persist |
| **DocumentCollectionSearcher** | Loads index + maps results; cached across queries |
| **FaissIndexer** | Vector storage + similarity search |
| **SentenceEmbedder** | Embedding generation (lazy-loaded) |
| **DiskPersister** | Atomic disk persistence |

---

## Typed Data Contracts

The three on-disk shapes the engine moves — the collection **manifest**, each
**converted document + chunk**, and each per-collection **search result** — are typed
Pydantic models in the `protocols` leaf (`protocols/models.py`: `Manifest`,
`ConvertedDocument`, `Chunk`, `CollectionSearchResult`). The engine reads and writes them
by model, never by `dict["stringKey"]`, so a field rename is a ty error rather than a
runtime `KeyError`. `model_dump(by_alias=True, exclude_none=True)` reproduces today's
camelCase JSON **byte-stable** — the on-disk v1 format is the compatibility boundary for
the v2 core swap. Full contract: [tech.md](tech.md) § Protocols Package.

---

## Embedding Strategy

**Default:** `all-MiniLM-L6-v2` — 384-dim, ~22MB, fast, good general quality.
**Alternatives:** `all-mpnet-base-v2` (768-dim, higher quality), `multi-qa-distilbert-cos-v1` (768-dim, Q&A).

### Lazy loading

**File:** `src/indexed/core/v1/engine/indexes/embeddings/sentence_embeder.py`

`SentenceEmbedder` exposes the model via a lazy `@property` — the heavy model is
loaded (and cached) on first access, not at import:

```python
@property
def model(self):
    """Lazy-load the embedding model on first access."""
    return get_embedding_model(self.model_name)
```

### Model cache contract

**Files:** `src/indexed/core/v1/engine/indexes/embeddings/model_manager.py`,
`src/indexed/core/v2/embedding/local.py`, `src/indexed/core/model_acquisition.py`

The embedding model lives in the shared HF hub cache (`HF_HUB_CACHE` >
`HF_HOME/hub` > `~/.cache/huggingface/hub`, `models--<org>--<name>/snapshots/<rev>/`).
A model counts as **cached** only when a snapshot holds a real weights file
(`model.safetensors` / `pytorch_model.bin`, resolving to a completed blob) — hub
symlinks a snapshot file only once its blob completes, so an interrupted download
leaves config/tokenizer files WITHOUT weights, and a weights-blind "any file"
check would pin the load offline (`local_files_only=True`) and then fail on the
missing weights — one interrupted download bricks every embedding op until a
manual re-download. v1 (`is_model_cached`) and core.v2 (`_is_model_cached`)
carry identical semantics (a parity test keeps them in lockstep).

**Predicate and loader are one selection.** v1's `_select_cached_snapshot` is the
single source for both `is_model_cached` and `_resolve_snapshot_path`, and
`load_model` loads THAT snapshot path (not the repo id) with
`local_files_only=True` — so "cached" always means "loadable offline" and a
config-only residue can never be reported as a false cached success. refs/main
names the active revision; with none, the first weights-bearing snapshot wins.

### Acquisition failure surface (issue #210)

**File:** `src/indexed/core/model_acquisition.py`

Acquisition (download/load) is bounded and categorized so an impossible
acquisition fails predictably instead of leaking dependency retry chatter:

- `acquire_with_retry` retries only transient failures (network / HTTP 429) up
  to `MAX_ATTEMPTS = 3` with exponential backoff; permanent failures (missing
  repo, 401/403/gated) raise immediately. Every retry logs at DEBUG, so
  `--debug` keeps the timeline while the default surface shows one line.
- The final failure is wrapped in `ModelAcquisitionError` (an `IndexedError`) —
  model name, cache dir + state, failure category, and a category-specific
  remedy (`indexed init --model …` / `--force` / network / auth). Token-shaped
  secrets are redacted from any cause text.
- `huggingface_hub`'s per-retry WARNINGs are floored at ERROR in
  `utils/logger.py`; `--debug` lowers them back to DEBUG. transformers' "does
  not appear to have a file named pytorch_model.bin or model.safetensors" fires
  for ANY swallowed lookup (offline, unreachable hub, gated, or genuinely
  absent) and must never surface raw.
- `ensure_model` verifies the download left weights; a "successful" weightless
  call raises rather than reporting a cached success. `--force` create no longer
  clears the existing collection up front — the build-aside/rename-swap keeps a
  failed acquisition from clobbering a healthy index.

### Collection replace + interrupted-swap recovery (#126)

**Files:** `src/indexed/core/v2/persist.py` (`replace_dir`),
`src/indexed/core/v2/ingestion.py` (create/update call sites),
`src/indexed/core/recovery.py`, `src/indexed/core/engine.py` (`_recover` gates).

A collection is never mutated in place: the new generation is built beside the
live directory and swapped in with two renames — `rename(dest -> dest.trash-<pid>)`
then `rename(<name>.tmp-<pid>-<hex> -> dest)` — after which the trash is removed.
A failure of the second rename renames the original back and re-raises.

The remaining window is a CRASH between those two renames: the canonical path is
missing while both generations sit in directories discovery excludes
(`\.(?:tmp|trash)-\d+`). `core.recovery.recover_stranded` therefore runs inside
every list/open gate (`_existing_collection_names`, `_resolve_existing_engine`,
`_group_names_by_engine`, `discover_v2_collections`) and:

- restores the newest COMPLETE generation (readable `version: "2"` manifest plus
  all three `storage/*.json` files) to the canonical name when a `.trash-`
  sibling proves the swap was in flight;
- never promotes a `.tmp-`-only strand (an interrupted new build was never
  published) and never mixes two generations;
- quarantines anything it cannot prove restorable into `<collections>/.recovery/<name>/`
  — moved, never deleted — with a `recovery.log`, and writes the durable
  `quarantine.json` marker ONLY for a name whose data it actually moved there: a
  hold on a live writer, or an incomplete canonical left in place, gets no marker
  (an empty `.recovery/<name>/` must not claim preserved data) and its
  `CollectionRecoveryError` names the canonical directory instead;
- removes a `.trash-` sibling only when the canonical directory is already
  complete (finishing the interrupted cleanup);
- touches a strand ONLY when its writer is proven finished, because the pid in
  the name is the only ownership record: a strand carrying the CURRENT process's
  pid is an in-flight write of ours (a long-lived MCP server runs searches while
  it creates/updates) and is never swept; a pid that is alive is left alone and,
  when the collection has no readable directory, the hold is RECORDED so it does
  not read as "no such collection" (a recycled pid never finishes); on non-POSIX
  platforms liveness is unknowable (`os.kill` is `TerminateProcess` on Windows,
  so probing would kill the recorded process) and nothing is swept;
- raises `CollectionRecoveryError` for an EXPLICITLY requested collection that
  could not be restored, and keeps the explanation ALIVE across reads: the
  quarantining pass is one-shot, so the reason is also read back from the
  `quarantine.json` marker on every read path — an unfiltered search returns a
  per-collection `{"error": …}` entry (never a bare "No results found") and a
  sweep logs it — until the collection is readable at its canonical name again.

**Contract:** recoverable after a process crash between the renames. NOT
power-loss safe — there is no `fsync` in the rename chain, so unflushed pages
after a power cut are outside this guarantee.

### Batching

`embed_batch` defaults to `DEFAULT_EMBEDDING_BATCH_SIZE = 128` (configurable per call).

### Chunk-size invariant

Every chunk must tokenize to **≤ the embedder's `max_seq_length`** (256 for the
default `all-MiniLM-L6-v2`), read live from the embedder — never a hardcoded 512.
Oversized text is split down to the token window (see [tech-parsing.md](tech-parsing.md))
so no content is silently truncated at embed time.

---

## FAISS Indexing

### Index types

| Type | Use Case | Memory | Speed |
|------|----------|--------|-------|
| **IndexFlatL2** | <50K docs (default) | high | fast |
| IndexIVFFlat | 50K–1M docs | low | medium |
| IndexHNSW | >1M docs | medium | fast |

**Current:** only `IndexFlatL2` (exact similarity).

### Creation

**File:** `src/indexed/core/v1/engine/indexes/indexers/faiss_indexer.py`

```python
import faiss, numpy as np
index = faiss.IndexFlatL2(384)                       # 384 = all-MiniLM-L6-v2
index.add(np.array(embedding_list).astype('float32'))
distances, indices = index.search(query_vec, k=10)
```

### Similarity scoring

Embeddings are unit-normalized, so `IndexFlatL2` returns **squared** L2 distance
in **[0, 4]** — used directly as the result `score`, **lower means more similar**
(monotonic with cosine; not normalized to 0–1). Threshold filtering
(`min_score` / `score_threshold`) keeps chunks whose score is **≤** the threshold;
the configurable range is **[0, 4]** (a sane cutoff is >1.0), not [0, 1].

---

## Search-Time Git Awareness (v2, issues #60/#144/#146)

Two opt-in options on `core.v2.retrieval.search` — query-time only: no new persisted
state, no re-index, and the v1 engine ignores both (its behaviour is unchanged).

| Option | Effect |
|--------|--------|
| `changed_since: str` | Keep only result documents whose file changed since that git ref, **including uncommitted and untracked work**. Applied to retrieved NODES, before document grouping, so `max_docs` fills with survivors instead of being starved. |
| `git_provenance: bool` | Attach a document-level `git` field — `{commit, short, author, email, committedAt, subject}` (camelCase, additive: absent when not requested). |

Both are no-ops unless the collection's manifest reader is a files reader
(`localFiles`/`files` **and** a `basePath`); the repo is resolved ONCE per collection
via `utils/git_meta.repo_toplevel` (see [tech-connectors](tech-connectors.md) § Query-Time
Git Helper), node `source_id`s are rebased from base-path-relative to repo-relative, and
a git failure (not a repo, invalid ref, no history) skips the filter — never an empty
result set and never a raised search. Provenance costs at most one
`git log -1` per admitted document, memoized per `(repo, path)` within the call.

**A skipped filter is never silent.** Every collection result carries a `gitFilter`
status when — and only when — `changed_since` was requested:
`{"ref": <ref>, "applied": true}` after a run, and
`{"ref": <ref>, "applied": false, "reason": <why>}` when it could not run
(`unknown-ref`, `no-git-repository`, `not-a-files-collection`, or `v1-engine` — stamped
by the `core.engine` facade, whose routing is the only place that knows a collection
went to v1). The skip is logged at WARNING, `mcp/formatting.py` turns it into a
`collection_errors` entry naming collection and ref, and the CLI renderers print the
same line via `utils/git_meta.filter_skip_message` — unfiltered rows arriving under a
"changed only" request are a defect, not a quiet degrade.

**Provenance never outlives its snapshot.** `git_provenance` is attached only when the
node's indexed `modified_time` still describes the file at query time
(`utils/git_meta.snapshot_is_current` — a stat comparison, no extra subprocess). If the
file changed or was committed after the collection was indexed, the `git` field is
omitted rather than crediting a commit that does not contain the returned text;
re-indexing restores it (#279 review, finding 2).

The node timestamp is stored **offset-aware in UTC**
(`datetime.fromtimestamp(mtime, timezone.utc).isoformat()`), so the comparison is
absolute and independent of the querying process's zone or a DST change. An
offset-less value is LEGACY (the old writers stored naive local wall time, whose zone
is unknowable): the guard does not parse it into an instant and instead compares
the file's mtime with the manifest's UTC `updatedTime` — a file not newer than the
index cannot have changed since — which degrades towards *provenance present*
rather than dark. A
node with no timestamp takes the same legacy path; a vanished file always omits the
field. The mtime equality is a heuristic, not a content hash (#279 B1).

Surfaced as `--changed-since` / `--git-provenance` on `indexed index search` and as
`changed_since` / `git_provenance` on the MCP search tools, whose payload then carries
the same document-level `git` block. An omitted `git_provenance` means
the configured `core.v1.search.git_provenance` on BOTH surfaces (the CLI/MCP parity
invariant of `[core.v1.search]`). The CLI detail card gains a `Last commit` row.

The CLI validates `--changed-since` up front: an unresolvable ref always exits 1, and so
does naming (`--collection`) a collection that cannot carry the filter — no files reader,
no git repo behind it, or the v1 engine. When searching EVERY collection, an unfilterable
one is not fatal (a single Jira collection must not veto the search): it is announced per
collection, exactly like the MCP `collection_errors` entry.

---

## Index Freshness (files collections, #146 slice 1)

Reporting only: how far behind the source working tree a collection's index is. No
hooks, no auto-update, no new persisted state — the baseline already exists.

**Baseline ownership.** The files connector's `state.json` (written by
`ChangeTracker.build_state` in the connector's `post_run`, after a *successful* create or
update) is the one baseline: `last_indexed_commit` + `file_hashes` +
`indexed_file_count`, in the collection directory, v1 and v2 alike. Freshness reads it and
never writes it (`utils/freshness.py::read_baseline`). `utils/freshness.py` holds the
whole verdict; `utils/git_meta.py` supplies every git fact (timeout-bounded, `GIT_*`-scrubbed,
stdlib-only).

**Verdicts and reason codes.** `fresh` / `stale` / `unknown`, one per collection, carrying
a single `summary` line that every surface reuses verbatim (never re-worded downstream).

| Status | Meaning | `reason` |
|--------|---------|----------|
| `fresh` | every source file's current bytes hash to what was indexed | — |
| `stale` | ≥1 source file's bytes differ, or it is gone, or it was never indexed | `source-changed` |
| `unknown` | the question cannot be answered honestly | one of the codes below |

`unknown` reason codes: `not-a-files-collection`, `no-base-path`, `no-git-repository`
(non-git source), `no-head` (unborn HEAD), `no-baseline` (state.json missing/pre-dates
change tracking), `history-missing` (baseline commit absent — shallow/pruned),
`history-rewritten` (baseline exists but is not an ancestor of HEAD), `git-unavailable`.
A degraded answer is NEVER a fabricated `fresh` — the same contract `gitFilter` holds.

**Byte comparison, not just `git status`.** Git can only say "differs from HEAD"; a tree
indexed while dirty is legitimately current. For every changed path inside the source
directory the current bytes are xxhash-compared against `file_hashes` — without stored
hashes the code stays conservative and counts every changed path. Committed changes are
diffed against the baseline commit (ancestry checked first), and `commits_behind` is a real
`rev-list --count`, `None` when git cannot count.

**Conservative on purpose.** The reader's `includePatterns`/`excludedDirs` are NOT
re-applied when counting pending paths: a change to a file the collection never indexed
still reads `stale`. That errs toward a spurious warning, never toward a false `fresh`.

**Surfaces.** `index inspect <name>` gains a `Freshness` row (and a `freshness` object in
`--simple-output`); `indexed index search --freshness` prints one advisory line per
collection (dim when fresh, a warning otherwise); the MCP search tools take
`include_freshness` and the envelope gains a `freshness` list; the MCP collection-status
resources include the verdict. Freshness is attached by the `core.engine` facade, not by
either engine's inspect/status, so v1's engine behaviour is untouched and both engines
report identically. The facade is the only place that resolves manifest reader →
`basePath`, so CLI/MCP cannot drift from it.

**Out of scope (deferred).** `post-commit`/`post-checkout` hooks and an `install-hooks`
command (consolidates with the #67 hook proposals); exact behind-commit counts when
history is missing.

---

## Persistence Strategy

`DiskPersister` atomic writes: write temp file → `fsync()` → rename (atomic on POSIX).
Prevents corruption from process/system crashes and disk-full errors.

**Durability invariants:**
- The FAISS index is persisted on **every** mutating path — create, add,
  remove-then-add, deletions-only, and explicit-deletions — so on-disk vectors
  never outlive their mapping keys (no orphaned ids / `KeyError` on later search).
- A failed `create` **builds aside and rename-swaps** into place, so an error
  mid-run never destroys the prior collection of the same name.
- A zero-chunk batch (e.g. an empty-body document) is a **no-op**, not a crash.

On-disk layout (dirs owned by `src/indexed/config/`): [tech-config.md](tech-config.md) § Storage Directory Structure.

---

## Performance

### Search latency

**Target:** <1s for 10K–100K docs. **Actual:** ~800ms (10K), ~1.5s (100K).

Optimizations: searcher caching (reuse loaded FAISS indexes), memory-mapped indexes,
batch query embedding.

### Memory

Idle ~80MB; indexing ~400MB; search ~250MB (embedding model + index).
