---
type: feature-product
feature: foundation
sibling: tech.md
parent: ../../product.md
updated: 2026-07-06
---

# Feature: Foundation — Architecture & Correctness

Make `indexed` **correct** and make its core **swappable**. The 2026-07-06
architecture audit found the search data path silently discards most content,
several reproduced corruption/data-loss/secret paths, and untyped stringly-keyed
contracts that let the engine and its callers drift without a type error. This
feature fixes every audited defect and lays the two structural pieces a future
v2 engine rewrite needs — typed data contracts and a single core facade — while
leaving the on-disk collection format byte-compatible so existing collections
keep working. It does **not** collapse the workspace, delete dead code, or
shrink CLI/config chrome; that is the follow-on Feature `simplify`, which is
gated on this one being DONE.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | The typed data contracts between layers (manifest, converted document, chunk, search result, source config) and the connector protocols; config **write** semantics (read-mostly runtime, atomic persist, secret routing); failure behavior of the CLI and MCP surfaces; connector content fidelity (attachments, incremental change detection, ADF/storage-format extraction, the off-origin credential guard); search recall correctness (chunking, `max_docs`, `score_threshold`); storage durability (FAISS persistence on every mutation, safe create); the core **swap facade** and the composition/wiring seam. |
| **Does not own** | Package layout — all work stays in the current 7-package workspace (collapse is Feature `simplify`). Deleting dead code, mechanism tests, or the never-batching batch (Feature `simplify`). Shrinking CLI/config chrome or the Rich component library (Feature `simplify`). The v2 engine implementation itself — this feature only builds the seam it drops into. The embedding model, FAISS index type, and search semantics beyond the recall fixes. New sources, commands, or MCP tools. The on-disk collection format, which is kept byte-compatible. |

---

## Requirements

### Requirement: Typed data contracts

The system SHALL express the manifest, converted document, chunk, search
result, and source config as typed Pydantic models defined in one module, and
the connector protocols SHALL declare the methods the engine actually calls
(`get_number_of_documents`, `read_all_documents`, `get_reader_details`,
`convert`) rather than a fictional method no caller invokes. The models MUST
round-trip today's camelCase collection JSON byte-stable so existing collections
keep working without re-indexing, and a contract mismatch between a producer and
a consumer MUST surface as a mypy error rather than a runtime `KeyError`.

#### Scenario: Manifest is read through a model

- **Given** a collection created before this feature, with its camelCase `manifest.json` on disk
- **When** any code reads the collection's manifest
- **Then** it is parsed into and re-serialized from one typed model with byte-identical output, and no code accesses `manifest["reader"]["type"]`-style string keys

#### Scenario: Protocol matches the calls the engine makes

- **Given** the corrected reader protocol
- **When** each shipped reader is checked against it by mypy
- **Then** every reader conforms, the engine is typed against only protocol methods, and adding a caller of a method not on the protocol fails type-checking

### Requirement: Core swap seam

The app (CLI and MCP) SHALL call the core only through a single facade exposing
`create` / `update` / `search` / `inspect` / `remove`; the core MUST NOT import
connectors or the app, and connectors MUST NOT import the core. Wiring SHALL
flow through one composition module that injects the connector-construction and
cache-decoration dependencies the core needs as **required** callables, with no
`| None` parameters guarded at runtime. A slim import check MUST enforce these
edges, and the on-disk collection format MUST be unchanged so that a future v2
engine implementing the same facade over the same disk format is a drop-in
replacement requiring no change to CLI, MCP, connector, or config code.

#### Scenario: v2 engine is a drop-in

- **Given** a hypothetical alternate engine implementing the same facade over the same disk format
- **When** the composition module is pointed at it
- **Then** no CLI, MCP, connector, or config code changes, and existing collections search identically

#### Scenario: Layer edges are enforced

- **Given** the import check that guards the four module edges
- **When** a forbidden import is added (core importing a connector, or a connector importing core)
- **Then** the check fails in CI

### Requirement: Read-mostly configuration

Runtime flows — create, update, and search — MUST NOT write to the user's
`config.toml`. CLI-argument overrides, date-stamped incremental queries, and
incremental cutoffs SHALL flow as an in-memory overlay only. The single write
path SHALL be the explicit `indexed config set` family, which persists
atomically and routes secret fields to `.env` — never into TOML and never echoed
in plaintext. Path and storage-mode resolution SHALL have one source of truth
rather than the triplicated logic in place today.

#### Scenario: Update leaves config untouched

- **Given** a `config.toml` describing a Jira source with a stored query
- **When** `indexed index update <collection>` runs
- **Then** `config.toml` is byte-identical afterwards — no date-stamped query, no URL echo, no baked-in CLI override — while the in-memory incremental cutoff is still applied to the request

