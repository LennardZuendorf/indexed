---
type: feature-tech
feature: right-sizing
sibling: product.md
parent: ../../tech.md
updated: 2026-07-06
---

# Feature: Right-Sizing — Architecture

Collapse the 7-package workspace into one package with four enforced module
edges, replace stringly dict contracts with typed models, make config
read-mostly, and delete phantom generality — so the v2 core rewrite later
swaps a module behind a stable facade instead of untangling a workspace.
Evidence for every decision: [research.md](research.md).

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

---

## Files (target layout)

```
pyproject.toml                    # the only one; hatchling, no una       ~80
src/indexed/
  models.py                       # Manifest, ConvertedDocument, Chunk,
                                  # SearchResult, SourceConfig, progress   ~200
  protocols.py                    # DocumentReader/Converter/Connector
                                  # (methods the engine actually calls)    ~80
  config/                         # collapsed from indexed-config          ~450
    __init__.py                   # get_config(), set_value(), resolve_mode()
    storage.py                    # dirs, .gitignore guard, .env routing
  core/                           # collapsed from indexed-core (v1 engine)
    __init__.py                   # THE FACADE: create/update/search/
                                  # inspect/remove + models re-export      ~60
    creator.py searcher.py embedder.py faiss_indexer.py persister.py
    services.py                   # collection/search/inspect, no factories-of-factories
  connectors/                     # collapsed from indexed-connectors
    registry.py                   # CONNECTOR_REGISTRY + NAMESPACE_REGISTRY only
    base helpers: _url_guard.py change_tracker.py v1_adapter.py
    files/ jira/ confluence/ outline/   # one reader per source
  parsing/                        # unchanged content
  utils.py                        # retry + batching (+ slimmed logging)
  cli/                            # Typer app; commands ≤300 lines each
    composition.py                # the ONE wiring module (replaces
                                  # bootstrap.py + connector_wiring.py + runtime.py)
  mcp/                            # kept as-is (already right-sized)
scripts/check_imports.py          # 4 forbidden edges, ~50 LOC
tests/                            # behavior + system + benchmarks only
AGENTS.md                         # the only one, ≤100 lines
```

## Module rules (replaces the workspace + import-graph apparatus)

```
cli, mcp   → core facade, connectors.registry, config, models, protocols
core       → models, protocols, config, utils           (NEVER connectors/cli/mcp)
connectors → models, protocols, config, parsing, utils  (NEVER core/cli/mcp)
config     → models only
```

