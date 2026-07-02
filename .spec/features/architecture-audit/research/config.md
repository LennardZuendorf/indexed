---
type: feature-research
feature: architecture-audit
cluster: config
parent: ../product.md
updated: 2026-06-29
---

# Research: indexed-config

Discovery artifact from the 2026-06-29 monorepo architecture audit. Covers
`packages/indexed-config/` (~1,634 LOC, 10 modules, 10 test files).

**Related:** [product.md](../product.md) R4 (single-source config), R5 (explicit
bootstrap). [tech-config.md](../../../tech-config.md) § Single-Source Config Resolution.

---

## Summary

`indexed-config` is **surviving infra** and ~75% v2-ready. The product model
(local-first, single `config.toml`, `.env` hierarchy, schema versioning) is
correct and well-tested. The package is mid-migration: `load_raw()` and
`read_for_mode()` implement the spec, but legacy merge paths, a singleton that
ignores `mode_override` after first use, and triple mode resolution across
modules keep behavior inconsistent with `.spec/tech-config.md`. Shape is heavier
than needed — a dict-wrapper registry and ~300 LOC of merge/conflict code serve
behavior the spec abandoned.

---

## Findings

| # | Finding | Priority | Path(s) |
|---|---------|----------|---------|
| 1 | `TomlStore.read()` still merges global + local TOML when no `mode_override` | **P1** | `store.py:140–172` |
| 2 | `load_raw()` / `read_for_mode()` are spec-correct (single source) | OK | `store.py:174–199` |
| 3 | `ConfigService.instance()` ignores `mode_override` after first call | **P1** | `service.py:64–74` |
| 4 | CLI `--local` on `ctx.obj` not wired to most commands (downstream of singleton) | **P0** | `apps/indexed/` (see [app.md](app.md)) |
| 5 | Triple mode resolution — same rules in three places | **P1** | `workspace.py`, `storage.py` (`StorageResolver`), `store.py:write()` |
| 6 | `ConfigRegistry` is a thin dict wrapper (YAGNI) | **P2** | `registry.py` |
| 7 | Duplicate test suites for same behavior | **P2** | `tests/unit/indexed_config/test_service.py`, `test_config_service.py` |
| 8 | `migrate.py` stub-only — schema versioning exists but no migration path | **P2** | `store.py` (`CURRENT_SCHEMA_VERSION`) |
| 9 | `provider.py` + `path_utils.py` overlap with `storage.py` / `store.py` | **P2** | Multiple modules |
| 10 | `IndexedError` hierarchy defined but unused at app/connector boundaries | **P1** | `errors.py` (cross-cutting) |

---

## Refactoring Proposals

### P1 — Unify read path (architecture-audit/6)

1. Route **all** config reads through `WorkspaceManager.resolve_storage_mode()` →
   `TomlStore.read_for_mode(mode)`.
2. Deprecate `TomlStore.read()` merge path; migrate callers (`workspace.get_config()`,
   `storage_info.py`, CLI private `_store._read_toml_file` access).
3. Delete merge/conflict detection code and associated tests once callers migrate.

### P1 — Fix singleton semantics (architecture-audit/6)

1. Replace `ConfigService.instance(mode_override=…)` with
   `ConfigService.for_context(workspace, mode_override)` per command invocation.
2. App callback creates context once from `ctx.obj["local"]` / `--global`; pass
   down to services — never reuse a global singleton across mode changes.
3. Keep `reset=True` only for tests.

### P1 — Consolidate mode resolution

1. **Single resolver:** `storage.py` owns `resolve_storage_mode()` (merge logic
   from `WorkspaceManager` and `StorageResolver`).
2. `TomlStore.write()` delegates mode to resolver — no inline re-implementation.
3. Document resolution order once in `tech-config.md`; code references one function.

### P2 — Target 3-module collapse

| Target module | Absorbs |
|---------------|---------|
| `service.py` | Registry inline (drop `registry.py` wrapper); orchestration only |
| `store.py` | `read_for_mode()` only; env overlay; schema versioning |
| `storage.py` | Mode resolver, path layout, `ensure_storage_dirs()`, `.gitignore` guard |

Retire or fold: `provider.py`, `path_utils.py` (if redundant), merge-specific helpers.

### P2 — Test consolidation

Merge `test_service.py` + `test_config_service.py` into one module mirroring
`service.py`. Add characterization tests for `read_for_mode()` as the sole read API.

### v2 — Namespace registration

Add `core.v2.*` registration path via app `bootstrap.py`; keep `core.v1.*` until
v1 retirement. Implement `migrate.py` when first schema bump ships.

---

## Delete / Merge / Keep / Defer

| Component | Path(s) | Action | Rationale | When |
|-----------|---------|--------|-----------|------|
| `TomlStore.read()` merge path | `store.py:140–172` | **DELETE** | Contradicts single-source spec | Phase 1 (architecture-audit/6) |
| Merge/conflict detection | `store.py`, related tests | **DELETE** | ~300 LOC for abandoned behavior | After caller migration |
| `ConfigRegistry` dict wrapper | `registry.py` | **MERGE → service.py** | YAGNI; inline typed dict suffices | Phase 1 |
| `provider.py` / `path_utils.py` | `indexed_config/` | **MERGE → storage.py** | Overlap with storage layout owner | Phase 1–2 |
| Duplicate test suites | `test_service.py`, `test_config_service.py` | **MERGE** | Same behavior, double maintenance | Quick win |
| `ConfigService` singleton | `service.py` | **MERGE → context factory** | `for_context()` per command | Phase 1 |
| `read_for_mode()` | `store.py` | **KEEP** | Spec-correct read API | — |
| `WorkspaceManager` / `StorageResolver` | `workspace.py`, `storage.py` | **MERGE → one resolver** | Triple mode resolution | Phase 1 |
| `EnvFileWriter` | `env_writer.py` | **KEEP** | Secrets → `.env` routing works | — |
| `IndexedError` hierarchy | `errors.py` | **KEEP** | Foundation for R6; wire at boundaries | Phase 2 |
| Schema versioning (`_meta`) | `store.py` | **KEEP** | Migration path for v2 namespaces | — |
| `migrate.py` implementation | (new) | **DEFER** | Stub until first breaking schema change | v2 kickoff |
| `core.v2.*` config namespaces | registration | **DEFER** | Add when v2 feature spec starts | Phase 2 |

---

## Essential Files

- `service.py` — orchestrator (target: context factory, inline registry)
- `store.py` — TOML I/O, `read_for_mode()`, schema versioning
- `storage.py` — storage dirs, mode resolver (target: sole resolver)
- `workspace.py` — merge into storage resolver
- `env_writer.py` — secret routing
- `errors.py` — `IndexedError` base hierarchy
- `models.py` — Pydantic validation (if present at package root)
