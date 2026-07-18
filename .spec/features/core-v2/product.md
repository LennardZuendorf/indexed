---
type: feature-product
feature: core-v2
sibling: tech.md
parent: ../../product.md
updated: 2026-07-18
---

# Feature: Core V2 (LlamaIndex engine) — Product

A second, coexisting core engine ("v2") built on LlamaIndex that expands indexed
beyond its fixed FAISS + sentence-transformers stack: configurable embedding
providers (local and API), pluggable vector stores, optional reranking, and a
foundation for richer retrieval — while every existing v1 collection keeps
working unchanged, and users control explicitly which engine serves which
collection.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)
**Research:** [research.md](research.md)

---

## Scope

| | |
|---|---|
| **Owns** | The v2 engine and its on-disk collection format; engine-version detection and routing for all CLI commands and MCP tools; the engine selector surface (flag, env, config); the `[core.v2.*]` config namespace; the v1→v2 migration command; v2 local-embedding configuration; optional reranking |
| **Does not own** | The v1 engine's behavior or on-disk format (frozen, byte-stable); connectors and parsing (consumed as-is via existing protocols); remote embedding providers and additional vector stores (Ollama, Qdrant, … — future work behind the seams this feature ships); knowledge graphs and hybrid/BM25 retrieval (future sibling features); flipping the built-in default engine to v2 (separate decision gate); server/multi-user deployment |

---

## Requirements

### Requirement: Engine-versioned collections (R1)

Every collection created by v2 SHALL carry a persistent engine-version marker.
A collection without a marker SHALL be treated as v1. An unrecognized marker
MUST fail loud with an actionable message — never silently fall back to v1.

#### Scenario: v2 collection is self-describing

- **Given** a collection created with the v2 engine
- **When** any command or MCP tool touches it
- **Then** it is served by the v2 engine without any flag or config

#### Scenario: legacy collection defaults to v1

- **Given** a collection created before this feature (no version marker)
- **When** it is searched, updated, inspected, or removed
- **Then** it is served by the v1 engine exactly as today

#### Scenario: unknown version fails loud

- **Given** a collection whose marker names an unsupported engine version
- **When** any operation touches it
- **Then** the operation fails with a message naming the found version and the
  supported versions, and the collection is not modified

### Requirement: Safe per-collection routing (R2)

Every CLI command, MCP tool, and internal call operating on an existing
collection MUST resolve the engine from the collection itself. An explicitly
requested engine that conflicts with the collection's engine MUST fail with an
actionable error; the system MUST NOT read or write a collection with the wrong
engine.

#### Scenario: explicit selector cannot override reality

- **Given** a v1 collection
- **When** the user runs search or update with the v2 engine explicitly selected
- **Then** the command fails, names both engines, and suggests the remedy
  (drop the selector, or migrate the collection)

#### Scenario: mixed collections search safely

- **Given** one v1 and one v2 collection
- **When** the user searches across all collections
- **Then** each collection is searched by its own engine and both contribute
  results

### Requirement: Explicit engine selection for new collections (R3)

Collection creation SHALL choose the engine by this precedence: CLI flag, then
environment variable, then config file, then the built-in default. The built-in
default SHALL remain v1 until the separate default-flip decision.

#### Scenario: flag wins over config

- **Given** config sets the default engine to v2
- **When** the user creates a collection with the v1 engine flag
- **Then** a v1 collection is created

#### Scenario: nothing configured

- **Given** no engine flag, env var, or config value
- **When** the user creates a collection
- **Then** a v1 collection is created, exactly as before this feature

### Requirement: Surface parity (R4)

All existing CLI commands, MCP tools, output formats, and agent-skill workflows
SHALL work identically for v2 collections. Result-shape differences are limited
to relevance semantics (R11) and additional diagnostic fields.

#### Scenario: same commands, both engines

- **Given** a v2 collection
- **When** the user runs the documented create/search/update/inspect/remove
  commands and MCP search tools
- **Then** each behaves as documented for v1, with no v2-only required flags

### Requirement: Incremental update parity (R5)

Updating a v2 collection SHALL be incremental: only new or changed source
documents are re-embedded, deleted documents are removed, and unchanged
documents are not reprocessed.

#### Scenario: incremental v2 update

- **Given** a v2 collection whose source has one modified, one added, and one
  deleted document
- **When** the user runs update
- **Then** exactly the modified and added documents are re-embedded, the
  deleted document no longer matches any search, and unchanged documents are
  not reprocessed

### Requirement: v1 remains untouched (R6)

All v1 behavior — including on-disk byte-stability, scoring, and CLI/MCP output
— MUST remain unchanged. No v1 workflow acquires a new required step.

#### Scenario: v1 lifecycle unchanged

