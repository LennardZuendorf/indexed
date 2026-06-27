---
type: feature-tech
feature: critical-bugs
sibling: product.md
parent: ../../tech.md
updated: 2026-06-27
---

# Feature: Critical Bugs (non-core) — Architecture

Four bounded fixes across the connectors and the app layers. The two security
fixes add an origin check before any credentialed attachment download and a loud
warning when Outline TLS verification is disabled. The two UX fixes re-order one
console call in `index create` and correct the status/progress copy in
`index search`. Nothing here imports from or edits `packages/indexed-core` — the
guards live where the credentials and the console output already are, so they
take effect through the existing `from_config` / command entry paths.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

---

## Files

```
# NEW — shared origin guard (connectors-local; no core dependency)
packages/indexed-connectors/src/connectors/_url_guard.py            # is_same_origin(url, base_url)        ~25 LOC

# #123 — credentialed attachment fetchers gain the origin guard
packages/indexed-connectors/src/connectors/jira/unified_jira_document_reader.py   # _fetch_attachment_bytes (~237)  +guard
packages/indexed-connectors/src/connectors/jira/async_jira_cloud_reader.py        # _fetch_attachment_bytes (~235)  +guard
packages/indexed-connectors/src/connectors/confluence/confluence_document_reader.py # __fetch_attachment_bytes (240) +guard
packages/indexed-connectors/src/connectors/outline/outline_document_reader.py     # _download_attachment_url (~390) +guard

# #124 — loud warning on insecure TLS
packages/indexed-connectors/src/connectors/outline/outline_document_reader.py     # __init__ (~91)  warn when verify_ssl is False

# #114 — storage indicator ordering (app)
apps/indexed/src/indexed/knowledge/commands/create.py            # create_jira/_confluence/_outline/_files: display indicator first
apps/indexed/src/indexed/knowledge/commands/_create_helpers.py   # remove indicator call from execute_create_command (~100-103)

# #110 / #88 — search status copy (app)
apps/indexed/src/indexed/knowledge/commands/search.py            # headline (414-417) + progress title/label (448-466)

# Tests
tests/unit/indexed_connectors/jira/test_reader_attachments.py
tests/unit/indexed_connectors/jira/test_async_reader_attachments.py
tests/unit/indexed_connectors/confluence/                        # attachment reader test (add off-origin case)
tests/unit/indexed_connectors/outline/test_reader_attachments.py
tests/unit/indexed_connectors/outline/test_readers.py            # verify_ssl warning
tests/unit/indexed_connectors/test_url_guard.py                  # NEW — origin helper unit tests
tests/unit/indexed/knowledge/commands/test_create.py             # indicator-order assertion
tests/unit/indexed/knowledge/commands/test_search.py             # status-copy assertions
```

---

## Contract / API

```python
# packages/indexed-connectors/src/connectors/_url_guard.py
def is_same_origin(url: str, base_url: str) -> bool:
    """True iff url and base_url share scheme + host (case-insensitive host).

    Port is intentionally NOT compared: Atlassian Cloud, Confluence and Outline
    serve attachments from the same host on the default port, and base URLs are
    often stored without an explicit port. Scheme+host matches the threat model
    in issue #123 ("same-origin … scheme+host"). A malformed or hostless url
    returns False (fail closed).
    """
```

Each credentialed fetcher gains the same prologue (sync example; the async
readers mirror it before issuing the `await client.get(...)`):

```python
from .._url_guard import is_same_origin   # relative import within connectors

def _fetch_attachment_bytes(self, url: str) -> bytes | None:
    if not is_same_origin(url, self.base_url):
        logger.warning(
            f"Skipping off-origin attachment; refusing to send credentials to: {url}"
        )
        return None
    ...  # existing credentialed download unchanged
```

---

## Implementation Detail

### #123 — origin guard before credentialed download (R1)

