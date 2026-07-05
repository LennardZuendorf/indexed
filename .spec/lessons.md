---
type: lessons
scope: project
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

---

## `is_verbose_mode()` is unreliable at command-function top

**Context:** `create.py` connector commands hoisted the storage indicator to the top
of each function. The original check (`if not is_verbose_mode():`) always returned
`False` there because `setup_root_logger` (which sets the global log level) only runs
inside `execute_create_command`, later in the flow.

**Lesson:** At command-function top, check `verbose` and `log_level` params directly.
`is_verbose_mode()` is only reliable after `setup_root_logger` runs. Tests that mock
`is_verbose_mode` directly pass regardless of timing — they don't expose this bug.

**Fix pattern:** Extract one predicate over the params and reuse it for *every*
pre-setup gate — the storage indicator *and* the connector-heading guards — so they
stay consistent (an `--log-level=INFO` run must suppress both, or neither):
```python
def _is_pre_setup_verbose(verbose: bool, log_level: Optional[str]) -> bool:
    return verbose or (log_level or "").upper() in ("INFO", "DEBUG")

# indicator + `if not _is_pre_setup_verbose(verbose, log_level):` heading guards
```
Pre-setup `logger.info(...)` lines stay gated on `is_verbose_mode()` — they genuinely
cannot fire before `setup_root_logger`, so that check is correct, not a bug.

---

## Share credential-guard helpers, never duplicate them

**Context:** The origin guard block (`is_same_origin` + warning + `return None`) was
added identically to 3 separate reader methods. Any future change to the warning
string or return contract requires touching all three in sync.

**Lesson:** Extract a `warn_if_off_origin(url, base_url) -> bool` helper in the
shared module (`_url_guard.py`). Call sites reduce to a single-line guard:
```python
if not warn_if_off_origin(url, self.base_url):
    return None
```

---

## Loguru module-level import is fine; the lazy-import rule is ML-only

**Context:** Review flagged that loguru was imported at module level in some files
and lazily in others, questioning consistency.

**Lesson:** CLAUDE.md's lazy-import rule targets `sentence-transformers`/`torch` only
(500ms+ penalty). Loguru is a lightweight logger — module-level import is correct and
consistent with `apps/indexed` usage. Lazy-import loguru only inside isolated
connector methods where the import itself is fine either way (no performance cost).

---

## Jira Cloud attachment URLs are intentionally off-origin

**Context:** Applying the origin guard to `AsyncJiraCloudDocumentReader` silently
dropped all Cloud attachments. Jira Cloud serves `att["content"]` from
`api.media.atlassian.com` — off-origin relative to `*.atlassian.net` base URLs.

**Lesson:** When applying a credential-guard to a family of readers, audit each for
CDN/proxy patterns. Cloud APIs often serve content from off-origin CDNs; the threat
model there is different (URLs come from the API, not user-controlled). Exclude
deliberately and document why.

---

## Same-origin checks must compare port, not just scheme + host

**Context:** `is_same_origin` originally ignored the port entirely, so
`https://host:8443/...` matched a `https://host` base and credentials would still be
sent to a different service on the same host. The permissive behavior was justified as
"base URLs rarely store a port."

**Lesson:** Compare the **effective** port — normalize a missing port to the scheme
default (443/80) — instead of dropping it. That keeps `https://host` ≡ `https://host:443`
(the reason ports were skipped) while correctly rejecting non-default ports. A different
port is a different origin for credential purposes; fail closed.
