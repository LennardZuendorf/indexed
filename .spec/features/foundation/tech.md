---
type: feature-tech
feature: foundation
sibling: product.md
parent: ../../tech.md
updated: 2026-07-08
---

# Feature: Foundation — Architecture Overview

Make `indexed` **correct** and make its core **swappable** without moving a
single package. Foundation fixes every audited behavioral defect (search recall,
durability, secrets, connector fidelity, honest CLI/MCP) and lays four
cross-cutting contracts under them: a typed data-contract layer (`models.py` +
corrected `protocols.py`) that round-trips today's on-disk JSON byte-stable, a
narrow **core facade** that becomes the v2 swap seam, a single **composition**
module replacing the three-file wiring soup, and a **read-mostly config**
contract. All of it lands in the CURRENT 7-package layout — collapsing the
workspace to one package is deferred to Feature `simplify`, so every path in this
document is a real path on the tree as it stands today
(`packages/indexed-core/src/core/v1/…`, `apps/indexed/src/indexed/…`).

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

---

## Scope of this file

This is the **entry / overview** tech file. It defines the seven cross-cutting
contracts every unit shares and links out to the four detail files (see
[Detailed architecture files](#detailed-architecture-files)). Per-bug detail,
per-engine detail, per-connector detail, and per-config/CLI/MCP detail live in
those files — not here.

Deferred-to-`simplify` (explicitly NOT in foundation): deleting packages,
collapsing to `src/indexed/`, removing `una`, shrinking `create.py`/`config/cli.py`
chrome, deleting mechanism tests. Foundation only adds the contracts and fixes
the bugs so those deletions later land against tested, stable seams.

---

## 1. Typed data-contract layer — `models.py`

Requirement: [R1](product.md#requirement-typed-data-contracts). Today the layer
purity is enforced on *imports* while the actual data is stringly typed:
`manifest["reader"]["type"]`, v1 document/chunk dicts, and search results as
`Dict[str, Any]` with `"results"`/`"matchedChunks"` keys. A contract mismatch is
invisible to mypy because every consumption point is `Any`.

Foundation adds these Pydantic models to the **`protocols` leaf package**
(`packages/indexed-protocols/src/protocols/models.py`, where `SourceConfig`
already lives). They MUST live in the leaf, not in `core.v1`, because the
corrected `protocols/connectors.py` references `ConvertedDocument`/`Manifest`
and connectors return `ConvertedDocument` — and per §5's edge list
`connectors`/`config`/`protocols` may not import `core`. Placing the models in
`core.v1` would make those edges illegal and the import-graph check would fail.
(The earlier draft placed them at `core/v1/models.py`; that was inconsistent
with §5 and is corrected here — foundation/7, 2026-07-08.) In `simplify` they
move with the rest of the leaf into the single package. The models are the
compatibility boundary: they must serialize to **byte-identical** JSON so
existing collections on disk keep loading.

### Manifest round-trip (the load-bearing contract)

The on-disk manifest is written by
`documents_collection_creator.py:494-504` `__create_manifest_content`. The exact
current keys (camelCase, `.isoformat()` timestamps) are:

```json
{
  "collectionName": "...",
  "updatedTime": "2026-07-06T...",
  "lastModifiedDocumentTime": "2026-07-06T...",
  "numberOfDocuments": 12,
  "numberOfChunks": 480,
  "reader": { "type": "localFiles", "...source-specific...": "..." },
  "indexers": [ { "name": "faiss-flat-l2" } ]
}
```

The model reproduces those keys via aliases + `populate_by_name`, so it accepts
snake_case in Python and emits camelCase to disk:

```python
# packages/indexed-protocols/src/protocols/models.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class ReaderDetails(BaseModel):
    # get_reader_details() returns a per-source dict keyed by "type" + source fields
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    type: str

class Manifest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    collection_name: str = Field(alias="collectionName")
    updated_time: datetime = Field(alias="updatedTime")
    last_modified_document_time: datetime = Field(alias="lastModifiedDocumentTime")
    number_of_documents: int = Field(alias="numberOfDocuments")
    number_of_chunks: int = Field(alias="numberOfChunks")
    reader: ReaderDetails
    indexer_name: str = Field(alias="indexer")   # see note below

    @classmethod
    def from_disk(cls, raw: dict) -> "Manifest":
        # collapse the single-element indexers[] list on read
        r = {**raw, "indexer": raw["indexers"][0]["name"]}
        return cls.model_validate(r)

    def to_disk(self) -> dict:
        d = self.model_dump(by_alias=True, mode="json")
        d["indexers"] = [{"name": d.pop("indexer")}]   # re-expand on write
        return d
```

Serialization rules that keep bytes stable:
- `mode="json"` + `datetime` → `.isoformat()` (matches
  `documents_collection_creator.py:488-489`).
- `by_alias=True` for every dump; `extra="allow"` on `ReaderDetails` so
  in-the-wild source fields (URLs, queries, patterns) survive untouched.
- The `indexers: [{name}]` single-element list is an artifact of the deleted
  multi-indexer plumbing; `from_disk`/`to_disk` bridge it so foundation carries
  today's format forward verbatim. The `existing_manifest` merge path
  (`:485-492`, update flow) is reproduced by loading → mutating four fields →
  `to_disk`.

### Other models in the module

| Model | Wraps | Source of truth today |
|---|---|---|
| `ConvertedDocument` | one converted doc (`{"id": ..., "chunks": [...]}`) | v1 dict written at `documents_collection_creator.py:228-230` |
| `Chunk` | one searchable chunk (text + metadata + score) | `matchedChunks` entries, `search_service.py:151-164` |
| `SearchResult` | per-collection result envelope | `Dict[str,Any]` w/ `"results"`, `search_service.py:146-164` |
| `DocumentMatch` | one doc inside a result (`matchedChunks: list[Chunk]`) | `result["results"][i]` |
| `SourceConfig` | create/update input | already a model in `protocols/models.py:7` — folded in here |
| `ProgressPhase` | enum of phase names (see §7) | magic strings in `metadata.py:51` docstring |

`ConvertedDocument`/`Chunk` generalize the quarantine idea currently in the
factories' `_types.py`. They wrap (not replace) the v1 dict on read so the
pipeline's disk format is unchanged; the typing surfaces at the service/facade
boundary where callers previously saw `Any`.

`SearchResult` carries an explicit failure channel so per-collection errors stop
being silently swallowed (see §6):

```python
class SearchResult(BaseModel):
    results: list[DocumentMatch] = []
    error: str | None = None      # non-None ⇒ this collection failed; surface it
```

Round-trip is the acceptance test (unit foundation/7): load a fixture manifest
from each of the four sources, `Manifest.from_disk(...).to_disk()`, assert the
dict is `==` the original and the re-serialized JSON bytes match.

---

## 2. Corrected connector protocols — `protocols.py`

Requirement: [R1](product.md#requirement-typed-data-contracts). Today
`packages/indexed-protocols/src/protocols/connectors.py:15` declares
`DocumentReader.read_documents()` — a method **no caller invokes**. The engine
actually calls three different methods on the reader and one on the converter:

| Called method | Call site |
|---|---|
| `reader.get_number_of_documents()` | `documents_collection_creator.py:202` |
| `reader.read_all_documents()` | `documents_collection_creator.py:225` |
| `reader.get_reader_details()` | `documents_collection_creator.py:500` |
| `converter.convert(doc)` | `documents_collection_creator.py:226` |

The corrected protocol declares what is actually called, so a connector missing
`get_reader_details` becomes a **mypy error** instead of a runtime `AttributeError`:

```python
# corrected protocols.py (contrast: current read_documents() is fiction)
@runtime_checkable
class DocumentReader(Protocol):
    def get_number_of_documents(self) -> int: ...
    def read_all_documents(self) -> Iterator[Any]: ...
    def get_reader_details(self) -> dict: ...   # → Manifest.reader on disk

class DocumentConverter(Protocol):
    def convert(self, doc: Any) -> Iterator[ConvertedDocument]: ...
```

`BaseConnector` keeps `reader` / `converter` / `connector_type` /
`config_spec` / `from_config`, and **gains one classmethod**:

```python
class BaseConnector(Protocol):
    @classmethod
    def from_manifest(
        cls, manifest: Manifest, config: "AppConfig"
    ) -> tuple[DocumentReader, DocumentConverter, list[str], Callable[[], None] | None]:
        """Rebuild (reader, converter, explicit_deletions, post_run) for an update
        from this collection's own manifest. Each connector owns its manifest keys."""
        ...
```

`from_manifest` is what lets **core drop its connector knowledge**. Today
`update_collection_factory.py:87` and `search_service.py:244` branch on
`if connector_type == "localFiles"`, and `connector_wiring.py:124-145` reads
camelCase manifest keys, reaches into `connector._config/._path/._include_patterns`
(`:227-231`), and uses an `os.environ` side-channel for the Outline cutoff
(`:164`). With `from_manifest`, the update path becomes source-agnostic:

```python
reader, converter, deletions, post_run = registry[manifest.reader.type].from_manifest(manifest, config)
```

The `localFiles` special-case and the per-connector `_populate_*` blocks are
deleted; each connector owns its own manifest→reader logic behind the protocol.

Detail: [tech-connectors.md](tech-connectors.md),
[tech-core.md](tech-core.md).

---

## 3. Core facade — the v2 swap point

Requirement: [R2](product.md#requirement-core-swap-seam). The app (CLI/MCP) must
call core through exactly one surface, and core must never import connectors or
app. Today core is consumed through three factory modules
(`create_collection_factory.py`, `update_collection_factory.py`,
`search_collection_factory.py`) each taking **`Callable | None` params guarded by
`missing_wiring_error`** — four such params in total
(`create_collection_factory.py:27`, `update_collection_factory.py:37-38`, plus
`cache_decorator_factory`), each a runtime landmine.

Foundation introduces a facade at
`packages/indexed-core/src/core/v1/engine/__init__.py` (current coordinates;
becomes `indexed/core/__init__.py` in `simplify`):

```python
# the v2 swap seam — same signatures over the same on-disk format
def create(configs: list[SourceConfig], *, connector_factory: ConnectorFactory,
           paths: StoragePaths, use_cache: bool = True, force: bool = False,
           progress: Progress | None = None) -> None: ...

def update(names: list[str], *, manifest_factory: ManifestFactory,
           paths: StoragePaths, progress: Progress | None = None) -> None: ...

def search(query: str, *, collections: list[str] | None, paths: StoragePaths,
           **filters) -> dict[str, SearchResult]: ...

def inspect(name: str, *, paths: StoragePaths) -> CollectionInfo: ...

def remove(names: list[str], *, paths: StoragePaths) -> None: ...
```

Two injected callables total, **both REQUIRED** (positional-or-keyword, no
default, no `| None`): `connector_factory` (create-time construction) and
`manifest_factory` (update-time reconstruction via §2's `from_manifest`). A
missing wiring is now a `TypeError` at call construction / a mypy error — the
`missing_wiring_error()` runtime-guard pattern and `indexed_config.errors`'s
"must be injected by the app layer" string are **removed from these paths**. The
`cache_decorator_factory` collapses into `use_cache: bool` handled inside the
facade.

A v2 engine ships as a new module implementing these five signatures over the
same disk format (`manifest.json` / documents / chunks / `indexer.faiss`);
nothing above the facade changes. This is R2's drop-in property.

Detail: [tech-core.md](tech-core.md).

---

## 4. Composition module — one wiring home

Requirement: [R2](product.md#requirement-core-swap-seam). The app-layer wiring is
spread across three files today:

| File | LOC | Role today |
|---|---|---|
| `apps/indexed/src/indexed/bootstrap.py` | 67 | `register_app_config`, `build_connector_registry`, `build_connector` |
| `apps/indexed/src/indexed/connector_wiring.py` | 259 | per-connector `_populate_*`, manifest→reader, `os.environ` side-channel |
| `apps/indexed/src/indexed/runtime.py` | 39 | runtime context assembly |

The audit (research.md §10) found this incoherent: `register_app_config` runs in
three places, `resolve_collections_context(reset=True)` discards those
registrations, and it only works because connectors self-register in
`from_config`. `bootstrap.build_connector` writes CLI args into config during
create (research.md §1).

Foundation collapses these into **one `composition` module** (current
coordinates `apps/indexed/src/indexed/composition.py`; becomes
`cli/composition.py` in `simplify`). It is the **only** module that binds
connectors to core: it constructs the two required facade callables
(`connector_factory` and `manifest_factory`) from `CONNECTOR_REGISTRY` and hands
them to the facade. Because §2 gives connectors `from_manifest`, `composition`'s
`manifest_factory` is a one-liner dispatch — no per-connector branches, no
private-attribute reaches, no `os.environ`.

Detail: [tech-config-app.md](tech-config-app.md).

---

## 5. Module boundary rules — the four edges

Requirement: [R2](product.md#requirement-core-swap-seam). Foundation enforces the
same four edges the eventual single package will, but on the CURRENT package
paths (workspace collapse is Feature `simplify`):

```
cli, mcp   → core facade, connectors registry, config, models, protocols
core       → models, protocols, config, utils          (NEVER connectors/cli/mcp)
connectors → models, protocols, config, parsing, utils (NEVER core/cli/mcp)
config     → models only
```

Concretely on today's tree:
- `apps/indexed/src/indexed/**` may import `core.v1.engine` (facade),
  `connectors.registry`, `indexed_config`, `core.v1.models`, `protocols`.
- `packages/indexed-core/src/core/**` may import `protocols`, `indexed_config`,
  `utils`, its own `models` — **never** `connectors.*`, `indexed` (app), or
  `mcp`. This kills the current upward import
  (`documents_collection_creator.py:28` imports from
  `core.v1.engine.services.models`) and the `localFiles` branches.
- `packages/indexed-connectors/src/connectors/**` may import `protocols`,
  `indexed_config`, `indexed_parsing`, `utils` — **never** `core.*`.

**Enforcement:** the repo already ships an AST import-graph check; foundation
keeps using it (no new mechanism), just tightened to assert these four edges.
(The check is replaced by a slim `scripts/check_imports.py` in `simplify` when
paths collapse; foundation does not touch that.)

---

## 6. Read-mostly config + failure-behavior contracts

### Read-mostly config

Requirement: [R3](product.md#requirement-read-mostly-configuration). Today
`ConfigService.set()` persists to disk (`store.py:322`), and create/update wiring
calls it during runtime — baking CLI args and date-stamped derived queries into
the user's `config.toml` (research.md §1, bug #25). Foundation's contract:

- **Runtime flows (create/update/search) never write `config.toml`.** Overrides
  (CLI args, prompted values, `INDEXED__*` env) are an **in-memory overlay**
  applied on top of the loaded config for the duration of the process.
- **Only `indexed config set` persists**, and it writes **atomically**
  (tmp → fsync → `os.replace`, mirroring the collections persister) after
  rejecting unserializable values — fixing the truncate-to-0-bytes data loss
  (bug #8, `store.py:358`). Secrets route to `.env` (quoted), never TOML, never
  echoed (bugs #11, #31).
- **Single source of truth for path/mode.** Today path/mode logic is triplicated
  (`TomlStore.has_local_config` vs `storage.has_local_config` vs
  `StorageResolver`, research.md §9) with a conditional-self-replacement
  singleton plus a second singleton in `search_service.py:301`. Foundation
  consolidates to one cached `get_config()` (+ explicit `reload()` for tests).

Detail: [tech-config-app.md](tech-config-app.md).

### Failure behavior

Requirement: [R7](product.md#requirement-honest-cli-and-mcp-behavior). Two
surfaces, one rule each — **fail loud on missing/corrupt collections**:

- **CLI:** `app.py` maps exceptions to a **non-zero exit code**
  (`sys.exit(exit_code_for(exc))`). Today `app.py:371` raises `typer.Exit`
  outside the click runner → traceback + dead exit-code table (bug #7).
  `InspectService` must **omit** missing collections, not return a zero-filled
  placeholder (`inspect_service.py:204`), so `if not statuses` guards actually
  fire instead of crashing at `search.py:423`/`coll_status.indexers[0]`
  (bugs #19, #22).
- **MCP:** the boundary wraps **any** exception in a result envelope
  (`except Exception`, not just `IndexedError`). Core raises `IndexedError`
  subclasses for expected failures (missing collection, corrupt manifest) so the
  envelope path (`resources.py:57,75,96`, `tools.py:45`) is reachable; today
  core raises none, so the envelope is dead code (bug #7). Per-collection search
  failures surface via `SearchResult.error` (§1) instead of being `continue`d
  away (`mcp/formatting.py:27`, bug #18).

Detail: [tech-config-app.md](tech-config-app.md),
[tech-bugfixes.md](tech-bugfixes.md).

---

## 7. Progress — one protocol, enum phases

Requirement: [R7](product.md#requirement-honest-cli-and-mcp-behavior). Today two
parallel progress systems coexist, coupled by **magic phase-name strings** across
the core/CLI boundary: the simple `ProgressCallback`/`ProgressUpdate` dataclass
(`protocols/models.py:24-40`, driven at
`documents_collection_creator.py:207-242`) **and** the `PhasedProgressCallback`
Protocol (`protocols/models.py:43-70`, driven at `:198-248`). Phase names like
`"Scanning Files"`, `"Fetching Documents"` are string literals matched on both
sides; the `metadata.py` docstring lists a *different* set
(`"Loading model"`, `"Generating embeddings"`…) than the code emits.

Foundation keeps **one** `Progress` protocol (the phased variant) and replaces
the magic strings with a `ProgressPhase` enum in `models.py`:

```python
class ProgressPhase(str, Enum):
    PREPARING = "Preparing"
    SCANNING = "Scanning Files"
    FETCHING = "Fetching Documents"
    CHUNKING = "Parsing & Chunking"
    EMBEDDING = "Generating Embeddings"
    INDEXING = "Building FAISS Index"
    WRITING = "Writing To Disk"

class Progress(Protocol):
    def start_phase(self, phase: ProgressPhase, total: int | None = None) -> None: ...
    def advance(self, phase: ProgressPhase, amount: int = 1) -> None: ...
    def finish_phase(self, phase: ProgressPhase) -> None: ...
    def log(self, message: str) -> None: ...
```

The legacy `ProgressCallback`/`ProgressUpdate` and the dual driving code in
`documents_collection_creator.py` are collapsed to this one protocol; CLI
implements it with Rich, MCP and tests use a no-op. Enum members mean a typo'd
phase is a mypy/`AttributeError` at author time, not a silently-dropped update.

---

## Detailed architecture files

This overview links out; the buildable detail lives in four sibling files. They
are REQUIRED reading before implementing the matching units and are listed here
so none is orphaned:

- **[tech-bugfixes.md](tech-bugfixes.md)** — every audited correctness bug in
  full detail (file:line, repro, fix), covering units foundation/2–6 and the
  honest-behavior parts of foundation/6. Requirements R4, R5, R6, R7 (+ secret
  parts of R3).
- **[tech-core.md](tech-core.md)** — engine architecture: creator/searcher/
  embedder/faiss-indexer/persister, the facade internals, token-aware chunking,
  durability (persist-on-every-mutation, zero-chunk guard, build-aside-swap).
  Units foundation/2, /3, /7, /8. Requirements R1, R2, R4, R5.
- **[tech-connectors.md](tech-connectors.md)** — connector architecture:
  reader/converter split, corrected protocol, `from_manifest`, registry,
  attachment/redirect fidelity, change-tracker, ADF/storage-format extraction,
  `_url_guard`. Units foundation/5, /7, /8. Requirements R1, R2, R6.
- **[tech-config-app.md](tech-config-app.md)** — config + CLI + MCP
  architecture: read-mostly overlay, atomic write, single path/mode home,
  composition module, exit codes, MCP envelope + cache invalidation, Rich-markup
  safety, logger flags, dead config sections. Units foundation/6, /8, /9.
  Requirements R2, R3, R7.

---

<!-- merge -->
## Architectural rules (post-foundation)

Promote to root `.spec/tech.md` on COMPOUND. (These are the CONTRACT rules;
Feature `simplify` adds the single-package/edge-enforcement rules on top.)

- **Layer data is typed.** Manifest, converted document, chunk, and search
  result are Pydantic models in one `models.py` with camelCase JSON aliases. The
  on-disk v1 format (camelCase manifest, `indexers:[{name}]`, `.isoformat()`
  times) is the **compatibility boundary** — models round-trip it byte-stable, so
  a v2 engine reads the same collections.
- **Connectors declare what the engine calls.** `protocols.py` declares
  `get_number_of_documents`/`read_all_documents`/`get_reader_details`/`convert`;
  a mismatch is a mypy error. `BaseConnector.from_manifest(...)` means core has
  no per-source branches (no `localFiles` special-case).
- **Core is consumed only through its facade** (`create/update/search/inspect/
  remove`) with two REQUIRED injected callables — no `| None` + runtime wiring
  errors. One `composition` module is the single connector↔core binding point. A
  v2 engine replaces the facade implementation over the same disk format.
- **Four module edges:** cli/mcp → core|connectors|config; core ↛ connectors;
  connectors ↛ core; config → models only. Enforced by the import-graph check.
- **`config.toml` is user-owned.** Runtime flows use an in-memory override
  overlay; only `indexed config set` persists, atomically, secrets to `.env`.
- **Failure is loud.** CLI maps exceptions to non-zero exit codes; MCP wraps any
  exception in an envelope; missing/corrupt collections raise `IndexedError`, are
  omitted from status, and never return a fake-healthy zero-fill.
- **One `Progress` protocol** with `ProgressPhase` enum names — no magic-string
  two-callback system.
<!-- /merge -->

---

## Risks

1. **Manifest model vs. in-the-wild collections.** A model stricter than reality
   silently breaks existing collections. *Mitigation:* `extra="allow"` on
   `ReaderDetails`, `from_disk`/`to_disk` bridge the `indexers[]` artifact, and a
   round-trip test asserts byte-equality against fixture manifests from all four
   sources (foundation/7). Gate on the foundation/1 harness first.
2. **Facade refactor changes behavior under the harness.** Swapping factories +
   `missing_wiring_error` for a required-callable facade touches every entry
   point. *Mitigation:* foundation/8 depends on foundation/1 (behavior harness)
   and foundation/7 (typed contracts); the harness asserts create→search→update→
   inspect→remove behavior is unchanged before and after.
3. **`from_manifest` moves connector knowledge but must preserve today's manifest
   keys.** Each connector's `from_manifest` has to reproduce what
   `connector_wiring._populate_*` did (queries, cutoffs, patterns).
   *Mitigation:* characterization tests per source (foundation/1) capture the
   current update behavior including incremental queries before the move.
4. **Read-mostly config changes the persistence surface.** Removing runtime
   `config.set()` calls risks dropping an override a later run depended on.
   *Mitigation:* the in-memory overlay carries every override within the process;
   a config get/set round-trip test (foundation/1) plus atomic-write rejection of
   unserializable values (foundation/3) fence the persist path.
5. **Import-edge tightening flags pre-existing violations** (e.g. the engine's
   upward import at `documents_collection_creator.py:28`). *Mitigation:* fix the
   cycle as part of foundation/7's typed-models move (models become the shared
   leaf), then flip the check to failing.
