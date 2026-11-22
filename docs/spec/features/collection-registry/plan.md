---
type: feature-plan
feature: collection-registry
sibling: tech.md
parent: ../../plan.md
updated: 2026-11-22
---

# Feature: Shared Collection Registry — Plan

**Parent:** issue [#346](https://github.com/LennardZuendorf/indexed/issues/346) ·
**Product:** [product.md](product.md) · **Tech:** [tech.md](tech.md).

## Slices

| # | Slice | Gate | Status |
|---|-------|------|--------|
| 1 | Registry + pointer files (`config/collections_registry.py`) | stable id survives reload; same name at a second path refused | ✅ DONE |
| 2 | Migration service + journal (`cli/storage/commands/_migration.py`) | dry run writes nothing; interrupted run resumes to one copy | ✅ DONE |
| 3 | `indexed storage migrate` command (group + flat) | `--dry-run`, `--on-collision`, `--rollback` reachable and rendered | ✅ DONE |
| 4 | Pointer-aware `resolve_collections_context` | a pointed workspace searches the shared store from CLI and MCP | ✅ DONE |

## Dependencies

- None. This is the spine: #344 (committed repository definitions) and #345
  (per-request scope) build on the registry, not the other way round.
- Rollback restores the pre-migration storage layout, so removing the
  local/global modes (milestone #229's end state) must come after, and must
  re-target `--rollback` at whatever layout replaces it.

## Evidence for slice 1–4

| Requirement | Proof |
|---|---|
| R1 reuse, one copy | `tests/system/test_collection_registry.py::test_two_workspaces_reuse_one_collection` |
| R2 dry run, idempotent, resumable | `tests/system/test_collection_registry.py::test_dry_run_is_idempotent_and_resumable` |
| R3 rollback + engine read-back | `tests/system/test_collection_registry.py::test_rollback_restores_local_collection_and_engine_reads_correct_engine` |
| R4 collisions named | `tests/unit/indexed/storage/test_migration.py::test_plan_reports_collision_kinds_without_writing`, `::test_adopt_policy_marks_identical_copies`, `::test_rename_policy_targets_a_distinct_name`, `::test_real_migration_refuses_collisions_before_touching_data` |
| Registry durability | `tests/unit/indexed/config/test_collections_registry.py` (11 cases) |
| R5 same surface in CLI and MCP | the R1 test drives `indexed ... search` in both workspaces; both go through `resolve_collections_context` |

Run:

```bash
uv run pytest tests/system/test_collection_registry.py tests/unit/indexed/config/test_collections_registry.py tests/unit/indexed/storage/test_migration.py -q
```