- **Given** the v2 feature is installed
- **When** a user runs the full v1 lifecycle (create, search, update, inspect,
  remove) without engine selectors
- **Then** behavior and on-disk artifacts are identical to before the feature

### Requirement: Migration on explicit request (R7)

The system SHALL migrate a v1 collection to v2 only on explicit request, with:
a dry-run preview, an automatic backup, rollback on failure, and post-migration
validation. Migration MUST NOT require source access by default (it re-embeds
from stored content) and MUST NOT remove v1 data until validation passes.

#### Scenario: dry run predicts, changes nothing

- **Given** a v1 collection
- **When** the user runs migration in dry-run mode
- **Then** the report shows document/chunk counts, the target embedding model
  and store, and no file changes occur

#### Scenario: failed migration leaves v1 intact

- **Given** a v1 collection and a migration that fails mid-way
- **When** the failure occurs
- **Then** the v1 collection remains fully usable and no partial v2 collection
  is left behind

#### Scenario: offline migration

- **Given** a v1 collection whose source credentials are no longer available
- **When** the user migrates without the from-source option
- **Then** migration succeeds using the stored document content

### Requirement: Local, self-contained embeddings (R8)

v2 SHALL run fully locally and self-contained. Its default embedding model
SHALL be the same model v1 uses, so v2 relevance matches v1 1:1; model data
already cached for v1 SHALL be reused without re-download; and no network
access SHALL occur at any point. Remote embedding providers are out of scope
(future work).

#### Scenario: same model as v1, fully local

- **Given** no embedding configuration
- **When** a v2 collection is created and searched
- **Then** the same local model as v1 embeds the text and no network request
  is made

#### Scenario: no duplicate model download

- **Given** the v1 embedding model is already cached locally
- **When** a v2 collection is created
- **Then** no model download occurs

### Requirement: Recorded, dispatched store identity (R9)

v2 SHALL use an embedded store requiring no external service or daemon, SHALL
record the store identity in each collection, and MUST load each collection
with its recorded store — failing loud on an unrecognized identity, never
silently substituting another store. Additional stores are out of scope
(future work behind this seam).

#### Scenario: default store is zero-setup

- **Given** a fresh install
- **When** a v2 collection is created with no store configuration
- **Then** it works offline with no additional service or daemon

#### Scenario: unrecognized store fails loud

- **Given** a collection whose recorded store identity this install does not
  support
- **When** it is loaded for any operation
- **Then** the operation fails naming the recorded store, and no other store
  is silently used

### Requirement: Optional reranking (R10)

v2 search SHALL support an optional, locally-run reranking stage, disabled by
default.

#### Scenario: rerank is opt-in

- **Given** reranking is not enabled
- **When** the user searches a v2 collection
- **Then** results are pure vector-similarity ordered with no reranker model
  loaded

### Requirement: Unified relevance semantics (R11)

v2 SHALL report similarity scores where higher is better. Any view that merges
results from both engines MUST rank on one comparable relevance measure.
Score-threshold options SHALL be engine-appropriate and documented.

#### Scenario: mixed results rank comparably

- **Given** a v1 and a v2 collection with related content
- **When** the user searches across both
- **Then** the merged ranking reflects true relative relevance (no engine's
  results systematically mis-sorted by raw score units)

### Requirement: Performance and privacy budgets hold (R12)

CLI startup MUST remain under 1 second with v2 installed. v2 search latency
MUST stay within 2× of v1 at the documented scale (<100k docs). No network
access occurs unless a remote provider is explicitly configured.

#### Scenario: startup budget

- **Given** the package with v2 installed
- **When** the user runs the help command
- **Then** it completes in under 1 second

### Requirement: Engine-aware diagnostics (R13)

Inspect, status, and debug output SHALL show each collection's engine version,
embedding model/provider, and store type, so users can always tell which engine
owns which collection.

#### Scenario: inspect shows engine identity

- **Given** one v1 and one v2 collection
- **When** the user inspects them
- **Then** each row shows its engine version, and the v2 row shows its
  embedding model/provider and store type

---

## Non-Goals

- Remote/API embedding providers (Ollama, OpenAI-compatible, …) — future
  work once the local core is proven (maintainer decision 2026-07-18:
  local-only, self-contained first).
- Additional vector stores (Qdrant, …) — the store-identity seam ships now;
  alternatives come later.
- Knowledge-graph indexing and retrieval — requires an LLM to add value;
  future sibling feature, LLM-gated.
- Hybrid/BM25 retrieval and query fusion — future sibling feature on top of v2.
- Flipping the built-in default engine to v2 — a separate, evidence-gated
  decision after dogfooding (criteria approved 2026-07-18; see plan).
- Automatic or implicit migration of v1 collections.
- Removing or deprecating the v1 engine (no deprecation planning now).
- New connectors, parsing changes, or server/multi-user deployment.
