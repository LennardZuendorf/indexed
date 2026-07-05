---
type: lessons
updated: 2026-07-05
---

# Lessons Learned

Accumulated mistakes and earned defaults. Read at session start.

---

## Architecture audit (2026-07-03)

- **Graph before polish.** Fix `core→connectors` and extract `indexed-protocols`
  before refactoring services or splitting command files. v2 depends on this.
- **App is the composition root.** Config registration, logging, connector wiring
  belong in `bootstrap.py` + `runtime.py`, never at library import time.
- **`resolve_collections_context()` is the only storage API.** Do not revive
  heuristics like “prefer local if non-empty collections dir”.
- **Singleton `mode_override` must rebuild.** `ConfigService.instance()` recreates
  when `mode_override` changes on a subsequent call; use `reset=True` in tests.
- **Migrate before delete.** Jira Server must use `UnifiedJiraDocumentReader`
  before removing deprecated wrapper modules in `/8`.
- **Registry lookup uses `cfg.type` verbatim.** Do not normalize `jiraCloud` → `jira`
  when resolving connector class — cloud and server connectors differ.
- **`localFiles` sets `sources.files.path`, not `.url`.** in `build_connector()`.
- **Lazy imports after `/5`.** Config classes live in `connectors.*.schema`; package
  `__init__.py` no longer re-exports them — update `create.py` `__getattr__` paths.
- **Empty dict is falsy for registry injection.** `build_connector(..., registry={})`
  falls back to full registry — pass a partial dict with a dummy entry to test unknown types.

---

## Audit remediation (2026-07-05)

- **Verify a gate actually runs.** The documented `uv run mypy src/` never
  executed (no root `src/`), so a branch's mypy debt shipped unguarded — including
  2 real bugs. Gate is `uv run mypy apps/indexed/src packages/*/src`; scope success
  to **0-new on touched files**, never tree-wide green (mypy isn't strict; ~230
  pre-existing untyped-def errors). Baseline the count before editing.
- **One `missing_wiring_error(component)` for DI gaps** (`indexed_config.errors`) →
  `"<component> must be injected by the app layer; see indexed.bootstrap"`. Never
  hand-roll the string; it was copied across 4 core sites + a dead app copy.
- **Factory type aliases live in leaf `factories/_types.py`** (imports only
  `DiskPersister` + protocols — downward). In `services/models` they'd re-introduce
  a services↔factories cycle. Real reader/converter element types (not `Any`)
  cleared 15 mypy errors for free.
- **Keep `update_collection_factory` lazy in `_update_one`.** `collection_service`
  ← `create_collection_factory` ← `documents_collection_creator` ← `services/__init__`
  is a cold-import cycle; hoisting the factory to module load re-enters it. "Trim
  the stale comment" meant fix the comment, keep the lazy import.
- **A public API whose only callers are its mocks is dead.** `core.v1.Index.update()`
  raised on every real call (DI made its factories required, never injected); its
  one prod caller discarded the result. Removed from `__all__`.
- **Assert behaviour, not existence.** `__name__ == 'X'`, `hasattr`, `assert x is
  not None`, `assert mock.set.called`, CWD-relative paths prove nothing. Use `is`,
  `isinstance` vs `@runtime_checkable` protocols, `assert_called_once_with`, and
  anchor test roots to `Path(__file__).resolve().parents[N]` + a zero-files guard.
- **A CI guardrail needs a negative test.** The import-graph gate's `FORBIDDEN`
  omitted `indexed` (so `core→indexed` passed silently) and `_package_for_path`
  ignored its `root` (inert under fixtures). Test that a synthetic bad edge IS caught.

---

## General (from AGENTS.md)

- Lazy-load heavy ML imports inside functions, never at module top level.
- Coverage is measured on installed packages — run `uv run pytest -q --cov=src`
  from project root.
- Spec drift is the main failure mode — update `.spec/` in the same cycle as code.
