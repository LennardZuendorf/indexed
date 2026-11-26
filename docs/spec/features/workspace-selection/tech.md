---
type: feature-tech
feature: workspace-selection
sibling: product.md
parent: ../../tech.md
updated: 2026-11-26
---

# Feature: Workspace Selection — Tech

**Sibling:** [product.md](product.md) · **Plan:** [plan.md](plan.md) ·
issue [#344](https://github.com/LennardZuendorf/indexed/issues/344).

## The file

```toml
# indexed.toml — commit this file. It selects collections that already live in
# the global store (~/.indexed/data). It never contains collection data.
version = 1

[collections]
use = ["indexed-docs", "8b1d2f5e6a7c4b9d0e3f2a1c8d7b6e5f"]
```

- `version` (int, required) — format version. Anything but `1` is a loud error;
  a missing `version` is a loud error rather than an assumed default, because an
  unversioned definition cannot be migrated later.
- `[collections].use` (array of strings, required) — ordered references. An
  entry of exactly 32 lowercase hex characters is a **stable id**; anything else
  is a **collection name**. Ids win over names, and ids are the canonical form
  (`indexed storage migrate` writes ids). Names exist so the file is
  hand-authorable: the user knows `indexed-docs`, not its uuid.
- Duplicate entries (same resolved collection) are an error — a selection is a
  set and a repeated entry is a typo, not intent.

Nothing else is read. Unknown keys are ignored so a newer indexed's file does
not break an older one.

## Discovery

`find_definition(workspace)` walks from the workspace directory upwards and
returns the first `indexed.toml` it finds, stopping **before** `$HOME` (a
definition must belong to a repository, not to the user's home directory). No
file found ⇒ `None` ⇒ no scope, today's behaviour (R4).

`find_git_root(workspace)` walks up to the first directory containing a `.git`
entry (a directory, or a *file* — inside a linked worktree `.git` is a file).
It answers a different question — *where the definition belongs* — and is used by
`indexed storage migrate` to write the file, not by resolution. A workspace
outside Git has no portable home for a definition, so `storage migrate` refuses
it with `MigrationError` naming the remedy rather than writing `indexed.toml`
somewhere a second clone would never look.

## Resolution and precedence

`resolve_collections_context` (`cli/composition.py`) is the single storage
resolver for CLI, LSP and MCP, so the definition is honoured once, there:

| Order | Source | Store used | Selection |
|---|---|---|---|
| 1 | `indexed.toml` found from the workspace | always the **global** root | its entries |
| 2 | legacy `./.indexed/collections.json` (deprecated) | the pointer's root | none (unfiltered) |
| 3 | storage mode (`--local` or global) | resolved mode root | none |

A definition always means the global store: the milestone's whole point is that
no repository owns a collection directory. It pins the **whole** store, so
`caches_path` is the global one too — mixing global collections with local
document caches would look for cache entries the store never wrote. `--local`
alongside a definition is therefore ignored, and one warning line says so;
silently overriding an explicit flag would be worse than the noise. The warning
fires only for an explicit `--local` flag, never for a local mode that came from
a saved preference or auto-detection, so a local workspace is not noisy.

Notices are **data on `CliContext.warnings`**, not prints: the resolver runs
twice per human search (`search` itself, then
`display_storage_mode_for_command`) and `indexed lsp` must never write to
stdout. Each command that owns an output stream decides where the line goes:
`print_info` on the console in human mode, `typer.echo(..., err=True)` under
`--json`/`--simple-output`, and `loguru` for the language server (stderr).

## Fail-closed rules (R3)

`WorkspaceSelectionError` (a `StorageError`) for each of:

- file unreadable, not valid TOML, or not a table;
- `version` missing or not `1`;
- `[collections].use` missing, empty, or not a list of non-empty strings;
- an entry that resolves to no registry record (deleted, or never registered);
- two entries resolving to the same collection;
- a resolved collection whose data directory is absent from the store
  (registered but moved or deleted).

Every message names the definition file, the offending entry, and the remedy
(`indexed collection list` for the store's real names and ids). Errors propagate:
there is no fallback to an unfiltered store and no fallback to an empty result.

## Where the selection is applied

- `CliContext` gains `workspace: Path`, `selection: WorkspaceSelection | None`
  and `warnings: tuple[str, ...]`. The selection carries resolved
  `(id, name)` pairs plus the definition's path and root.
- `indexed search` with no `--collection` filters the store's collections by the
  selection (R1/R2 take effect here), in definition order. A selected collection
  the store no longer serves is named in the payload's `sources` (status
  `missing`), with the other selected sources still answering — see
  [project-search](../project-search/tech.md). Resolution itself still fails
  closed: `load_selection(strict=True)` (LSP, storage) raises for such an entry,
  and a malformed definition raises on every path.
- `indexed search --collection NAME` outside the selection warns and proceeds
  (R5).
- `indexed index create` does **not** edit the definition (a committed file is
  not a command's to rewrite). The collection lands in the global store, so the
  command warns that the new collection is not yet in the repository's scope.
- `KnowledgeBackend` (`indexed.lsp`) takes `selected_names` and filters
  `statuses()`, so `workspace/symbol`, hover and diagnostics see the same scope
  as the CLI.
- `indexed storage migrate` writes the definition at the worktree root instead
  of the pointer, and `--rollback` removes the entry it added (deleting the file
  when that entry was the only one).

## Migration off the pointer (#346 → this feature)

`indexed storage migrate` journals the definition root (`journal["definition"]`)
beside its steps, so a resumed run selects the collection in the same file the
first attempt created, and a step is idempotent: re-adding an id already listed
returns the file unchanged. `--rollback` reverses the definition entry and, for
a workspace migrated under #346, deletes the legacy pointer — leaving it would
keep routing that workspace at a store that no longer holds the collection.

## Legacy pointer: read-only, deprecated

`.indexed/collections.json` keeps its reader and loses its writer. Reason: it
shipped with the registry and it is the *only* thing routing an already-migrated
workspace at the shared store; dropping the reader would make those collections
unreachable rather than migrated. A workspace still relying on it gets one
warning line naming `indexed.toml`, and the pointer is documented as removed in
the next minor. It is never written again.

## Module boundaries

`config/workspace_selection.py` is the `config` layer: it reads TOML and the
registry, and imports neither `core` nor `cli`. It is consumed by
`cli/composition.py` and `cli/storage/commands/_migration.py`; nothing in
`core`/`connectors` imports it.
