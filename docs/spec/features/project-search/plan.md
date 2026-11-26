---
type: feature-plan
feature: project-search
sibling: tech.md
parent: ../../plan.md
updated: 2026-11-26
---

# Feature: Project Search — Plan

**Parent:** issue [#340](https://github.com/LennardZuendorf/indexed/issues/340) ·
**Product:** [product.md](product.md) · **Tech:** [tech.md](tech.md).

## Slices

| # | Slice | Gate | Status |
|---|-------|------|--------|
| 1 | `WorkspaceSelection.unresolved` + `strict` resolution; search degrades instead of exiting 1 | a selection with a vanished entry returns the rest and exits 0 | this PR |
| 2 | `sources` on `indexed.search/1`; CLI and MCP declare the same scope; `empty` reported | three seeded collections → three `ok`; one deleted → `missing` + hits from the other two | this PR |
| 3 | GitHub comment id/url, comment bodies chunked like bodies, `Hit.url` | a long comment yields bounded hits that each name the comment | this PR |
| 4 | Four-way retrieval comparison, latency, distractor rates, default choice | measured on a payload that can report a dead source | next card (#340, slice 3) |

Slices 1–3 ship together: a `sources` array that cannot say `missing` would be
the very silence the card exists to remove, and the bounded-detail assertion
needs the comment change to have something to bound.

## Dependencies

- #344 (workspace selection) — shipped; this narrows its fail-closed rule for
  search only.
- #204 (retrieval-eval) — the next card measures on this payload.

## Evidence

| Requirement | Proof |
|---|---|
| R1 citable hits | `tests/system/test_project_search_sources.py::test_each_source_is_citable` |
| R2 intent visible | `tests/unit/indexed/mcp/test_source_status_payload.py::test_a_declared_source_the_engine_never_saw_is_missing` |
| R3 empty ≠ no match | `::test_an_empty_collection_is_not_a_zero_hit_match`, `tests/system/test_project_search_sources.py::test_an_emptied_source_is_reported_empty` |
| R4 one dead source does not blank the rest | `tests/system/test_project_search_sources.py::test_a_deleted_source_leaves_the_others_answering`, `tests/unit/indexed/knowledge/commands/test_search.py::TestWorkspaceSelectionScope::test_a_selected_collection_that_vanished_is_named_and_the_rest_search` |
| R5 bounded detail | `tests/system/test_project_search_sources.py::test_payload_and_hit_text_stay_bounded` |
| R6 additive contract | `tests/unit/indexed/mcp/test_search_payload_golden.py` (one builder, byte-identical across CLI and MCP) |
| CLI/MCP parity | `tests/unit/indexed/mcp/test_search_workspace_scope.py::test_mcp_search_uses_the_workspace_selection`, `::test_mcp_search_never_widens_to_the_store_when_every_selection_is_dead` |
