---
type: feature-product
feature: blame-ownership
sibling: tech.md
parent: ../../product.md
updated: 2026-06-23
---

# Feature: Blame & Ownership — Product

Developers and AI agents who find code through search still have to leave the
tool to learn *who* owns or last touched it, then guess who to ask. This feature
**surfaces** the per-chunk git provenance that the git-metadata-enrichment
feature already captures (`last_author`, `touching_commits`, `commit_count`,
`last_committed_date`) — in search output, through a new `who_owns` MCP tool, and
in a CLI ownership view. It only formats and exposes ownership; it never captures
or persists blame.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| Owns | Does not own |
|------|--------------|
| Last-author + contributors shown in search output (CLI cards, JSON, MCP) | Capturing/persisting blame (git-metadata-enrichment feature provides it) |
| The `who_owns(path \| symbol)` MCP tool | Git-signal re-ranking ([#144](https://github.com/LennardZuendorf/indexed/issues/144)) |
| A CLI ownership view summarising contributors | Commit-as-document indexing (git-history-documents feature) |
| Graceful empty/degraded display when a collection has no git metadata | Embedding model / vector index changes |

---

## Requirements

### Requirement: Search results SHALL show last author + contributors for matched chunks

Across the CLI card output, the CLI/MCP JSON output, and the MCP `search` tool,
every matched chunk that carries git metadata shall display its `last_author`
and the set of contributors derived from `touching_commits`.

#### Scenario: Git-enriched chunk in CLI cards
- **Given** a search match on a chunk that carries git metadata
- **When** results render as cards
- **Then** the meta card shows the last author and a short contributors summary

#### Scenario: Git-enriched chunk in JSON / MCP output
- **Given** the same match returned via `--simple-output` JSON or the MCP `search` tool
- **When** the result is serialized
- **Then** each chunk includes an `ownership` object with `last_author`,
  `contributors`, `commit_count`, and `last_committed_date`

### Requirement: The MCP `who_owns(path | symbol)` tool MUST return owners and contributing commits

A new MCP tool shall accept a file path or a code symbol and return the owners
(ranked by contribution) plus the contributing commits for the matching chunks,
reusing the same `SearchService` and `ConfigService` as the existing tools.

#### Scenario: Lookup by file path
- **Given** an indexed git collection containing `src/auth/login.py`
- **When** an agent calls `who_owns(target="src/auth/login.py")`
- **Then** the response lists owners ranked by contribution plus the contributing
  commits, each with author and date

#### Scenario: Lookup by symbol
- **Given** a collection containing a function `validate_token`
- **When** an agent calls `who_owns(target="validate_token")`
- **Then** the response resolves the symbol to matching chunks and returns their
  owners and contributing commits

### Requirement: A CLI ownership view SHOULD summarise contributors for a collection or path

The CLI shall offer an ownership view (surfaced through `index inspect` or a
dedicated display) that aggregates contributors and last-touched dates so a user
can see ownership at a glance using the existing Rich card design.

#### Scenario: Ownership summary for a collection
- **Given** a git-enriched collection
- **When** the user requests the ownership view
- **Then** a Rich card lists top contributors with their commit counts and the
  most recent touch date

### Requirement: Display MUST degrade gracefully when a collection has no git metadata

When matched chunks or a target carry no git fields (e.g. indexed from a non-git
source), ownership surfaces shall render a clear empty/degraded state rather than
failing or showing blanks.

#### Scenario: Non-git collection in search output
- **Given** a collection indexed from a non-git source
- **When** results render with ownership enabled
- **Then** the ownership area shows an explicit "no git metadata" note and the
  rest of the result renders normally

#### Scenario: `who_owns` on a target with no git data
- **Given** a target whose chunks carry no git fields
- **When** `who_owns` is called
- **Then** the tool returns a structured empty result explaining no git metadata
  is available, not an error

## Non-Goals

- No re-ranking of search results by authorship or recency ([#144](https://github.com/LennardZuendorf/indexed/issues/144)).
- No new persisted data — this feature is read-only over existing git metadata.