Enforced by `scripts/check_imports.py` in CI (AST walk, same idea as today's
checker, one package's worth of paths). These four edges ARE the core swap
seam — everything else about the workspace (una, per-package pyprojects,
protocols-as-a-package, `_types.py`, `missing_wiring_error`) existed to
approximate them and is deleted.

## Contract / API

### Typed models (`models.py`) — round-trip today's JSON unchanged

```python
class Manifest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    collection_name: str = Field(alias="collectionName")
    updated_time: datetime = Field(alias="updatedTime")
    last_modified_document_time: datetime = Field(alias="lastModifiedDocumentTime")
    number_of_documents: int = Field(alias="numberOfDocuments")
    number_of_chunks: int = Field(alias="numberOfChunks")
    reader: ReaderDetails                  # type + per-source fields (extra="allow")
    indexer: str                           # from indexers[0]; serialized back as [{name}]

class SearchResult(BaseModel):            # per collection
    results: list[DocumentMatch]
    error: str | None = None
```

`ConvertedDocument`/`Chunk` wrap the v1 dict format (generalizing
`v1_adapter.py`'s quarantine idea). Serialization keeps camelCase aliases so
existing collections are byte-compatible (R9).

### Protocols (`protocols.py`) — what the engine actually calls

```python
@runtime_checkable
class DocumentReader(Protocol):
    def get_number_of_documents(self) -> int: ...
    def read_all_documents(self) -> Iterator[Any]: ...
    def get_reader_details(self) -> dict: ...

class DocumentConverter(Protocol):
    def convert(self, doc: Any) -> Iterator[ConvertedDocument]: ...
```

`Creator.__init__` and the facade are annotated with these — a mismatch is now
a mypy error (R2). `BaseConnector` keeps `reader`/`converter`/`connector_type`
/`from_config`, and **gains `from_manifest(manifest, config) -> (reader,
converter, deletions, post_run)`** so each connector owns its own manifest
keys. This deletes `connector_wiring.py`'s per-connector `_populate_*` blocks,
the private-attribute reaches, the `os.environ` side-channel, and core's
`localFiles` branch: `update` just calls
`registry[manifest.reader.type].from_manifest(...)` for every source.

### Core facade (`core/__init__.py`) — the v2 swap point

```python
def create(configs: list[SourceConfig], *, connector_factory, paths: StoragePaths,
           use_cache=True, force=False, progress: Progress | None = None) -> None
def update(names: list[str], *, manifest_factory, paths, progress=None) -> None
def search(query: str, *, collections=None, paths, **filters) -> dict[str, SearchResult]
def inspect(name: str, *, paths) -> CollectionInfo
def remove(names: list[str], *, paths) -> None
```

Two injected callables total (create-time and update-time connector
construction), both **required** — no `| None` + runtime wiring errors.
`cli/composition.py` is the only module that binds connectors to core.
A v2 engine ships as a new implementation of this facade over the same disk
format; nothing above the facade changes (R9).

### Config (`config/`) — read-mostly, one source of truth

- `get_config()` → cached `(mode, paths, raw_dict)` for the process; explicit
  `reload()` for tests. Kills the conditional-self-replacement singleton and
  the second singleton in `search_service`.
- **Runtime overrides are an in-memory overlay** (`with_overrides(dict)`),
  never persisted. Only `set_value()` (backing `indexed config set`) writes
  TOML/.env (R3).
- One home for path/mode logic (today it's triplicated across
  `store`/`storage`/`resolver`). Registry/Provider/`bind()` deleted —
  connectors validate their own schema section in `from_config`.

### Failure behavior

- `app.py`: `sys.exit(exit_code_for(exc))` (R4).
- MCP boundary: `except Exception` → envelope; core raises `IndexedError`
  subclasses for expected failures (missing collection, corrupt manifest).
- Creator builds a re-create into `<name>.tmp-<pid>` and swaps via rename;
  a failed create no longer destroys the existing collection.

### Progress

One `Progress` protocol (today's phased variant), phase names as an enum in
`models.py` instead of magic strings in two layers. The legacy simple callback
is deleted; CLI and MCP both implement or ignore the one protocol.

## Implementation Detail

Mechanical collapse order matters: fix behavior first (small diffs on the old
tree), then collapse the workspace (one big mechanical rename commit — imports
`core.v1.engine.*` → `indexed.core.*` etc., no logic), then do the semantic
shrinks on the new tree so every later diff is reviewed in final coordinates.
Details per unit: [plan.md](plan.md).

<!-- merge -->
## Architectural rules (post-right-sizing)

- One package, four module edges (cli/mcp → core|connectors|config;
  core ↛ connectors; connectors ↛ core; config leaf), enforced by
  `scripts/check_imports.py`.
- Layer contracts are typed models in `indexed/models.py` (manifest, document,
  chunk, search result) with camelCase JSON aliases — the on-disk v1 format is
  the compatibility boundary for the core swap.
- `config.toml` is user-owned: runtime flows use in-memory overrides;
  only `indexed config set` persists.
- Core is consumed only through its facade (`indexed/core/__init__.py`);
  `cli/composition.py` is the single wiring point. A v2 engine replaces the
  facade implementation over the same disk format.
- Coverage gate applies to `core/`, `connectors/`, `config/`; UI chrome is
  exempt. No mechanism tests (registry membership, shims, protocol stubs).
<!-- /merge -->

## Risks

1. **Big-bang rename (unit 2).** Mitigation: zero-logic commit, `git mv` to
   preserve history, full suite + smoke `create/search/update` on a real
   collection before and after.
2. **Wheel regression** (una removal). Mitigation: keep `validate_wheel.py`
   trimmed; CI installs the wheel in a clean venv and runs `indexed --help` +
   `indexed-mcp --help`.
3. **Manifest model vs. in-the-wild collections.** Mitigation: `extra="allow"`
   + round-trip test against fixture manifests from all four sources.
4. **Deleting tests that secretly caught behavior.** Mitigation: delete by
   category with the suite green between categories; keep any test that fails
   a mutation smoke check.
