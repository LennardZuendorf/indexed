---
type: feature-product
feature: workspace-profile
sibling: tech.md
parent: ../../product.md
updated: 2026-06-22
---

# Feature: Workspace Profile — Product

Replaces the dual local/global **storage** model with a single global store plus a
lightweight, committable **workspace profile** at `./.indexed/config.toml`. The
profile does two things only: it **filters** which global collections are active
in a codebase, and it **overrides** a subset of global settings for that codebase.
Storage location is no longer a user choice — all collections and caches live in
`~/.indexed/`.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | The `[workspace]` profile schema in `./.indexed/config.toml` (collection filter + setting overrides); collection-filter (allowlist) semantics across CLI search/inspect and MCP; removal of the local-vs-global storage mode. |
| **Does not own** | The indexing/search engine, connectors, parsing. The `indexed migrate` legacy-data mover (`./data/` → `~/.indexed/`) — orthogonal, stays as-is. Secret/`.env` resolution beyond dropping the local `.indexed/.env` root. |

---

## Requirements

### Requirement: Single global store

The system SHALL store all collections and caches under `~/.indexed/data/` and
MUST NOT expose any local-vs-global storage choice (no `--local`/`--global` flag,
no storage-mode preference, no local data directory).

#### Scenario: Create writes to the global store

- **Given** any working directory, with or without a `./.indexed/config.toml`
- **When** the user runs `indexed index create my-docs --source files --source-path ./docs`
- **Then** the collection is written under `~/.indexed/data/collections/my-docs/` and never under `./.indexed/`

#### Scenario: The local flag is gone

- **Given** the CLI
- **When** the user runs any command with `--local`
- **Then** the command fails with an unknown-option error (the flag no longer exists)

### Requirement: Collection filter

The workspace profile SHALL restrict which global collections are visible to
read operations (search, inspect/list, and MCP) to the set declared under
`[workspace.collections]`. When no profile is present, all global collections are
visible.

#### Scenario: Search is scoped to the profile

- **Given** global collections `docs`, `api`, and `notes`, and a profile declaring only `docs` and `api`
- **When** the user runs `indexed index search "query"` with no `--collection`
- **Then** only `docs` and `api` are searched; `notes` is not

#### Scenario: No profile means no filtering

- **Given** global collections `docs` and `api`, and no `./.indexed/config.toml`
- **When** the user runs `indexed index search "query"`
- **Then** both `docs` and `api` are searched

#### Scenario: MCP agent sees only the profile's collections

- **Given** a profile declaring only `docs`, launched from that workspace
- **When** an agent lists collections or searches via MCP
- **Then** only `docs` is listed and searchable; requesting `notes` by name returns an access error

### Requirement: Settings override

The workspace profile SHALL override a subset of global config settings for the
workspace via `[workspace.overrides]`, layered on top of the global
`~/.indexed/config.toml` and below `INDEXED__*` env vars and CLI args. Per-collection
overrides under `[workspace.collections.<id>.overrides]` SHALL apply only to that
collection.

#### Scenario: Workspace-wide override applies

- **Given** global `search.max_docs = 10` and a profile with `[workspace.overrides.search]` `max_docs = 3`
- **When** the user runs a search in that workspace
- **Then** the effective `max_docs` is `3`

#### Scenario: Env var still wins over the profile

- **Given** a profile setting `[workspace.overrides.search] max_docs = 3`
- **When** `INDEXED__core__v1__search__max_docs=7` is set in the environment
- **Then** the effective `max_docs` is `7`

### Requirement: Profile management from the CLI

The system SHALL let a user scaffold a workspace profile and inspect its effective
contents. Explicit named operations (`create`, `update`, `remove` with a name)
SHALL still reach any global collection, but SHALL warn when the named collection
is outside the workspace profile's collection set.

#### Scenario: Scaffold a profile

- **Given** a workspace with no `./.indexed/config.toml`
- **When** the user runs the profile-init command
- **Then** a `./.indexed/config.toml` with a `[workspace]` skeleton (commented examples) is created

#### Scenario: Warn on out-of-scope named operation

- **Given** a profile declaring only `docs`
- **When** the user runs `indexed index update notes`
- **Then** the command warns that `notes` is not in the workspace profile, and proceeds against the global store

---

## User Experience

The profile is a small TOML file the user is meant to commit (like `pyproject.toml`):

```toml
# ./.indexed/config.toml — workspace profile
[_meta]
schema_version = "2"

# Collection filter — only these global collections are active here.
[workspace.collections.backend-docs]
name = "Backend Docs"

[workspace.collections.api-spec]
name = "API Spec"
[workspace.collections.api-spec.overrides.search]   # per-collection override
max_docs = 5

# Settings override — global config changed for this workspace only.
[workspace.overrides.search]
include_matched_chunks = false
```

Commands no longer print a storage-mode banner. Search/inspect instead note when a
workspace filter is narrowing the active set (e.g. `Scoped to 2 workspace collections`).

---

## Non-Goals

- Storing collection **definitions** (source/path/filters) in the profile — `update`
  re-reads each collection's own `manifest.json`, so id + name is enough.
- Auto-namespacing collection ids to avoid cross-repo collisions — ids stay globally
  unique; the user picks distinct names.
- A migration shim from the old local store — v0.1.0 is alpha; this is a clean break.

---

## Open Questions

1. **Out-of-scope named ops: warn vs block?** — Recommendation: warn and proceed
   (above). Blocking would surprise users who legitimately maintain a global
   collection from inside an unrelated repo.
