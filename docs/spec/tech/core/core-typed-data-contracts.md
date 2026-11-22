---
type: tech
updated: 2026-11-22
applies: ["src/indexed/protocols/**", "src/indexed/core/**"]
---

# Typed Data Contracts

The three on-disk shapes the engine moves — the collection **manifest**, each
**converted document + chunk**, and each per-collection **search result** — are typed
Pydantic models in the `protocols` leaf (`protocols/models.py`: `Manifest`,
`ConvertedDocument`, `Chunk`, `CollectionSearchResult`). The engine reads and writes them
by model, never by `dict["stringKey"]`, so a field rename is a ty error rather than a
runtime `KeyError`. `model_dump(by_alias=True, exclude_none=True)` reproduces today's
camelCase JSON **byte-stable** — the on-disk v1 format is the compatibility boundary for
the v2 core swap. Full contract: [Protocols Package](../protocols-subpackage.md).
