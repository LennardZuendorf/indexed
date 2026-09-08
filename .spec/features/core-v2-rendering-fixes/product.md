---
type: feature-product
feature: core-v2-rendering-fixes
sibling: tech.md
parent: ../../product.md
updated: 2026-09-02
---

# Feature: Core v2 Rendering Fixes — Product

Remediation of the eight visual/rendering-consistency defects tracked in
[issue #187](https://github.com/LennardZuendorf/indexed/issues/187), clustered from
the [PR #162 Core v2 review](https://github.com/LennardZuendorf/indexed/blob/claude/pr-162-review-testing-ldg0qp/reviews/pr-162-core-v2-review.md)'s
P3 "polish" tier (plus the CLI-rendering slice of two P2 findings — the review's
deeper MCP-envelope/unbounded-score correctness bugs are explicitly out of scope
here, already tracked separately). The baseline CLI renders cleanly; these are a
scattered tail of inconsistencies on the new v2 surface, not one big flaw. Users are
indexed CLI operators; the output is visually consistent, honest, and legible
regardless of terminal width or which engine/feature (v1/v2, rerank) produced a
result.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | Fixes at the eight confirmed defect sites in `src/indexed/cli/` (error rendering, detail cards, update summary, `--help`, search-result rendering, inspect list/detail views) and `src/indexed/core/engine.py` (collection-group ordering) plus `src/indexed/connectors/files/schema.py` (pattern-display root cause); regression tests per fix |
| **Does not own** | The reranking correctness bugs from the same review (unbounded rerank score treated as bounded cosine, `mcp/formatting.py` mislabeling rerank as cosine in the JSON envelope, `--simple-output` JSON contract violations, manifest-version blast radius, config validation inconsistency) — those are P1/P2 correctness defects tracked outside issue #187; new features; style/formatting unrelated to the eight findings |

---

## Requirements

All eight are **P3** (polish/consistency) per the source review's own severity
tiering — none crash or lose data — except R5, which the investigation upgraded:
an existing test (`test_other_matches_excludes_promoted_top`) currently *asserts*
the buggy behavior as correct, so it's the one requirement here with an existing
regression guard that must be **corrected**, not just extended.

### Requirement: Engine-mismatch errors render as a panel like every other CLI error

The system MUST render `CoreError` subtypes that reach the top-level CLI handler
(`EngineMismatchError`, `UnknownEngineVersionError`, and any other `IndexedError`
that escapes per-command handling) inside the same `✗`-panel format every other
CLI error uses — never as bare styled text.

#### Scenario: creating a collection with a mismatched engine

- **Given** a collection named `docs` already exists as a v2 collection
- **When** the user runs `indexed index create files --collection docs --engine v1`
- **Then** the resulting `EngineMismatchError` MUST render inside a bordered `✗` panel (the same shape `migrate`'s own errors use), not as plain styled console text.

### Requirement: Detail cards size to the terminal, not a fixed 60 columns

The system MUST derive the detail-card width from the live terminal width (with a
sane min/max clamp), so `inspect <name>` and every `migrate` panel stop truncating
the engine/model descriptor regardless of actual terminal width.

#### Scenario: wide terminal, single-collection inspect

- **Given** a terminal at least 100 columns wide
- **When** the user runs `indexed index inspect docs` (a v2 collection with a long embedding-model descriptor)
- **Then** the model descriptor MUST render on one line, not wrap ragged across multiple lines at a fixed 60-column card width.

### Requirement: `index update`'s "Included Patterns" row shows the user's own pattern text

The system MUST NOT display an internal regex-translated form of a glob pattern
(e.g. `(?s:.*)\Z`) in any user-facing summary row; it MUST show the pattern text
the user configured (or the existing `"* (all files)"` default label), aligned
consistently with the `Type`/`Excluded` rows around it.

#### Scenario: updating a files collection created with default include patterns

- **Given** a files collection created with no `--include` flag (default `*`)
- **When** the user runs `indexed index update docs`
- **Then** the "Included Patterns" row MUST show `* (all files)`, never a raw compiled-regex string, and MUST be padded consistently with the other summary rows.

#### Scenario: updating a files collection created with a custom glob

- **Given** a files collection created with `--include '*.py'`
- **When** the user runs `indexed index update docs`
- **Then** the "Included Patterns" row MUST show `*.py`, never its `fnmatch.translate()` form.

### Requirement: `index create files --help` renders its option table without mid-word truncation

The system MUST render every option name in `index create files --help` in full at
a standard 80-column terminal, consistent with every other `--help` screen in the
CLI, never truncated mid-word with an ellipsis.

#### Scenario: standard-width terminal

- **Given** an 80-column terminal
- **When** the user runs `indexed index create files --help`
- **Then** the gitignore-related boolean flag pair MUST render in full (no `…` mid-word cut), matching the clean rendering of every other option in the same table.

### Requirement: "Other Search Query Matches" never outranks "Top Result"

The system MUST apply the same content-free-chunk filter to both the "Top Result"
selection and the "Other Search Query Matches" list, so the list below the
headline can never contain a strictly better-scored, non-content-free chunk than
the one promoted above it. When every candidate chunk is content-free, the
existing fallback behavior (first chunk as Top Result, "No excerpt available"
messaging) MUST still hold — this requirement must not introduce a crash or an
empty Top Result on that edge case.

#### Scenario: low-signal query surfaces a content-free chunk ahead of a real match

- **Given** a collection with one high-scoring content-free chunk (e.g. a bare file-path chunk) and one lower-scoring but real-content chunk
- **When** the user runs a low-signal search that would otherwise promote the content-free chunk
- **Then** "Top Result" MUST show the best non-content-free chunk, and "Other Search Query Matches" MUST NOT list the content-free chunk above it.

### Requirement: Rendered scores are labeled with their scale

The system MUST visually distinguish a reranked score (unbounded, e.g.
`[-11.23, +6.27]` observed) from a cosine-similarity score (`[0, 1]`) wherever a
per-result score renders in the CLI, using the `scoreKind` already carried by the
search result.

#### Scenario: reranking is enabled

- **Given** `core.v2.rerank.enabled` is `true` for a v2 collection
- **When** the user searches that collection
- **Then** each rendered score MUST carry a visible label distinguishing it as a rerank score, not indistinguishable from a cosine score.

### Requirement: `inspect` list view shows a collection's `Path` in full

The system MUST NOT truncate a `Path` value in the `index inspect` list view (all
collections) any more aggressively than the single-collection detail view does for
the same collection at the same terminal width.

#### Scenario: multiple collections listed at once

- **Given** three collections listed together via `indexed index inspect` (no name argument)
- **When** one collection's path is long enough to display in full in `indexed index inspect <that-name>`
- **Then** the list view MUST show that same path without truncating it purely because multiple cards are laid out side by side.

### Requirement: `inspect`'s collection groups render in a stable order

The system MUST order engine groups in `inspect`/`status` output by a deterministic
key (e.g. ascending engine version), never by which collection happened to be
encountered first, so migrating or creating one collection cannot reorder
unrelated groups.

#### Scenario: migrating one collection to v2

- **Given** an existing list of v1 collections displayed via `indexed index inspect`
- **When** the user migrates one alphabetically-early v1 collection to v2 and re-runs `indexed index inspect`
- **Then** the v1 group's internal order and position relative to the (new) v2 group MUST follow the deterministic ordering rule, not jump based on migration order.
