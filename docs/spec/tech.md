---
type: hub
updated: 2026-11-22
---

# Tech

High-level architecture summary: cross-cutting concerns plus one spec per `src/indexed/` subpackage. Product decisions (what/why) are in [product.md](product.md).

## Components

- [App](tech/app/README.md): `cli/`, `mcp/`, `lsp/`. CLI architecture, storage-mode, Rich UI, logging, MCP and LSP servers, search result contract.
- [Core](tech/core/README.md): `core/`. Engine, embedding, FAISS, persistence, git awareness, freshness, performance.
- [Config](tech/config/README.md): `config/`. Config resolution, `.env` hierarchy, storage layout, schema versioning.
- [Connectors](tech/connectors/README.md): `connectors/`. Connector protocol, implemented connectors, change tracking.
- [Parsing](tech/parsing/README.md): `parsing/`. ParsingModule, Docling, tree-sitter, token window.
- `utils/` (logging, retry, batching, provenance) is a thin shared foundation with no spec of its own. `protocols/` (typed contracts, the leaf) is covered by [Protocols subpackage](tech/protocols-subpackage.md) and the core and connectors specs.

## Architecture

- [Architecture overview](tech/architecture-overview.md)
- [Tech stack](tech/tech-stack.md)
- [Package structure](tech/package-structure.md)
- [Data flow](tech/data-flow.md): indexing and search pipelines.

## Rules

- [Architectural rules](tech/architectural-rules.md): hard constraints across all code; the notes below refine it.
- [Dependency direction](tech/dependency-direction.md) and [Import-graph CI](tech/import-graph-ci.md).
- [Core facade and composition root](tech/core-facade-composition-root.md)
- [Error handling](tech/error-handling.md) and [HTTP retry policy](tech/http-retry-policy.md).
- [All tech notes](tech/README.md): structural rules, file size limits, config registration, protocols.

## Testing, CI and release

- [Testing strategy](tech/testing-strategy.md) and [System tests in CI](tech/system-tests-ci.md).
- [CI benchmarking](tech/ci-benchmarking/README.md): the same-job A/B gate and refresh lane.
- [Retrieval evaluation gate](tech/retrieval-eval-gate/README.md)
- [Size-gate CI](tech/size-gate-ci.md) and [Spec-root CI](tech/spec-root-ci.md).
- [Wheel build](tech/wheel-build.md) and [Release](tech/release/README.md).

## Open

- [Open technical questions](questions/open-technical-questions.md)
- [Spec ledger merging](tech/spec-ledger-merging.md)
