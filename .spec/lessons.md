---
type: lessons
scope: project
updated: 2026-06-29
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

**Fix pattern:** Extract a helper with direct param access:
```python
def _display_storage_indicator(verbose: bool, log_level: Optional[str]) -> None:
    if not verbose and not (log_level and log_level.upper() in ("INFO", "DEBUG")):
        from ...utils.storage_info import display_storage_mode_for_command
        display_storage_mode_for_command(console)
```

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
