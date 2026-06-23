---
type: feature-plan
feature: blame-ownership
sibling: tech.md
parent: ../../plan.md
updated: 2026-06-23
---

# Feature: Blame & Ownership — Implementation Plan

Surface existing git provenance in four small, mostly-independent steps: a shared
ownership aggregator, then search output (CLI + JSON/MCP), the `who_owns` MCP
tool, and the CLI ownership view. All work lives in `apps/indexed`; no engine or
persistence changes.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Starts only when the **git-metadata-enrichment** feature is
DONE — this feature reads the per-chunk git fields that feature persists
(`last_author`, `touching_commits`, `commit_count`, `last_committed_date`) in
chunk metadata and `index_document_mapping.json`. It captures nothing itself.

## Problem Frame

Search already surfaces *what* matches; it cannot surface *who* owns it, so users
context-switch to git to find the right person. The git-metadata-enrichment
feature has already attached blame facts to chunks and returns them on
`matchedChunks`. The only gap is presentation: a reusable aggregator plus three
thin surfaces (search output, an MCP tool, a CLI view), each degrading cleanly
when a collection has no git metadata. Because enrichment is the data source,
this feature must not begin until that feature has shipped.

## Requirements Trace

| Requirement | Description | Units |
|-------------|-------------|-------|
| R1 | Search results show last author + contributors (CLI/JSON/MCP) | blame-ownership/1, blame-ownership/2 |
| R2 | `who_owns(path \| symbol)` MCP tool returns owners + commits | blame-ownership/1, blame-ownership/3 |
| R3 | CLI ownership view summarising contributors | blame-ownership/1, blame-ownership/4 |
| R4 | Graceful empty/degraded display when no git metadata | blame-ownership/1, blame-ownership/2, blame-ownership/3, blame-ownership/4 |

## Key Technical Decisions

- **One shared aggregator.** A pure `ownership.py` (`build_ownership` +
  `Ownership` model) is the single source of truth for both CLI and MCP, keeping
  command files ≤150 lines and the degraded path in exactly one place (R4).
- **Reuse, don't rebuild.** `who_owns` rides the existing `svc_search` +
  `_resolve_config` path and the existing MCP error convention; the CLI view
  extends `index inspect` rather than adding a new command file.
- **Read-only.** No new persisted data, config keys, or embedded-text changes —
  ownership is derived from fields already on each chunk.

### blame-ownership/1 — Ownership aggregator
- **Goal:** A pure, tested helper that turns a chunk's git fields into a display
  model, with a defined empty state.
- **Requirements:** R1, R2, R3, R4
- **Dependencies:** —
- **Files:** `apps/indexed/src/indexed/knowledge/ownership.py`;
  `tests/unit/indexed/knowledge/test_ownership.py`
- **Test scenarios:** enriched fields → ranked contributors + last author;
  empty/None fields → `has_git_metadata=False`; `ownership_to_dict` round-trips.
- **Verification:** `uv run pytest tests/unit/indexed/knowledge/test_ownership.py -q`;
  `uv run mypy src/`

### blame-ownership/2 — Ownership in search output
- **Goal:** Show ownership in CLI cards and in JSON/MCP search output.
- **Requirements:** R1, R4
- **Dependencies:** blame-ownership/1
- **Files:** `apps/indexed/src/indexed/knowledge/commands/search.py`;
  `apps/indexed/src/indexed/mcp/formatting.py`; matching unit tests
- **Test scenarios:** enriched chunk renders author + contributors row;
  JSON/MCP chunk carries an `ownership` object; non-git chunk shows the dim
  "no git metadata" state without breaking layout.
- **Verification:** `uv run pytest -q -k "search or formatting"`;
  `uv run ruff check . --fix && uv run ruff format`

### blame-ownership/3 — `who_owns` MCP tool
- **Goal:** Add the `who_owns(target)` tool returning owners + contributing
  commits for a path or symbol.
- **Requirements:** R2, R4
- **Dependencies:** blame-ownership/1
- **Files:** `apps/indexed/src/indexed/mcp/tools.py`;
  `tests/unit/indexed/mcp/test_who_owns.py`
- **Test scenarios:** path target resolves via `documentPath`; symbol target
  resolves via `svc_search`; no-git target returns a structured empty result;
  service failure returns `{"error": ...}`.
- **Verification:** `uv run pytest -q -k who_owns`; `uv run mypy src/`

### blame-ownership/4 — CLI ownership view
- **Goal:** Surface an aggregated contributor summary in `index inspect`.
- **Requirements:** R3, R4
- **Dependencies:** blame-ownership/1
- **Files:** `apps/indexed/src/indexed/knowledge/commands/inspect.py`;
  matching unit tests
- **Test scenarios:** git collection renders a contributors card with counts +
  last touch date; non-git collection renders the degraded note.
- **Verification:** `uv run pytest -q -k inspect`;
  `uv run pytest -q --cov=src` (suite >85%)
