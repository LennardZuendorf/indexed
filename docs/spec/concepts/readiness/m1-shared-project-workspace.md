---
type: concept
updated: 2026-11-23
---

# Shared Project Workspace (M1)

[GitHub milestone 11](https://github.com/LennardZuendorf/indexed/milestone/11) · [Parent issue #229](https://github.com/LennardZuendorf/indexed/issues/229) · [Readiness](README.md)

A developer can index a collection once, select it from several repositories and understand which collections a query will use.

| Requirement | Observable behavior |
| --- | --- |
| Shared storage | Multiple projects can reference one collection. Selecting it or moving a checkout leaves the existing index data reusable. |
| Repository selection | Indexed reads one committed `indexed.toml` at or above the Git worktree root: `version = 1` and a `[collections].use` array of stable collection ids or names. The file is a selection, never a store — no collection data, no absolute paths, no credentials. It replaces the `.indexed/collections.json` workspace pointer, which stays readable and deprecated for workspaces migrated before it and is never written again. A definition pins collections and document caches to the global store, so `--local` is ignored and says so. The developer can inspect the resolved project and selection. Engine settings and credentials keep their existing configuration. |
| Request isolation | CLI, MCP and LSP resolve the same project selection. Concurrent MCP requests from separate projects each use their own selection, even if a collection update runs at the same time. A present but malformed definition or an unresolved collection reference produces an actionable result without widening scope. |
| Existing data | A developer explicitly previews and starts migration of local collections. `indexed storage migrate` journals a collection before its data moves, moves it, verifies the moved bytes when content verification is requested, and only then registers it and adds it to the committed definition. The journal is the rollback record: after a move, the old path is empty and `--rollback` restores it. Conflicts, interruption and repetition have explicit recovery paths. |
| Checkout differences | A shared local Files or Git collection preserves the indexed snapshot. Use Git provenance when available. A different checkout exposes a mismatch when opening evidence. Remote connectors keep their existing source identity and freshness behavior. |

**Acceptance.** Use two clones or worktrees at different revisions, a second project with an overlapping selection, and two concurrent MCP clients. Prove reuse of the same collection data, distinct scopes, and correct behavior for missing or renamed collections. Take one v1-engine and one v2-engine local collection through `indexed storage migrate --dry-run`, `--verify hash`, a real run, `--rollback` and a re-run after completion, and prove each run leaves exactly one copy on disk, one registry record and one `indexed.toml` entry. Kill a run between the move and registration, resume it, and prove the same outcome with no duplicate and no lost collection. Record the verification mode in the evidence.

`indexed storage migrate` moves local collections into the global store and keeps no copy. The separate `indexed index migrate` converts one collection from the v1 to the v2 engine, keeping the original as `<name>.v1-backup`.

The feature design settles how CLI, MCP and LSP supply the workspace, how requests behave without a profile, and how to present migration and rollback.

- **Delivered on `main` since v0.0.11.** One global store with a stable-id registry, a committed `indexed.toml` selection resolved by CLI, LSP and MCP, and `indexed storage migrate` with `--dry-run`, `--rollback`, resume and `--verify structural|hash` (#363, #372, #373).
