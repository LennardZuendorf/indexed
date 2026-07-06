---
type: feature-product
feature: right-sizing
sibling: tech.md
parent: ../../product.md
updated: 2026-07-06
---

# Feature: Right-Sizing — Product

Shrink the codebase to the size the product warrants — a local-first semantic
search CLI/MCP used mainly by its author — while fixing the rotten foundations
the 2026-07-06 architecture audit found and preserving the one strategic goal:
**core must stay easy to swap out for a v2 rewrite**. The audit evidence lives
in [research.md](research.md).

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | Repository layout (workspace → single package), data contracts between layers, config write semantics, CLI/MCP failure behavior, CLI surface size, test-suite composition, process/docs apparatus size. |
| **Does not own** | The v2 core engine rewrite itself (separate future feature — this feature only prepares its seam). New connectors or search features. The on-disk collection format (kept byte-compatible). |

---

## Requirements

### Requirement: R1 — Single package

The codebase SHALL build and install as **one** Python package (`indexed`,
wheel `indexed-sh`) with plain modules replacing the 7-package uv workspace.
`una`, per-package `pyproject.toml`s, and cross-package version sync machinery
MUST be removed.

#### Scenario: One build, same wheel

- **Given** a fresh clone
- **When** `uv sync` then `uv build` run
- **Then** exactly one `pyproject.toml` exists and one `indexed-sh` wheel is produced with the same console scripts (`indexed`, `indexed-mcp`) as before

### Requirement: R2 — Typed data contracts

The contracts between layers (collection manifest, converted document, chunk,
search result) SHALL be typed models, and the connector protocols SHALL declare
the methods callers actually invoke, so that a contract mismatch is a
type-check failure — this is the load-bearing prerequisite for a swappable core.

#### Scenario: Protocol matches reality

- **Given** the reader protocol
- **When** any shipped reader is checked against it (`isinstance` or mypy)
- **Then** it conforms, and the engine calls only protocol methods

#### Scenario: Manifest is a model

- **Given** a collection on disk
- **When** any code reads its manifest
- **Then** it goes through one typed model (round-trips the existing camelCase JSON unchanged), not `dict["stringKey"]` access

### Requirement: R3 — Config is read-mostly

Runtime operations (create, update, search) MUST NOT write to the user's
`config.toml`. Derived state (date-stamped incremental queries, CLI-arg
overrides, incremental cutoffs) SHALL flow in memory only. The sole write path
is the explicit `indexed config set` family.

#### Scenario: Update leaves config untouched

- **Given** a `config.toml` with a Jira source query
- **When** `indexed index update <collection>` runs
- **Then** `config.toml` is byte-identical afterwards (no dated query, no URL echo)

### Requirement: R4 — Honest failure behavior

The CLI SHALL exit with its documented exit codes (no traceback for handled
`IndexedError`s), and the MCP surface SHALL return its error envelope for
**any** exception raised while serving a tool/resource call.

#### Scenario: Mapped exit code

- **Given** a command that raises a handled configuration error
- **When** it runs in a terminal
- **Then** the process exits with the mapped code (not 1-with-traceback)

#### Scenario: MCP never leaks raw exceptions

- **Given** a corrupt collection on disk
- **When** an MCP client calls `search`
- **Then** the response is the structured error envelope, not a protocol-level exception

### Requirement: R5 — No phantom generality

Machinery that serves no second implementation SHALL be deleted: the indexer
registry/factory naming scheme (one indexer exists), multi-indexer plumbing,
the never-batching 500k batch mechanism, dead DTOs and registry APIs, and
re-export shims (inventory in [research.md](research.md) § Dead weight).

#### Scenario: Dead API is gone

- **Given** the refactored tree
- **When** grepping for the audited dead symbols
- **Then** neither the symbols nor tests asserting their existence remain

### Requirement: R6 — Right-sized CLI

