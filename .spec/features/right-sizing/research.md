---
type: feature-research
feature: right-sizing
sibling: product.md
parent: ../../tech.md
updated: 2026-07-06
---

# Feature: Right-Sizing — Research (2026-07-06 audit)

Condensed evidence base from the full-codebase architecture audit (main pass +
app-layer, packages-layer, and adversarial overengineering reviews). Numbers
verified against the tree at branch `claude/architecture-audit-review-kkeihg`.

## Size inventory (verified)

| Area | LOC | Note |
|---|---|---|
| apps/indexed src | 9,764 | 45% of all source is the "thin UI layer" |
| indexed-connectors src | 5,548 | 4 sources |
| indexed-core src | 3,020 | the actual engine |
| indexed-config src | 1,584 | reads/writes TOML + .env |
| parsing / utils / protocols | 828 / 588 / 269 | |
| tests | 25,244 | 1.17× source; 1,410 test functions |
| `.agents/` vendored skills | 12,592 | larger than core+config+connectors combined |
| `config/cli.py` alone | 1,959 | larger than the whole config package it fronts |
| `create.py` | 992 | 4 near-identical ~230-line command clones |

## Rotten foundations (must not survive into v2's base)

1. **config.toml as mutable runtime state.** `ConfigService.set()` persists to
   disk (`store.py:322` writes TOML); `bootstrap.build_connector` and
   `connector_wiring._populate_*_config` call it during create/update, writing
   CLI args and **date-stamped derived queries** into the user's config.
2. **Untyped dict contracts.** Manifest (`manifest["reader"]["type"]`),
   documents/chunks (v1 dict format), search results (`Dict[str, Any]` with
   `"results"`/`"matchedChunks"` keys) — layer purity is enforced on imports
   while the actual data contract is stringly typed.
3. **Protocol fiction.** `protocols.DocumentReader` declares only
   `read_documents()`; zero callers exist — the engine calls
   `get_number_of_documents()` / `read_all_documents()` / `get_reader_details()`
   (`documents_collection_creator.py:202,225,500`). All consumption points are
   `Any`-typed, so mypy can't see it.
4. **Engine imports upward** from `core.v1.engine.services.models`
   (`documents_collection_creator.py:28`) — the cycle that forced the lazy
   import in `collection_service.py:111` and the `_types.py` leaf module.
5. **DI callable soup.** Four injected `Callable | None` params
   (`connector_factory`, `cache_decorator_factory`, `manifest_connector_factory`,
   `local_files_update_factory`) with runtime `missing_wiring_error` guards;
   the moved logic re-couples anyway: per-connector `if/elif` + camelCase
   manifest keys in app-layer `connector_wiring.py:124-145`, private reaches
   into `connector._config/._path/._include_patterns` (lines 227-231), and an
   `os.environ` side-channel for the Outline cutoff (line 164).
6. **Core still knows connectors**: `if connector_type == "localFiles"`
   (`update_collection_factory.py:87`, `search_service.py:244`).
7. **Broken failure paths.** `app.py:371` raises `typer.Exit` outside the click
   runner → traceback + exit 1, exit-code table dead (reproduced). MCP catches
   only `IndexedError` (`resources.py:57,75,96`, `tools.py:45`) but core raises
   none → envelope unreachable.
8. **Create deletes before building** (`documents_collection_creator.py:77`):
   failed re-create loses the existing collection despite the atomic-write persister.
9. **Config path logic triplicated** (`TomlStore.has_local_config` vs
   `storage.has_local_config` vs `StorageResolver`), singleton with conditional
   self-replacement (`service.py:72-79`), plus a second module-level singleton
   in `search_service.py:301`.
10. **Composition incoherence.** `register_app_config` runs in 3 places;
    `resolve_collections_context(reset=True)` discards those registrations;
    works only because connectors self-register in `from_config`.
    `update.py:360,374` omits `collections_path`, relying on singleton side-effects.

## Dead weight (delete list)

- `SearchArgs` DTO (`search_service.py:369`) — zero usages.
- `CONFIG_REGISTRY`, `get_config_class`, `list_connector_types`
  (`connectors/registry.py`) — zero production consumers; tests only.
- Indexer registry/factory naming scheme (`indexer_registry.py` 163 +
  `indexer_factory.py` 97) — exactly one indexer exists (`faiss_indexer.py`).
- Multi-indexer lists/loops + `manifest["indexers"][0]` asymmetry;
  `indexing_batch_size=500_000` batching that never batches.
- Sync `confluence_cloud_document_reader.py` (293 LOC) — never instantiated;
  async reader borrows its static helpers only.
- `_UpdatingCollectionCreator` wrapper class; `get_raw()` alias; tautological
  `test_core_shims.py`; 4× registry-membership `test_init.py` clones;
  protocol-conformance stub tests; ~3,770 LOC of Rich component markup tests;
  632 LOC testing `migration.py` (itself one-time legacy code still shipping).
- Two parallel progress systems (`ProgressCallback` + `PhasedProgressCallback`)
  coupled by magic phase-name strings across the core/CLI boundary.

## Worth keeping (the good bones)

- Atomic disk persistence (`disk_persister.py`: tmp → fsync → `os.replace`).
- Lazy ML imports (<1s startup discipline) and searcher caching
  (`SearchService._searcher_cache`).
- `_url_guard.py` off-origin credential guard; `change_tracker.py`
  (git/hash/mtime incremental indexing — a differentiating feature).
- The reader/converter split + `BaseConnector` idea (4 sources onboarded) —
  keep the protocol, fix its methods, drop the package around it.
- `retry.py` + `batch.py`; the MCP layer's proportions (~774 LOC total);
  system/e2e/benchmark tests; static `CONNECTOR_REGISTRY` (post-audit form).

## Performance notes

- `resolve_collections_context` eagerly imports all connectors (~0.4s measured)
  for commands that never use them; `register_app_config` adds schema imports
  in the app callback. Threatens the documented <1s startup.
- Pipeline writes every converted doc to disk, then re-reads all of them to
  embed (`__read_documents` → `__add_documents_to_index`) — double I/O + parse.
- `ConfigService.get/set` re-reads and re-parses TOML per call; update wiring
  performs up to 8 sequential read-parse-write cycles.
