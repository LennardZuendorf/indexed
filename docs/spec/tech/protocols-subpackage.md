---
type: tech
updated: 2026-11-22
applies: "src/indexed/protocols/**"
---

# Protocols Subpackage (`indexed.protocols`)

Shared connector contracts, **typed data models**, and cross-layer DTOs live in the
**leaf** subpackage `src/indexed/protocols/` (import `indexed.protocols`) — the only
import-legal home, since `core`/`connectors`/`config` may not import one another but all
may import `protocols`. Engine-only DTOs stay in core.

- **Typed data contracts** (`protocols/models.py`): `Manifest`, `ConvertedDocument`,
  `Chunk`, `CollectionSearchResult` (+ `DocumentMatch`/`MatchedChunk`) and `SourceConfig`.
  They round-trip today's on-disk **camelCase JSON byte-stable** (fields declared in
  on-disk key order, dumped `by_alias=True`, `exclude_none=True`) — the on-disk v1 format
  is the **compatibility boundary**, so a v2 engine reads the same collections. The engine
  reads/writes these models, never `dict["stringKey"]`; a field mismatch is a ty error,
  not a runtime `KeyError`.
- **Corrected connector protocols** (`protocols/connectors.py`): `DocumentReader` declares
  exactly what the engine calls — `get_number_of_documents` / `read_all_documents` /
  `get_reader_details`; `DocumentConverter` declares `convert`. A connector missing one is
  a ty error, not a runtime `AttributeError`. `BaseConnector` also declares
  `from_manifest(manifest, config, *, storage_path) -> ConnectorRun` — each connector owns
  its manifest keys and incremental cutoff, so **core's update path has no per-source /
  `localFiles` branches**.
- `SourceConfig`, `ProgressUpdate`, `ProgressCallback`, `PhasedProgressCallback` (the
  progress callbacks are today's dual system; Feature 14 collapses them to one `Progress`
  protocol).

`core` and `connectors` both depend on `protocols`; neither imports the other's
concrete types for wiring.
