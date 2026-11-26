---
type: feature-product
feature: workspace-selection
sibling: tech.md
parent: ../../product.md
updated: 2026-11-22
---

# Feature: Workspace Selection — Product

**Parent:** issue [#344](https://github.com/LennardZuendorf/indexed/issues/344) ·
milestone [#229](https://github.com/LennardZuendorf/indexed/issues/229) ·
spine: [#346](https://github.com/LennardZuendorf/indexed/issues/346).

## Problem

The registry gave a collection a stable id and let one workspace point at the
shared store, but the pointer is a **hidden directory** (`./.indexed/`) that a
repository cannot meaningfully review, commit or diff. The milestone's goal is
the opposite: one store at `~/.indexed/data/`, and a small **committed file** in
each repository saying which collections its commands search. Without that file
a repo either sees every collection in the store or needs its own copy — the
sprawl the global store exists to remove.

## Outcome

A repository carries one committed `indexed.toml` at its worktree root. It is a
*selection*: it names collections that already exist in the global store and
nothing else. CLI and LSP resolve it the same way, so two clones of the same
repository search the same collections without any per-clone setup.

## Requirements

- **R1 — The definition is portable.** Two independent clones (or two worktrees)
  of the same repository resolve the identical collection selection. Nothing in
  the file is path-dependent, machine-dependent or credential-bearing.
- **R2 — It is a selection, never a store.** The file carries collection
  references only. No collection data, no absolute paths, no provider keys, no
  per-repo cache. Removing it changes *scope* and nothing else.
- **R3 — Resolution fails closed and loud.** A malformed file, an unsupported
  version, or a reference that no longer resolves is an error naming the file,
  the offending entry and the remedy. It never silently widens to the whole
  store, and it never silently narrows to nothing.
- **R4 — Absence means no scope.** A directory with no definition behaves
  exactly as before: every collection in the resolved store is searched. A
  user who never writes the file loses nothing.
- **R5 — An explicit collection wins and says so.** `--collection NAME` for a
  collection outside the selection still runs (this is a default scope, not an
  access boundary — see #229's non-goal) and prints one warning line, so the
  wider scope is never silent.

## Non-goals

- **Per-repo settings overrides.** `[search]`/engine overrides in the definition
  are deliberately out of this slice: they must interact with `ConfigService`'s
  precedence chain, which is a separate, riskier change. The format reserves room
  (`version` gate) so adding a section later is not a breaking edit.
- **Per-request MCP scope.** A running MCP server still resolved one workspace
  from its process CWD in this feature; which workspace each request belongs to
  is [#345](https://github.com/LennardZuendorf/indexed/issues/345), shipped as
  [mcp-request-scope](../mcp-request-scope/product.md), which reads the
  `CliContext.selection` this feature puts in place.
- **A command editing the definition.** `index create` never rewrites
  `indexed.toml`: a committed file is the repository's, not a command's. The
  collection lands in the global store and the command warns that it is outside
  the repository's scope until the definition lists it.
- **Credential relocation.** `.env` stays where it is; the definition adds no
  second path to secrets.
