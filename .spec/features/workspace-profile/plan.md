---
type: feature-plan
feature: workspace-profile
sibling: tech.md
parent: ../../plan.md
updated: 2026-07-20
---

# Feature: Workspace Profile — Implementation Plan

Delivers the single-global-store + workspace-profile model in five units, bottom-up:
config foundation first (it's the dependency for everything), then core filtering,
then CLI, then MCP, then the docs/spec COMPOUND. Each unit is independently
testable and leaves the suite green.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Standalone cleanup on surviving infra; no upstream feature gate.
Runs on branch `claude/global-local-storage-workspace-h9sb7z`.

> **Layout note.** Paths target the single package `src/indexed/` (post-Simplify /
> Feature 14). Verification uses the current gate — `uv run ty check src/indexed`
> (not mypy), `uv run pytest ... --cov=src/indexed`, and `python scripts/check_imports.py`
> for the four module edges.

---

## Problem Frame

The local/global storage axis conflates "where bytes live" (should be global) with
"which collections are relevant here" (a per-codebase filter). We remove the storage
axis entirely and rebuild the local concept as a thin, committable profile. The
`config` module is the foundation — every other layer reads paths and filters through
it — so it lands first and the rest stack on top.

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Single global store](product.md#requirement-single-global-store) | workspace-profile/1, workspace-profile/3 |
| R2 | [Collection filter](product.md#requirement-collection-filter) | workspace-profile/2, workspace-profile/3, workspace-profile/4 |
| R3 | [Settings override](product.md#requirement-settings-override) | workspace-profile/1, workspace-profile/3 |
| R4 | [Profile management from the CLI](product.md#requirement-profile-management-from-the-cli) | workspace-profile/3 |

---

## Key Technical Decisions

1. **Bottom-up sequencing.** The `config` module first — its public API change (drop
   `mode_override`, `StorageResolver`, `resolve_storage_mode`) breaks downstream
   importers in `cli`/`mcp`, so it must land and re-green before core/CLI/MCP build on
   it. `config` stays a leaf (module-edge gate green).
2. **Allowlist over path-switching.** Filtering is an `allowed_collection_ids`
   parameter on read services, not a second storage path. `None` = no filter keeps
   the no-profile path behaviour-identical.
3. **Overlay merge replaces single-source.** `[workspace.overrides]` deep-merges on
   global; this is the one config-principle reversal and is documented in COMPOUND.
4. **Clean break (alpha).** No migration of old `./.indexed/data/` collections; the
   `indexed migrate` legacy mover is untouched (different concern).

---

## Unit IDs

Units are `workspace-profile/n`, assigned once and never renumbered.

---

### workspace-profile/1 — Config foundation: global-only storage + WorkspaceProfile

**Goal:** The `config` module exposes one global store and a `WorkspaceProfile`
(filter + overlay merge); all storage-mode machinery removed.

**Requirements:** R1, R3

**Dependencies:** —

**Files:**

```
src/indexed/config/storage.py    # strip mode/local/resolver
src/indexed/config/workspace.py  # WorkspaceManager → WorkspaceProfile
src/indexed/config/store.py      # overlay merge; schema "2"
src/indexed/config/service.py    # drop mode_override; add profile accessors
src/indexed/config/__init__.py   # trim exports
src/indexed/config/errors.py     # drop StorageConflictError
tests/unit/indexed/config/*      # rewrite storage/service/store/workspace tests
```

**Test scenarios:**

- Global config + profile overrides deep-merge; env var still wins (R3 scenarios).
- `WorkspaceProfile.collection_ids()` returns declared ids, `None` when no file.
- No storage-mode symbols remain importable; `ConfigService.instance()` takes no `mode_override`.

**Verification:** `uv run pytest tests/unit/indexed/config -q` green; `uv run ty check src/indexed` 0 diagnostics; `python scripts/check_imports.py` green.

---

### workspace-profile/2 — Core: collection-id allowlist on search/inspect

**Goal:** `SearchService` and `InspectService` (+ functional wrappers) accept
`allowed_collection_ids`; default path helpers always return global.

**Requirements:** R2

**Dependencies:** workspace-profile/1

**Files:**

```
src/indexed/core/v1/config_models.py                  # global-only paths
src/indexed/core/v1/engine/services/search_service.py # allowlist filter
src/indexed/core/v1/engine/services/inspect_service.py# allowlist filter
tests/unit/indexed/core/services/*                    # filter tests
```

**Test scenarios:**

- `search(..., allowed_collection_ids=["a"])` over collections `a`,`b` searches only `a`.
- `allowed_collection_ids=None` searches all (no behaviour change).
- Empty allowlist yields no results / empty status.

**Verification:** `uv run pytest tests/unit/indexed/core/services -q` green; `uv run ty check src/indexed` clean.

---

### workspace-profile/3 — CLI: remove storage mode, wire the profile

**Goal:** Drop `--local`/`--global` and the mode banner; search/inspect apply the
profile filter; `create` writes global; `update`/`remove` warn out-of-scope;
`config` scaffolds the profile; `config inspect` shows it.

**Requirements:** R1, R2, R4

**Dependencies:** workspace-profile/1, workspace-profile/2

**Files:**

```
src/indexed/cli/app.py, composition.py
src/indexed/cli/init.py                           # drop storage-mode banner
src/indexed/cli/knowledge/commands/create.py, _create_helpers.py, _create_options.py
src/indexed/cli/knowledge/commands/search.py, inspect.py, update.py, remove.py
src/indexed/config/cli.py, config/commands/       # profile scaffold + inspect
src/indexed/cli/utils/storage_info.py             # delete → thin scope note
src/indexed/cli/utils/conflict_prompt.py          # delete
tests/unit/indexed/test_app.py, test_init_command.py
tests/unit/indexed/knowledge/commands/*, tests/unit/indexed/cli/utils/*, tests/unit/indexed/utils/test_storage_info.py
tests/unit/indexed/config/test_cli.py
```

**Test scenarios:**

- `--local` is unknown (R1); create lands in `~/.indexed/` regardless of cwd.
- Search with a profile is scoped; without a profile, unscoped (R2 scenarios).
- Profile scaffold writes a `[workspace]` skeleton; `update notes` warns when out of scope (R4).

**Verification:** `uv run pytest tests/unit/indexed -q` green; `uv run indexed index search` manual smoke; `uv run ty check src/indexed` clean; `python scripts/check_imports.py` green.

---

### workspace-profile/4 — MCP: thread the filter through lifespan

**Goal:** MCP server loads the collection filter into lifespan context; tools and
resources scope to it and reject out-of-scope named access.

**Requirements:** R2

**Dependencies:** workspace-profile/1, workspace-profile/2

**Files:**

```
src/indexed/mcp/server.py     # lifespan: load allowlist
src/indexed/mcp/tools.py      # pass allowlist; validate access
src/indexed/mcp/resources.py  # pass allowlist; validate access
tests/unit/indexed/mcp/*      # MCP scope tests
tests/system/test_mcp_storage_parity.py  # storage-parity regression
```

**Test scenarios:**

- list_collections / search via MCP return only profile collections.
- Naming an out-of-scope collection returns an access error.

**Verification:** `uv run pytest tests/unit/indexed/mcp tests/system/test_mcp_storage_parity.py -q` green; `uv run ty check src/indexed` clean.

---

### workspace-profile/5 — COMPOUND: specs + docs reflect the new model

**Goal:** Specs, AGENTS/CLAUDE files, and READMEs describe one global store + the
workspace profile; promote the two `<!-- merge -->` blocks from tech.md.

**Requirements:** R1, R2, R3, R4

**Dependencies:** workspace-profile/1–4

**Files:**

```
.spec/tech-config.md, .spec/tech-app.md, .spec/tech.md, .spec/product.md
.spec/plan.md                                   # Feature Sequence row (Feature 16)
CLAUDE.md / AGENTS.md (root; single package — symlinked), README.md
.spec/lessons.md                                # record the single-source→overlay reversal
```

**Test scenarios:**

- `bash .agents/skills/spec/scripts/validate.sh` → 0 errors.
- No remaining doc references to `--local`/storage mode resolution.

**Verification:** validate.sh clean; grep shows no stale `mode_override`/`--local` in specs/docs.

---

## Dependencies

| Unit | Blocks | Blocked by |
|---|---|---|
| workspace-profile/1 | /2, /3, /4 | — |
| workspace-profile/2 | /3, /4 | /1 |
| workspace-profile/3 | /5 | /1, /2 |
| workspace-profile/4 | /5 | /1, /2 |
| workspace-profile/5 | — | /1, /2, /3, /4 |

---

## Progress

| Unit | Status |
|---|---|
| workspace-profile/1 | NOT STARTED |
| workspace-profile/2 | NOT STARTED |
| workspace-profile/3 | NOT STARTED |
| workspace-profile/4 | NOT STARTED |
| workspace-profile/5 | NOT STARTED |

---

## Open Questions

1. **Out-of-scope named ops: warn vs block?** — Plan assumes warn-and-proceed
   (product Open Question 1). If we switch to block, it lands in /3 and /4.