All four readers already hold the configured base URL as `self.base_url`
(`unified_jira_document_reader.py:96`, `async_jira_cloud_reader.py:55`,
`confluence_document_reader.py:83`, `outline_document_reader.py:79`) and pass an
**API-supplied** URL straight into a credentialed request (`att["content"]` for
Jira/Confluence; the attachment href for Outline). The fix inserts the
`is_same_origin` check as the first statement of each fetch method and returns
`None` (skip, already the readers' "failed download" contract) on mismatch. No
signature changes, so callers and the `BaseConnector` protocol are untouched.

The helper is a single ~25-LOC module under `connectors/` using
`urllib.parse.urlsplit`; it has no third-party or core dependency, so importing
it from each connector keeps the change connector-local. Outline already guards
*inline image* rewriting against its host — this extends the same principle to
API-returned attachment URLs, which were not covered.

### #124 — loud TLS warning (R2)

`verify_ssl` defaults to `True` (`outline/schema.py:52`, reader param
`outline_document_reader.py:76`). The reader stores it at `__init__`
(`:91 self.verify_ssl = verify_ssl`) and threads it into every `requests` /
`httpx` client (`:235, :280, :498`). The fix adds, immediately after `:91`:

```python
if not verify_ssl:
    logger.warning(
        "Outline: TLS certificate verification is DISABLED (verify_ssl=False). "
        "Your API token may be exposed to a man-in-the-middle. Only use this for "
        "trusted self-hosted instances with self-signed certificates."
    )
```

Because the warning lives in the connector constructor, it fires through the
normal `connector_cls.from_config(...)` path — including the incremental-update
restore in core's `update_collection_factory.py` — **without editing core**. The
schema default and the transport behaviour are unchanged; the escape hatch stays
functional, just no longer silent.

### #114 — storage indicator ordering (R3)

Root cause: each connector command (`create_jira`/`create_confluence`/
`create_outline` in `create.py`) prints its own "<Source> Configuration" header
and prompts for the URL **before** calling `execute_create_command`, while the
indicator is printed *inside* `execute_create_command`
(`_create_helpers.py:~100-103`). Fix: hoist the indicator to the first lines of
each connector command (guarded by the existing `if not is_verbose_mode()`), and
delete the call from `execute_create_command` so it is not printed twice. The
`files` path, which prompts via a callback inside `execute_create_command`, gets
the same hoisted call at the top of `create_files`. Pure ordering change, app-only.

### #110 / #88 — search status copy (R4)

In `search.py`, the single-collection branch prints a redundant headline
(`:414-417`) and the progress block builds its title from the **query** instead
of the collection (`:448-452`). Fixes:

- **Remove** the `:414-417` single-collection headline entirely. The
  multi-collection branch keeps its existing headline (`:400-402`).
- **Branch the progress title by mode** (the mode is already known —
  `collection is None` ⇒ multi):
  - single: `title = f'Searching "{collection}" Collection for: "{query}"'`,
    phase label stays `Searching {coll_name}` (→ `✓ Searching outline`).
  - multi: pass `title=""` to `create_phased_progress` (the summary headline
    already printed at `:400-402`) and set each phase label to
    `f'Searching "{coll_name}" Collection for: "{query}"'`.

`create_phased_progress(title=...)` prints `title` once on enter
(`progress_bar.py:74-75`); each `start_phase`/`finish_phase` renders the
`✓ <label>` line. Simple/verbose paths (`:433-445`) print no status lines and
are left unchanged.

---

## Open Questions

1. **Outline `_download_attachment_url` origin source** — it fetches an
   attachment href that may already be relative-resolved against `self.base_url`;
   confirm at impl whether the guard should run on the raw API href or the
   resolved URL so a same-origin attachment is never falsely skipped.
2. **Confluence attachment test location** — `tests/unit/indexed_connectors/
   confluence/` has no dedicated attachment test file yet; add one mirroring the
   Jira `test_reader_attachments.py` fixture style (mock `requests.get`).
