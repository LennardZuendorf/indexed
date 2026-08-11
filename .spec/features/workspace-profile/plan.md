---
type: feature-plan
feature: workspace-profile
sibling: tech.md
parent: ../../plan.md
updated: 2026-08-11
---

# Feature: Workspace Profile — Implementation Plan

Delivers the single-global-store + workspace-profile model in six units, bottom-up: config
foundation first (it is the dependency for everything), then core filtering, then the two CLI
units, then MCP, then the docs/spec COMPOUND. Each unit is independently testable and leaves
the suite green.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Standalone cleanup on surviving infra; no upstream feature gate.

> **Layout note.** Paths target the single package `src/indexed/` (post-Simplify /
> Feature 14). Verification uses the current gate — `uv run ty check src/indexed` (not mypy),
> `uv run pytest ... --cov=src/indexed`, and `python scripts/check_imports.py` for the four
> module edges.

---

## Problem Frame

The local/global storage axis conflates "where bytes live" (should be global) with "which
collections are relevant here" (a per-codebase filter). We remove the storage axis entirely
and rebuild the local concept as a thin, committable profile at the workspace root.

The agent-facing half is the harder half: an MCP server has no inherent notion of the
caller's workspace, and the MCP protocol removed sessions in revision `2026-07-28`, so the
answer has to be resolved per request rather than pinned at startup. The `config` module is
the foundation for both halves — every other layer reads paths, filters, and overrides
through it — so it lands first and the rest stack on top.

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Single global store](product.md#requirement-single-global-store-r1) | workspace-profile/1, workspace-profile/3 |
| R2 | [Workspace profile discovery](product.md#requirement-workspace-profile-discovery-r2) | workspace-profile/1 |
| R3 | [Collection filter](product.md#requirement-collection-filter-r3) | workspace-profile/2, workspace-profile/3, workspace-profile/5 |
| R4 | [Settings override](product.md#requirement-settings-override-r4) | workspace-profile/1, workspace-profile/3 |
| R5 | [Profile lifecycle from the CLI](product.md#requirement-profile-lifecycle-from-the-cli-r5) | workspace-profile/4 |
| R6 | [MCP workspace handover](product.md#requirement-mcp-workspace-handover-r6) | workspace-profile/5 |
| R7 | [Config schema version 2](product.md#requirement-config-schema-version-2-r7) | workspace-profile/1 |

---

## Key Technical Decisions

1. **Bottom-up sequencing.** The `config` module first — its public API change (drop
   `mode_override`, `StorageResolver`, `resolve_storage_mode`) breaks downstream importers in
   `cli`/`mcp`, so it must land and re-green before the rest build on it. `config` stays a
   leaf (module-edge gate green).
2. **Allowlist over path-switching.** Filtering is an `allowed_collection_ids` parameter on
   read services, not a second storage path. `None` = no filter keeps the no-profile path
   behaviour-identical. Appended **keyword-only** — the existing module wrappers take
   positional parameters.
3. **Overlay merge replaces single-source.** `[workspace.overrides]` deep-merges on global;
   this is the one config-principle reversal and is recorded in COMPOUND.
4. **Scope is an immutable value, not singleton state.** `WorkspaceScope` is resolved per CLI
   invocation and per MCP request and passed down. `ConfigService.set_overlay()` is
   process-global mutable state and would race between concurrent MCP requests for different
   workspaces.
5. **Per-request MCP resolution, fail closed.** No lifespan-pinned workspace (MCP dropped
   sessions in `2026-07-28`); an unresolvable explicit workspace or an unparseable profile
   raises rather than falling back to an unfiltered global view.
6. **Roots is a guarded probe, not the primary path.** Deprecated as of `2026-07-28`, absent
   from most clients, and it returns a list with no "primary" — but it is the only channel
   tracking a workspace that changes mid-session, so it sits at chain position 3 behind a
   capability check, a `try/except`, and a cache.
7. **Clean break (alpha), with a legible error.** No migration of old `./.indexed/data/`
   collections; `schema_version = "2"` enforcement turns an old config into a named error
   instead of a mystery. The `indexed migrate` legacy mover is untouched (different concern).

---

## Unit IDs

Units are `workspace-profile/n`, assigned once and never renumbered.

---

### workspace-profile/1 — Config foundation: global store, profile discovery, scope

**Goal:** The `config` module exposes one global store, discovers the workspace profile by
upward search, and resolves an immutable `WorkspaceScope` (filter + overlay). All
storage-mode machinery removed; `schema_version = "2"` enforced.

**Requirements:** R1, R2, R4, R7

**Dependencies:** —

**Files:**

```
src/indexed/config/storage.py    # strip mode/local/resolver
src/indexed/config/discovery.py  # NEW upward search (canonical + legacy, $HOME bound)
src/indexed/config/workspace.py  # WorkspaceManager → WorkspaceProfile + WorkspaceScope + cache
src/indexed/config/store.py      # global base only; schema "2" enforcement
src/indexed/config/service.py    # drop mode_override; narrow get_config()
src/indexed/config/__init__.py   # trim exports
src/indexed/config/errors.py     # drop StorageConflictError; add SchemaVersionError,
                                 #   WorkspaceResolutionError
tests/unit/indexed/config/*      # rewrite storage/service/store/workspace tests
```

**Test scenarios:**

- Discovery from a subdirectory finds the parent's `indexed.config.toml`; the walk stops at `$HOME`.
- Legacy `.indexed/config.toml` resolves with a deprecation notice; both forms in one dir → canonical wins + warning.
- `~/.indexed/config.toml` is never adopted as a profile when the walk reaches `$HOME`.
- Global config + profile overrides deep-merge; env var still wins (R4 scenarios).
- `WorkspaceScope.apply()` is pure — it mutates neither the singleton nor its input.
- Schema `"1"` + `[workspace].mode` → `SchemaVersionError` naming the key; clean `"1"` loads; unknown version raises.
- No storage-mode symbols remain importable; `get_config()` takes no `mode_override`.

**Verification:** `uv run pytest tests/unit/indexed/config -q` green; `uv run ty check src/indexed` 0 diagnostics; `python scripts/check_imports.py` green.

---

### workspace-profile/2 — Core: collection-id allowlist on search/inspect

**Goal:** `SearchService` and `InspectService` (+ functional wrappers) accept
`allowed_collection_ids`; default path helpers always return global.

**Requirements:** R3

**Dependencies:** workspace-profile/1

**Files:**

```
src/indexed/core/v1/config_models.py                   # global-only paths
src/indexed/core/v1/engine/services/search_service.py  # allowlist filter
src/indexed/core/v1/engine/services/inspect_service.py # allowlist filter; workspace-anchored
                                                       #   relative_path (was os.getcwd())
tests/unit/indexed/core/services/*                     # filter tests
```

**Test scenarios:**

- `search(..., allowed_collection_ids=["a"])` over collections `a`,`b` searches only `a`.
- `allowed_collection_ids=None` searches all (no behaviour change).
- Empty allowlist yields no results / empty status.
- A declared id with no collection on disk warns and is skipped, not raised.
- Existing positional wrapper calls keep their meaning — a positional call with the old
  argument count binds exactly as before.

**Verification:** `uv run pytest tests/unit/indexed/core/services -q` green; `uv run ty check src/indexed` clean.

---

### workspace-profile/3 — CLI: remove storage mode, wire the scope

**Goal:** Drop `--local`/`--global` and the mode banner; search/inspect apply the scope filter
and print a scope note; `create` writes global; composition builds one `WorkspaceScope` per
invocation.

**Requirements:** R1, R3, R4

**Dependencies:** workspace-profile/1, workspace-profile/2

**Files:**

```
src/indexed/cli/app.py, composition.py
src/indexed/cli/init.py                           # drop storage-mode banner
src/indexed/cli/knowledge/commands/create.py, _create_helpers.py, _create_options.py
src/indexed/cli/knowledge/commands/search.py, inspect.py
src/indexed/cli/utils/storage_info.py             # delete → thin scope note
src/indexed/cli/utils/conflict_prompt.py          # delete
tests/unit/indexed/test_app.py, test_init_command.py
tests/unit/indexed/knowledge/commands/*, tests/unit/indexed/cli/utils/*
```

**Test scenarios:**

- `--local` is unknown (R1); create lands in `~/.indexed/` regardless of cwd.
- Search with a profile is scoped and prints the scope note; without a profile, unscoped (R3 scenarios).
- A workspace override changes effective search config for that invocation only.

**Verification:** `uv run pytest tests/unit/indexed -q` green; `uv run indexed index search` manual smoke; `uv run ty check src/indexed` clean; `python scripts/check_imports.py` green.

---

### workspace-profile/4 — CLI: profile lifecycle

**Goal:** `config workspace init` scaffolds a profile; `create` appends its collection and
`remove` drops it (both atomic, `--no-profile` opts out); out-of-scope named operations warn
and proceed; `config inspect` shows the resolved scope.

**Requirements:** R5

**Dependencies:** workspace-profile/1, workspace-profile/3

**Files:**

```
src/indexed/config/cli.py, config/commands/       # workspace init + inspect shows scope
src/indexed/cli/knowledge/commands/create.py      # append entry; --no-profile
src/indexed/cli/knowledge/commands/remove.py      # drop entry
src/indexed/cli/knowledge/commands/update.py      # out-of-scope warning
tests/unit/indexed/config/test_cli.py
tests/unit/indexed/knowledge/commands/*
```

**Test scenarios:**

- Scaffold writes an `indexed.config.toml` `[workspace]` skeleton; `--force` overwrites, absence of it refuses.
- `create api` in a profiled workspace appends `[workspace.collections.api]` and a following unscoped search finds it.
- `create ... --no-profile` leaves the profile byte-identical.
- `remove api` drops the entry; removing a collection absent from the profile is a no-op.
- `update notes` out of scope warns and proceeds (R5 scenario).
- Profile writes are atomic and preserve unrelated keys, comments excepted.

**Verification:** `uv run pytest tests/unit/indexed -q` green; `uv run ty check src/indexed` clean.

---

### workspace-profile/5 — MCP: per-request workspace resolution

**Goal:** The MCP server resolves the workspace per request through the five-step chain,
scopes tools and resources to it, reports a `scope` block on every response, and fails closed.

**Requirements:** R6, R3

**Dependencies:** workspace-profile/1, workspace-profile/2

**Files:**

```
src/indexed/mcp/workspace.py  # NEW: resolution chain, roots probe, per-request cache
src/indexed/mcp/server.py     # lifespan holds env/cwd defaults only
src/indexed/mcp/tools.py      # `workspace` argument; allowlist; scope block
src/indexed/mcp/resources.py  # chain steps 2–5; scope block
src/indexed/mcp/config.py     # delete default_global_context()
tests/unit/indexed/mcp/*
tests/system/test_mcp_workspace_scope.py   # replaces test_mcp_storage_parity.py
```

**Test scenarios:**

- Explicit `workspace` argument scopes the search; `scope.source == "argument"`.
- Header path scopes under http and is ignored under stdio (`get_http_headers()` returns `{}`); lookup is lowercase.
- Roots probe: capability absent → skipped without raising; one root → used; several with profiles → error naming candidates.
- `INDEXED_WORKSPACE` then `CLAUDE_PROJECT_DIR` are consulted in that order; cwd is used under stdio only.
- Non-existent explicit workspace → error, **not** an unfiltered search.
- Unparseable profile → error naming the file, **not** an unfiltered search.
- No profile anywhere → unfiltered, `scope.source == "none"`.
- Out-of-scope named collection proceeds with the warning in `scope.warnings`.
- Two consecutive requests naming different workspaces get different scopes from one process.

**Verification:** `uv run pytest tests/unit/indexed/mcp tests/system/test_mcp_workspace_scope.py -q` green; `uv run ty check src/indexed` clean.

---

### workspace-profile/6 — COMPOUND: specs + docs reflect the new model

**Goal:** Specs, AGENTS/CLAUDE files, and READMEs describe one global store, the workspace
profile, and the MCP handover; promote the three `<!-- merge -->` blocks from tech.md.

**Requirements:** R1–R7

**Dependencies:** workspace-profile/1–5

**Files:**

```
.spec/tech-config.md, .spec/tech-app.md, .spec/tech.md, .spec/product.md
.spec/plan.md                                   # Feature Sequence row (Feature 16)
CLAUDE.md / AGENTS.md (root; symlinked), README.md   # incl. the .mcp.json handover recipes
.spec/lessons.md                                # single-source→overlay reversal; the
                                                #   INDEXED__workspace collision; roots deprecation
```

**Test scenarios:**

- `bash .agents/skills/spec/scripts/validate.sh` → 0 errors.
- No remaining doc references to `--local`/storage mode resolution.
- The documented `.mcp.json` snippets match the implemented env var and header names.

**Verification:** validate.sh clean; grep shows no stale `mode_override`/`--local` in specs/docs.

---

## Dependencies

| Unit | Blocks | Blocked by |
|---|---|---|
| workspace-profile/1 | /2, /3, /4, /5 | — |
| workspace-profile/2 | /3, /5 | /1 |
| workspace-profile/3 | /4, /6 | /1, /2 |
| workspace-profile/4 | /6 | /1, /3 |
| workspace-profile/5 | /6 | /1, /2 |
| workspace-profile/6 | — | /1–/5 |

---

## Progress

| Unit | Status |
|---|---|
| workspace-profile/1 | NOT STARTED |
| workspace-profile/2 | NOT STARTED |
| workspace-profile/3 | NOT STARTED |
| workspace-profile/4 | NOT STARTED |
| workspace-profile/5 | NOT STARTED |
| workspace-profile/6 | NOT STARTED |

---

## Open Questions

None. Out-of-scope named operations warn and proceed (CLI and MCP); per-collection overrides
apply at the CLI/MCP layer. The `x-mcp-header` convergence is a documented follow-up in
[tech.md](tech.md), deliberately deferred until the SDK speaks protocol `2026-07-28`.
