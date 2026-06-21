# indexed-connectors — Source adapters

> Scope: this package. Workflow, rules, and verify gate live in the root
> [`AGENTS.md`](../../AGENTS.md). Canonical design: [`.spec/tech-connectors.md`](../../.spec/tech-connectors.md).

## What this is

Protocol-based data-source adapters. Each connector pairs a **Reader** (fetch raw
documents from a source) with a **Converter** (transform raw docs into searchable
chunks via the parsing module). Reader and converter stay separate.

## Layer & dependencies

Plugin layer. May import: protocols (from `core`), `indexed_config`, `utils`,
`parsing`. MUST NOT import: core engine, CLI, or MCP. The engine receives
connectors by injection; it never imports these.

## Where to find what

```
src/connectors/
  registry.py                          connector registration / lookup by type
  document_cache_reader_decorator.py   caching decorator over any DocumentReader
  files/        connector · reader · converter · schema · change_tracker · v1_adapter
  jira/         connector · (async) cloud reader · converter · schema
  confluence/   connector · (async) cloud reader · converter · schema
  outline/      connector · reader · converter · schema
```

Each connector implements `BaseConnector` (`reader` / `converter` /
`connector_type`); protocols live in `core/v1/connectors/base.py`.

## Architecture notes

- **Implemented:** FileSystem (no auth), Jira Cloud/Server, Confluence
  Cloud/Server (email + token), Outline (bearer token).
- **Change tracking** (Files, incremental indexing) via `ChangeTracker`:
  strategies `git` (diff between commits), `content-hash` (xxhash), `mtime`,
  and `auto` (git if `.git` present, else content-hash). State in `state.json`,
  updated after each successful run.
- **Parsing is delegated**, not reimplemented — converters call `indexed-parsing`
  ([`.spec/tech-parsing.md`](../../.spec/tech-parsing.md)) for document/code chunking.
- **Mock at `read_documents`** in tests — stub the network boundary, not the engine.
- Credentials come through `ConfigService`/`.env`; never hardcode secrets.