### Requirement: Search recall correctness

Documents SHALL be chunked to the embedder's real token window so no chunk is
silently truncated at embed time; `max_docs` MUST be honored, with neighbor
retrieval decoupled from the document cap and backfill after the score filter so
the requested number of documents is returned when that many match; and
`score_threshold` MUST have the correct scale, direction, and range for the
distance metric actually used, with a description that matches the behavior.

#### Scenario: Large document is fully searchable

- **Given** a document several thousand tokens long with no headings
- **When** it is indexed and a query matches text near its end
- **Then** that text lives in its own chunk within the embedder's token window and is returned as a hit — not truncated away

#### Scenario: max_docs is honored despite a chunk-heavy document

- **Given** a collection where one document produces many chunks and several other documents each match a query
- **When** a search requests `max_docs` results with a `score_threshold` set
- **Then** the chunk-heavy document does not starve the others, and the result set contains as many distinct qualifying documents as `max_docs` when that many pass the threshold

### Requirement: Storage durability

The FAISS index SHALL be persisted to disk on every mutating operation,
including a deletions-only incremental update, so on-disk vectors never outlive
their mapping keys; a zero-chunk batch MUST NOT crash the embed or index path; a
failed create MUST NOT destroy a pre-existing collection of the same name; and
`indexed config set` MUST NOT be able to truncate or destroy `config.toml` under
any input.

#### Scenario: Delete-then-search stays consistent

- **Given** a collection with one document removed via an incremental update that deletes but adds nothing
- **When** any subsequent query runs whose neighbors include the removed document's former vectors
- **Then** the on-disk FAISS index and the id-to-chunk mapping agree — no orphaned vector, no `KeyError`, no whole-collection error

#### Scenario: A bad config set cannot destroy the file

- **Given** an existing `config.toml`
- **When** `indexed config set <key> null` (or any unserializable value) runs
- **Then** the value is rejected before the file is touched, `config.toml` is left byte-identical, and no partial or zero-byte write occurs

### Requirement: Connector fidelity

Attachments SHALL download successfully when the source redirects to an
off-origin CDN; incremental change detection MUST catch working-tree edits that
were reverted and MUST handle non-ASCII filenames; ADF and storage-format
extraction MUST retain text carried on leaf nodes (mentions, inline/link cards,
media, images, emoji, dates); and the off-origin credential guard MUST parse the
request authority the same way the HTTP client does, so it neither leaks
credentials to a look-alike host nor drops legitimate hosts.

#### Scenario: Redirected attachment is indexed

- **Given** a Jira or Confluence Cloud attachment whose download 302-redirects to a media/S3 host
- **When** the collection is created or updated
- **Then** the client follows the redirect, fetches the content, and the attachment text is indexed rather than silently skipped

#### Scenario: Credential guard matches the HTTP client

- **Given** a URL crafted so a naive authority parse sees an allowed host but the HTTP client would send the request elsewhere
- **When** the guarded request is prepared
- **Then** the guard resolves the same authority the client will use and refuses to attach credentials to the off-origin destination, while a legitimate trailing-dot host is still allowed

### Requirement: Honest CLI and MCP behavior

Missing or corrupt collections SHALL fail loud with a documented,
"not found"-class error and a non-zero exit — never a traceback and never a
success exit. User-supplied and indexed-content strings MUST NOT crash Rich
markup rendering. The `--verbose` and log-level flags MUST actually take effect.
The MCP surface MUST NOT serve hour-stale cached results after a re-index, MUST
NOT silently swallow a per-collection failure as "0 matches", and MUST return
its structured error envelope for any exception raised while serving a call.
Every config section that is settable MUST actually be read by the code.

#### Scenario: Missing collection fails cleanly

- **Given** a nonexistent or corrupt collection name
- **When** `search`, `update`, or `inspect` targets it
- **Then** the user sees a "not found"-class error and the process exits non-zero — never a raw `IndexError`/traceback, and never a misleading success exit

#### Scenario: MCP never leaks a raw exception or a swallowed failure

- **Given** an MCP client searching across collections where one collection's index is corrupt
- **When** the tool call runs
- **Then** the response is the structured error envelope surfacing that collection's failure — not a protocol-level exception and not a silent "0 matches" that hides the broken index

## Non-Goals

- Rewriting the engine — v2 is a separate future feature; this feature only builds its seam.
- Changing the embedding model, FAISS index type, or search semantics beyond the recall fixes.
- Collapsing the workspace, deleting dead code, or shrinking CLI/config chrome — all Feature `simplify`.
- New sources, commands, or MCP tools.
- Any change to the on-disk collection format.