The CLI surface SHALL shrink to what one user needs: **one** generic `create`
command driven by connector schemas (replacing four ~230-line clones), a config
CLI reduced to `get` / `set` / `list` / `validate`, the legacy-layout
`migration.py` deleted, and the bespoke Rich component library reduced to the
pieces actually rendered. No command module may exceed 300 lines.

#### Scenario: Create still works per source

- **Given** each of the four source types
- **When** `indexed index create <name> --source <type> ...` runs with its existing flags
- **Then** behavior matches today (prompting for missing required fields included)

### Requirement: R7 — Tests assert behavior

Tests that assert mechanism (registry key membership, shim re-exports, protocol
conformance of stubs, Rich component markup) SHALL be deleted; behavior,
system/e2e, and benchmark tests stay. The coverage gate SHALL apply to
`core/` + `connectors/` + `config/` only, not UI chrome.

#### Scenario: Suite survives a rename

- **Given** an internal symbol rename with unchanged behavior
- **When** the suite runs
- **Then** only tests encoding real behavior can fail

### Requirement: R8 — Right-sized process

The agent/process apparatus SHALL fit the project: one root `AGENTS.md`
(≤100 lines), vendored `.agents/skills/` removed (installed via
`skills-lock.json` instead), per-package `AGENTS.md` files collapsed into the
root one, CI workflows trimmed to lint + typecheck + test + import-check.

#### Scenario: Docs cannot drift package-wise

- **Given** the single-package tree
- **When** looking for agent instructions
- **Then** exactly one `AGENTS.md` and the `.spec/` root docs exist

### Requirement: R9 — Core swap seam preserved

After collapse, the boundaries that make core replaceable SHALL survive as
module rules: the app (CLI/MCP) calls core **only** through its service facade;
connectors never import core; core never imports connectors or the app; the
on-disk collection format is unchanged so existing collections keep working.
A slim import check enforces these three edges in CI.

#### Scenario: v2 drop-in

- **Given** a hypothetical `core2` module implementing the same facade and disk format
- **When** the composition module points at it
- **Then** no CLI, MCP, connector, or config code changes

#### Scenario: Existing collections keep working

- **Given** a collection created before this feature
- **When** `search`, `inspect`, and `update` run against it
- **Then** they behave as before (no re-index required)

---

### Requirement: R10 — Data-path correctness

The 2026-07-06 deep hunt ([research.md](research.md) § Correctness bugs) found
the search data path silently discards most content and two reproduced
corruption paths. Before or alongside the structural work, the system SHALL:
chunk documents to the embedder's real token window (no silent truncation);
persist the FAISS index on every mutating operation including deletions-only;
never destroy the user's `config.toml` or leak secrets into it; and fail
loudly (documented error, non-zero exit) on missing/corrupt collections instead
of crashing or reporting success.

#### Scenario: Large document is fully searchable

- **Given** a 5,000-token document with no headings
- **When** it is indexed and a query matches text near its end
- **Then** that text is embedded in its own chunk and is findable (not truncated away)

#### Scenario: Delete-then-search stays consistent

- **Given** a collection, one document deleted via incremental update
- **When** any subsequent query runs
- **Then** the on-disk FAISS index and mapping agree — no `KeyError`, no whole-collection error

#### Scenario: Config edits are safe and private

- **Given** any `indexed config set` (including `... null` and a secret field)
- **When** it runs
- **Then** `config.toml` is never truncated/destroyed and secrets are routed to `.env`, not written or echoed in plaintext

#### Scenario: Missing collection fails cleanly

- **Given** a nonexistent or corrupt collection name
- **When** `search`/`update`/`inspect` target it
- **Then** the user sees a "not found"-class error and a non-zero exit — never a traceback or a success exit

## Non-Goals

- Rewriting the engine (v2 is its own future feature; this feature is the ground-clearing for it).
- Changing embedding model, FAISS index type, or search semantics.
- New sources, new commands, new MCP tools.
- Async-ifying or de-async-ifying readers beyond deleting dead duplicates.
