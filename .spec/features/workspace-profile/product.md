---
type: feature-product
feature: workspace-profile
sibling: tech.md
parent: ../../product.md
updated: 2026-08-12
---

# Feature: Workspace Profile — Product

Replaces the dual local/global **storage** model with a single global store plus a
lightweight, committable **workspace profile** at `./indexed.config.toml`. The profile
does two things only: it **filters** which global collections are active in a codebase,
and it **overrides** a subset of global settings for that codebase. Storage location is
no longer a user choice — all collections and caches live in `~/.indexed/`.

Because agents reach the same collections over MCP, this feature also owns **how an MCP
client tells the server which workspace it is working in**. Without that, a server
serving more than one repo has no way to know which profile applies.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | The `[workspace]` profile schema and its file discovery (canonical `indexed.config.toml` + legacy `./.indexed/config.toml`); collection-filter (allowlist) semantics across CLI search/inspect and MCP; the MCP workspace-resolution chain and the `scope` block on MCP responses; profile lifecycle from the CLI; removal of the local-vs-global storage mode; `schema_version = "2"` enforcement; the workspace's slot in the engine-selection chain. |
| **Does not own** | The indexing/search engine itself, connectors, parsing. **The v1/v2 engines and the version-dispatching facade (`core/engine.py`) — owned by Core v2 (PR #162); this feature only threads an allowlist through it and contributes one link to its selection chain.** The `indexed migrate` legacy-data mover (`./data/` → `~/.indexed/`) — orthogonal, stays as-is. MCP transport security (auth tokens, `Origin` validation, loopback binding) — pre-existing concerns, untouched here. |

> **Upstream gate.** This feature is sequenced **after** Core v2 (PR #162). #162 introduces
> the version-dispatching facade `core/engine.py` and repoints `cli/` and `mcp/` at it, so
> the collection allowlist must be threaded through that facade rather than through
> `core/v1/engine/services/*` — otherwise the workspace filter would apply to v1 collections
> only and silently miss every v2 collection. See [tech.md](tech.md) § Collection filter as
> an allowlist.

---

## Requirements

### Requirement: Single global store (R1)

The system SHALL store all collections and caches under `~/.indexed/data/` and MUST NOT
expose any local-vs-global storage choice (no `--local`/`--global` flag, no storage-mode
preference, no local data directory).

#### Scenario: Create writes to the global store

- **Given** any working directory, with or without a workspace profile
- **When** the user runs `indexed index create my-docs --source files --source-path ./docs`
- **Then** the collection is written under `~/.indexed/data/collections/my-docs/` and never under `./.indexed/`

#### Scenario: The local flag is gone

- **Given** the CLI
- **When** the user runs any command with `--local`
- **Then** the command fails with an unknown-option error (the flag no longer exists)

### Requirement: Workspace profile discovery (R2)

The system SHALL locate the workspace profile by walking upward from the workspace
directory, taking the first match of `indexed.config.toml` (canonical) then
`.indexed/config.toml` (legacy) in each directory, stopping at `$HOME` inclusive or the
filesystem root. The legacy form MUST NOT be resolved at `$HOME`, because
`~/.indexed/config.toml` is the global config. When both forms exist in one directory the
canonical form wins and the system warns once.

#### Scenario: Profile found from a subdirectory

- **Given** `~/code/app/indexed.config.toml` and a shell in `~/code/app/src/api/`
- **When** the user runs `indexed index search "query"`
- **Then** the profile at `~/code/app/indexed.config.toml` is applied

#### Scenario: Legacy location still works

- **Given** a workspace with `./.indexed/config.toml` and no `./indexed.config.toml`
- **When** any command resolves the profile
- **Then** the legacy profile is applied and a one-time deprecation notice names the canonical path

#### Scenario: The global config is never treated as a profile

- **Given** a global `~/.indexed/config.toml` and a workspace under `~` with no profile of its own
- **When** the upward search reaches `$HOME`
- **Then** `~/.indexed/config.toml` is not adopted as a profile and the workspace resolves as unfiltered

#### Scenario: Canonical wins over legacy

- **Given** a directory containing both `indexed.config.toml` and `.indexed/config.toml`
- **When** the profile is resolved
- **Then** the canonical file is used and a warning names the ignored legacy file

### Requirement: Collection filter (R3)

The workspace profile SHALL restrict which global collections are visible to read
operations (search, inspect/list, and MCP) to the set declared under
`[workspace.collections]`. When no profile is present, all global collections are visible.
A declared collection id with no matching collection in the global store SHALL warn and be
skipped, not fail the operation.

#### Scenario: Search is scoped to the profile

- **Given** global collections `docs`, `api`, and `notes`, and a profile declaring only `docs` and `api`
- **When** the user runs `indexed index search "query"` with no `--collection`
- **Then** only `docs` and `api` are searched; `notes` is not

#### Scenario: No profile means no filtering

- **Given** global collections `docs` and `api`, and no profile in scope
- **When** the user runs `indexed index search "query"`
- **Then** both `docs` and `api` are searched

#### Scenario: A stale entry warns rather than fails

- **Given** a profile declaring `docs` and `deleted-one`, where only `docs` exists globally
- **When** the user runs a search
- **Then** `docs` is searched and a warning names `deleted-one` as declared but missing

#### Scenario: An empty collection set hides everything

- **Given** a profile with a `[workspace]` section declaring no collections
- **When** the user runs a search
- **Then** no collections are searched and the output states the workspace scope is empty

### Requirement: Settings override (R4)

The workspace profile SHALL override a subset of global config settings for the workspace
via `[workspace.overrides]`, layered on top of the global `~/.indexed/config.toml` and
below `INDEXED__*` env vars and CLI args. Per-collection overrides under
`[workspace.collections.<id>.overrides]` SHALL apply only to that collection.

#### Scenario: Workspace-wide override applies

- **Given** global `search.max_docs = 10` and a profile with `[workspace.overrides.search]` `max_docs = 3`
- **When** the user runs a search in that workspace
- **Then** the effective `max_docs` is `3`

#### Scenario: Env var still wins over the profile

- **Given** a profile setting `[workspace.overrides.search] max_docs = 3`
- **When** `INDEXED__core__v1__search__max_docs=7` is set in the environment
- **Then** the effective `max_docs` is `7`

### Requirement: Per-workspace default engine (R8)

The workspace profile SHALL be able to set the default core engine for new collections
created in that workspace, via `[workspace.overrides.core] engine`. It slots into the
existing engine-selection chain introduced by Core v2 (PR #162) — `--engine` flag ›
`INDEXED__CORE__ENGINE` env › workspace profile › global `[core] engine` › built-in default
— so an explicit flag or env var still wins, and the profile still beats global config.
The engine of an **existing** collection is never changed by the profile: it is read from
that collection's own manifest.

#### Scenario: A workspace pins its default engine

- **Given** a global `[core] engine = "v1"` and a profile with `[workspace.overrides.core] engine = "v2"`
- **When** the user runs `indexed index create api --source files --source-path ./api` in that workspace
- **Then** the collection is created on the v2 engine

#### Scenario: An explicit flag still wins over the profile

- **Given** a profile with `[workspace.overrides.core] engine = "v2"`
- **When** the user runs `indexed index create api ... --engine v1`
- **Then** the collection is created on the v1 engine

#### Scenario: The profile never re-engines an existing collection

- **Given** an existing v1 collection `docs` and a profile setting `engine = "v2"`
- **When** the user searches or updates `docs`
- **Then** `docs` is served by the v1 engine, routed from its own manifest, and no migration is implied

### Requirement: Profile lifecycle from the CLI (R5)

The system SHALL let a user scaffold a workspace profile, and SHALL keep the profile in
step with collection lifecycle: `create` adds the new collection to the profile in scope,
`remove` drops its entry. Explicit named operations (`create`, `update`, `remove` with a
name) SHALL still reach any global collection, warning when the named collection is
outside the profile.

#### Scenario: Scaffold a profile

- **Given** a workspace with no profile
- **When** the user runs the profile-init command
- **Then** an `./indexed.config.toml` with a `[workspace]` skeleton (commented examples) is created

#### Scenario: Create registers the collection in the profile

- **Given** a workspace whose profile declares only `docs`
- **When** the user runs `indexed index create api --source files --source-path ./api`
- **Then** the collection is written globally, an `[workspace.collections.api]` entry is appended to the profile, and a subsequent unscoped search in that workspace finds `api`

#### Scenario: Opting out of the profile write

- **Given** a workspace with a profile
- **When** the user runs `indexed index create scratch ... --no-profile`
- **Then** the collection is created globally and the profile is left untouched

#### Scenario: Remove drops the profile entry

- **Given** a profile declaring `docs` and `api`
- **When** the user runs `indexed index remove api`
- **Then** the collection is removed from the global store and its `[workspace.collections.api]` entry is dropped from the profile

#### Scenario: Warn on out-of-scope named operation

- **Given** a profile declaring only `docs`
- **When** the user runs `indexed index update notes`
- **Then** the command warns that `notes` is not in the workspace profile, and proceeds against the global store

### Requirement: MCP workspace handover (R6)

The MCP server SHALL resolve the caller's workspace **per request** from the first
available of: an explicit `workspace` tool argument; an `Indexed-Workspace` HTTP header
(http transport); the client's MCP roots; the `INDEXED_WORKSPACE` then `CLAUDE_PROJECT_DIR`
environment variables; and — under stdio transport only — the server process working
directory. Every tool and resource response SHALL carry a `scope` block naming the
resolved workspace, the profile in force, the resolution source, the active collections,
and any warnings.

Resolution SHALL fail closed: an explicitly supplied workspace that does not resolve to an
existing directory, and a profile file that is found but cannot be parsed, MUST both raise
an error rather than fall back to an unfiltered global view.

#### Scenario: The agent names its workspace

- **Given** global collections `docs` and `notes`, and `~/code/app/indexed.config.toml` declaring only `docs`
- **When** an agent calls the search tool with `workspace = "~/code/app"`
- **Then** only `docs` is searched and the response `scope` block reports source `argument`

#### Scenario: Claude Code hands over the workspace without the model's help

- **Given** an `indexed` MCP server launched over stdio by a client that answers `roots/list` with `~/code/app`, and no `workspace` argument on the call
- **When** an agent calls the search tool
- **Then** the `~/code/app` profile is applied and the `scope` block reports source `roots`

#### Scenario: Ambiguous roots ask rather than guess

- **Given** a client whose roots are `~/code/app` and `~/code/lib`, both containing a profile
- **When** an agent calls a tool with no `workspace` argument and no header or env override
- **Then** the call fails with an error naming both candidates and asking for an explicit `workspace` argument

#### Scenario: A bad explicit workspace fails closed

- **Given** an agent calling the search tool with `workspace = "/no/such/dir"`
- **When** the server resolves the workspace
- **Then** the call returns an error and does **not** fall back to searching all global collections

#### Scenario: An unreadable profile fails closed

- **Given** a workspace whose `indexed.config.toml` contains invalid TOML
- **When** an agent calls any tool scoped to that workspace
- **Then** the call returns an error naming the file and the parse failure, and does **not** fall back to an unfiltered view

#### Scenario: Unscoped is stated, not implied

- **Given** a stdio server whose working directory has no profile anywhere up to `$HOME`
- **When** an agent calls the search tool
- **Then** all global collections are searched and the `scope` block reports source `none` with an empty profile path

#### Scenario: Out-of-scope named access warns in the payload

- **Given** a workspace profile declaring only `docs`
- **When** an agent calls the collection-search tool for `notes`
- **Then** the search proceeds against `notes` and the response `scope.warnings` states that `notes` is outside the workspace profile

### Requirement: Config schema version 2 (R7)

Config and profile files SHALL declare `[_meta] schema_version = "2"`. A file carrying
version `"1"` or no version SHALL be accepted when it contains no removed keys, and SHALL
be rejected with a migration message naming the offending keys when it contains
`[workspace].mode`, `[workspace].local_path`, or `[workspace].global_path`. An unrecognised
version SHALL be rejected.

#### Scenario: A pre-collapse config is rejected legibly

- **Given** a global `~/.indexed/config.toml` with `[_meta] schema_version = "1"` and `[workspace] mode = "local"`
- **When** any command loads config
- **Then** the command fails with an error naming `[workspace].mode` and stating that storage modes were removed

#### Scenario: A clean version-1 config still loads

- **Given** a global config with `schema_version = "1"` and no `[workspace]` section
- **When** any command loads config
- **Then** the config loads unchanged and is treated as version `"2"`

---

## User Experience

The profile is a small TOML file the user is meant to commit, sitting beside
`pyproject.toml` rather than inside a hidden directory:

```toml
# ./indexed.config.toml — workspace profile
[_meta]
schema_version = "2"

# Collection filter — only these global collections are active here.
# Each <id> MUST match a collection directory name under ~/.indexed/data/collections/.
[workspace.collections.backend-docs]
name = "Backend Docs"          # display label only

[workspace.collections.api-spec]
name = "API Spec"
[workspace.collections.api-spec.overrides.search]   # per-collection override
max_docs = 5

# Settings override — global config changed for this workspace only.
[workspace.overrides.search]
include_matched_chunks = false
```

With the local data root gone, this one committed file is the entire workspace footprint —
no `./.indexed/` directory, no local collections, no `.gitignore` guard. Project secrets
live in `./.env` as usual.

Commands no longer print a storage-mode banner. Search/inspect instead note when a
workspace filter is narrowing the active set (e.g. `Scoped to 2 workspace collections`).

**Handing the workspace to an agent.** The recommended setup gives the server the
workspace through client configuration, so the model never has to supply it:

```jsonc
// stdio — .mcp.json
{"mcpServers": {"indexed": {"command": "indexed-mcp", "args": ["run"],
  "env": {"INDEXED_WORKSPACE": "${workspaceFolder}"}}}}

// http
{"mcpServers": {"indexed": {"type": "http", "url": "http://127.0.0.1:8000/mcp",
  "headers": {"Indexed-Workspace": "${workspaceFolder}"}}}}
```

Clients that answer `roots/list` (Claude Code does, including every `--add-dir`) need
neither. The `workspace` tool argument is the escape hatch for one server serving several
repos.

---

## Non-Goals

- Storing collection **definitions** (source/path/filters) in the profile — `update`
  re-reads each collection's own `manifest.json`, so id + name is enough.
- Auto-namespacing collection ids to avoid cross-repo collisions — ids stay globally
  unique; the user picks distinct names.
- A migration shim from the old local store — v0.1.0 is alpha; this is a clean break,
  softened only by the version-2 error message.
- Making the profile a **security boundary**. It is a default-scope filter: named access
  warns and proceeds, matching MCP's own framing of roots as *"informational guidance
  rather than an access-control mechanism"*. Anything that needs enforcement belongs in
  transport auth, not here.
- Per-workspace **storage**. A workspace narrows and overrides; it never relocates data.

---

## Open Questions

None. The two questions carried by the previous revision are resolved: out-of-scope named
operations **warn and proceed** on both CLI and MCP (see Requirement: Profile lifecycle and
the MCP payload-warning scenario), and per-collection overrides are applied in the CLI/MCP
layer when building that collection's search config (see [tech.md](tech.md) § Merge
semantics).
