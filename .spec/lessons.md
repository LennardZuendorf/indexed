---
type: lessons
updated: 2026-07-03
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
- **Singleton `ConfigService.instance()` ignores later `mode_override`.** Pass
  `mode_override` on first call or use `for_context()` per command invocation.
- **Migrate before delete.** Jira Server must use `UnifiedJiraDocumentReader`
  before removing deprecated wrapper modules in `/8`.

---

## General (from AGENTS.md)

- Lazy-load heavy ML imports inside functions, never at module top level.
- Coverage is measured on installed packages — run `uv run pytest -q --cov=src`
  from project root.
- Spec drift is the main failure mode — update `.spec/` in the same cycle as code.
