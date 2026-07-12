---
type: lessons
scope: project
updated: 2026-07-11
---

# Lessons Learned

Earned patterns — apply by default in future work.

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

---

## `test_e2e_search_collection` is order-dependent, not deterministic

**Context:** Full-suite run (`pytest -q --cov=src`) failed this test with
`IndexError('list index out of range')` inside a CLI search call; the same test passed
standalone. Deleting unrelated `.benchmarks/*.py` scripts was ruled out as the cause
(no import references, files never on the `--cov=src` path).

**Lesson:** `tests/benchmarks/test_e2e_performance.py::test_e2e_search_collection` leaks
shared state from an earlier test in the full run (likely collection/FAISS index state).
Treat a full-suite-only failure here as this known flake before assuming a real
regression — but still confirm by running the test standalone before shrugging it off.

---

## `!dir/` doesn't un-ignore files inside it — need `!dir/**`

**Context:** `.benchmarks/.gitignore` had `*.json` / `!baselines/`, meant to keep
`.benchmarks/baselines/*.json` trackable. Once the benchmark action started staging
a baseline commit on the PR branch itself (see tech.md § CI Benchmarking), every run
failed to stage it: `git add` errored "paths are ignored by one of your .gitignore
files" — the job still passed (push failures are non-fatal) but baselines silently
never updated.

**Lesson:** Negating a directory (`!baselines/`) only un-ignores the directory entry;
files inside are still matched by an earlier broad pattern (`*.json`) unless the
negation also covers them (`!baselines/**`). `git check-ignore -v` doesn't reliably
surface this — verify with `git add`/`git status` instead, since that's what CI
actually runs.
