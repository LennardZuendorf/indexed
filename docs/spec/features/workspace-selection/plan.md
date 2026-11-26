---
type: feature-plan
feature: workspace-selection
sibling: tech.md
parent: ../../plan.md
updated: 2026-11-22
---

# Feature: Workspace Selection — Plan

**Parent:** issue [#344](https://github.com/LennardZuendorf/indexed/issues/344) ·
**Product:** [product.md](product.md) · **Tech:** [tech.md](tech.md).

## Slices

| # | Slice | Gate | Status |
|---|-------|------|--------|
| 1 | `config/workspace_selection.py` — discovery, parse, resolve | malformed/unsupported/unresolvable each raise with the file and entry named | ✅ DONE |
| 2 | `resolve_collections_context` honours the definition; `CliContext` carries the scope and its notices | a definition selects the global store from `--local`, the local store without one | ✅ DONE |
| 3 | `indexed search` scope, the `--collection` out-of-scope notice, the create notice | selected search hits only selected collections; notices stay off JSON stdout | ✅ DONE |
| 4 | LSP `KnowledgeBackend` scope | `statuses()` filtered, same names as the CLI | ✅ DONE |
| 5 | `indexed storage migrate` writes `indexed.toml`; `--rollback` removes its entry | two projects reuse one collection through their definitions | ✅ DONE |
| 6 | Pointer demoted to a read-only compatibility path | an old pointer still routes and warns naming `indexed.toml` | ✅ DONE |

Slices 1–6 ship in one PR: 2 and 5 are the same migration (a definition that
nothing reads is not a migration), and the pointer demotion is what makes them
safe to land together.

## Dependencies

- #346 (registry) — shipped, this builds on `CollectionRegistry`.
- #345 (per-request MCP scope) — a separate feature
  ([mcp-request-scope](../mcp-request-scope/tech.md)). It consumes the
  `CliContext.selection` this feature produces and applies it per request from
  the client's MCP roots.
- Removing `--local`/`--global` entirely (milestone #229's end state) is a later
  slice; `--rollback` re-targets then, not now.

## Evidence

| Requirement | Proof |
|---|---|
| R1 two clones, one selection | `tests/unit/indexed/config/test_workspace_selection.py::test_two_clones_resolve_the_same_selection`; `tests/system/test_collection_registry.py::test_two_workspaces_reuse_one_collection` |
| R2 selection, not a store | `::test_definition_writes_nothing_into_the_workspace` |
| R3 fails closed | `::test_read_definition_is_loud` (parametrised: missing/unsupported version, no entries, bad entry), `::test_unknown_name_names_the_file_and_entry`, `::test_unknown_stable_id_is_loud`, `::test_registered_but_missing_data_is_loud`, `::test_duplicate_entry_is_loud`, `tests/unit/indexed/test_runtime_context.py::test_definition_fails_closed_on_an_unresolvable_entry`, `tests/unit/indexed/knowledge/commands/test_search.py::TestWorkspaceSelectionScope::test_a_selected_collection_that_vanished_fails_closed` |
| R4 absence means no scope | `tests/unit/indexed/test_runtime_context.py::test_resolve_collections_context_local_mode`, `tests/unit/indexed/knowledge/commands/test_search.py::TestWorkspaceSelectionScope::test_no_selection_searches_every_collection`, `tests/unit/indexed/lsp/test_backend_selection.py::test_no_selection_leaves_statuses_unfiltered` |
| R5 explicit collection wins, loudly | `TestWorkspaceSelectionScope::test_out_of_selection_collection_warns_and_runs`, `::test_out_of_selection_warning_stays_off_json_stdout` |
| Precedence | `tests/unit/indexed/test_runtime_context.py::test_definition_selects_the_global_store_from_local_mode`, `::test_definition_beats_the_legacy_pointer`, `::test_legacy_pointer_still_routes_and_warns` |
| LSP parity | `tests/unit/indexed/lsp/test_backend_selection.py::test_statuses_filter_to_the_selected_names`, `::test_the_filter_is_applied_to_the_cached_snapshot` |
| Migration writes the definition | `tests/unit/indexed/storage/test_migration.py::test_migrate_writes_the_definition_at_the_git_root`, `::test_migrate_writes_the_definition_above_a_nested_workspace`, `::test_migrate_refuses_a_directory_outside_git`, `::test_rollback_removes_its_entry_then_deletes_the_definition` |

Run:

```bash
uv run pytest tests/unit/indexed/config/test_workspace_selection.py \
  tests/unit/indexed/test_runtime_context.py \
  tests/unit/indexed/lsp/test_backend_selection.py \
  tests/unit/indexed/knowledge/commands/test_search.py \
  tests/unit/indexed/storage/test_migration.py \
  tests/system/test_collection_registry.py -q
```
