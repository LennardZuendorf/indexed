---
type: feature-plan
feature: critical-bugs
sibling: tech.md
parent: ../../plan.md
updated: 2026-06-27
---

# Feature: Critical Bugs (non-core) — Implementation Plan

Five small, independently shippable units: a shared origin guard wired into the
four credentialed attachment fetchers (security), a loud Outline TLS warning
(security), and two app-layer copy/ordering fixes (UX). Security units land
first. No unit touches `packages/indexed-core`.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Standalone hardening on the shipped v1 surface (root
[plan.md](../../plan.md) Feature Sequence #1–#9 are `DONE`). Does not depend on
the v2 rewrite or the `file-watcher` work.

---

## Problem Frame

Four open bugs are high-impact yet fixable outside core: two leak or expose
credentials (#123 SSRF/credential-to-attacker, #124 TLS-off MITM), two emit
wrong/confusing CLI output (#114 indicator order, #110/#88 search status). The
SSRF fix is shared logic touching four readers, so a helper lands first (unit 1)
and the remaining readers consume it (unit 2). The other three units are
orthogonal one-file fixes. Security units precede UX units.

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Attachment fetches MUST NOT leak credentials off-origin](product.md#requirement-attachment-fetches-must-not-leak-credentials-off-origin) | critical-bugs/1, critical-bugs/2 |
| R2 | [Disabling TLS verification MUST be loud](product.md#requirement-disabling-tls-verification-must-be-loud) | critical-bugs/3 |
| R3 | [Storage indicator MUST precede the first prompt](product.md#requirement-storage-indicator-must-precede-the-first-prompt) | critical-bugs/4 |
| R4 | [Search status messages MUST be accurate and non-redundant](product.md#requirement-search-status-messages-must-be-accurate-and-non-redundant) | critical-bugs/5 |

---

## Key Technical Decisions

1. **Shared `is_same_origin` helper, scheme+host only.** One ~25-LOC module in
   `connectors/` rather than four copies; port intentionally ignored to match the
   #123 threat model and avoid false skips on default-port base URLs. Fail closed
   on malformed URLs. Detail: [tech.md](tech.md#contract--api).
2. **Skip-and-warn on off-origin (not hard-error).** Returns `None` — the
   readers' existing "download failed" contract — so indexing continues and no
   credentials ever leave the configured host. (Open Q in product.md.)
3. **TLS warning in the connector constructor, not core.** Fires via
   `from_config` on every run including incremental updates, keeping the fix out
   of `update_collection_factory.py`. Default `verify_ssl=True` unchanged.
4. **Hoist the storage indicator into each connector command.** The indicator
   must precede connector prompts that run *before* `execute_create_command`; the
   only place earlier than those prompts is the command function top.
5. **Branch search progress title by single/multi.** Mode is already known at the
   print site; reuse it to drop the redundant single headline and name the
   collection instead of the query.

---

## Unit IDs

Units are `critical-bugs/n`, assigned once and never renumbered. Cite in commits
and tests (`fix(connectors): critical-bugs/1 ...`).

---

### critical-bugs/1 — Origin guard helper + Jira readers

**Goal:** Add `is_same_origin` and stop both Jira readers from sending credentials to off-origin attachment URLs.

**Requirements:** R1

**Dependencies:** —

**Files:**

```
packages/indexed-connectors/src/connectors/_url_guard.py                          # NEW helper
packages/indexed-connectors/src/connectors/jira/unified_jira_document_reader.py    # guard in _fetch_attachment_bytes
packages/indexed-connectors/src/connectors/jira/async_jira_cloud_reader.py         # guard in _fetch_attachment_bytes
tests/unit/indexed_connectors/test_url_guard.py                                    # NEW helper unit tests
tests/unit/indexed_connectors/jira/test_reader_attachments.py                      # +off-origin case
tests/unit/indexed_connectors/jira/test_async_reader_attachments.py                # +off-origin case
```

**Test scenarios:**

- `is_same_origin` true for same scheme+host, false for different host, different scheme, and malformed/hostless URL.
- Off-origin attachment URL → fetcher returns `None`, issues **no** HTTP request (assert mock `requests.get` / `httpx` client never called), logs a warning.
- Same-origin attachment URL → existing credentialed download still runs and returns bytes (regression).

**Verification:** `uv run pytest tests/unit/indexed_connectors/test_url_guard.py tests/unit/indexed_connectors/jira/ -q` green; `uv run mypy src/` 0 errors.

---

### critical-bugs/2 — Confluence + Outline attachment guard

**Goal:** Apply the same origin guard to the Confluence and Outline credentialed attachment fetchers.

**Requirements:** R1

**Dependencies:** critical-bugs/1

**Files:**

```
packages/indexed-connectors/src/connectors/confluence/confluence_document_reader.py   # guard in __fetch_attachment_bytes
packages/indexed-connectors/src/connectors/outline/outline_document_reader.py         # guard in _download_attachment_url
tests/unit/indexed_connectors/confluence/<attachment test>                            # NEW/updated off-origin case
tests/unit/indexed_connectors/outline/test_reader_attachments.py                      # +off-origin case
```

**Test scenarios:**

- Confluence off-origin attachment URL → skipped, no credentialed request, warning logged.
- Outline off-origin attachment URL → skipped, no credentialed request, warning logged.
- Same-origin attachment for both → downloads unchanged (regression). Resolve tech.md Open Q1 (raw vs resolved href) so a legitimate same-origin attachment is never falsely skipped.

**Verification:** `uv run pytest tests/unit/indexed_connectors/confluence/ tests/unit/indexed_connectors/outline/ -q` green.

---

### critical-bugs/3 — Outline insecure-TLS warning

**Goal:** Emit a loud security warning when `verify_ssl=False`, default unchanged.

**Requirements:** R2

**Dependencies:** —

**Files:**

```
packages/indexed-connectors/src/connectors/outline/outline_document_reader.py   # warn in __init__ (~91)
tests/unit/indexed_connectors/outline/test_readers.py                           # warning present/absent
```

**Test scenarios:**

- Reader constructed with `verify_ssl=False` → security warning logged (assert via `caplog`).
- Reader constructed with default `verify_ssl` → no TLS warning, verification active.

**Verification:** `uv run pytest tests/unit/indexed_connectors/outline/ -q` green.

---

### critical-bugs/4 — Storage indicator ordering

**Goal:** Print the storage-mode indicator before any connector header/prompt in `index create`.

**Requirements:** R3

**Dependencies:** —

**Files:**

```
apps/indexed/src/indexed/knowledge/commands/create.py            # hoist indicator into create_jira/_confluence/_outline/_files
apps/indexed/src/indexed/knowledge/commands/_create_helpers.py   # remove indicator call from execute_create_command
tests/unit/indexed/knowledge/commands/test_create.py             # ordering assertion
```

**Test scenarios:**

- Running a connector create command prints the storage indicator before the "<Source> Configuration" header / URL prompt (assert ordering via the mocked `console` `mock_calls`).
- Indicator is printed exactly once (no duplicate from `execute_create_command`).

**Verification:** `uv run pytest tests/unit/indexed/knowledge/commands/test_create.py -q` green.

---

### critical-bugs/5 — Search status copy

**Goal:** Drop the redundant single-collection headline and label progress by collection name.

**Requirements:** R4

**Dependencies:** —

**Files:**

```
apps/indexed/src/indexed/knowledge/commands/search.py        # headline 414-417 + title/label 448-466
tests/unit/indexed/knowledge/commands/test_search.py         # single + multi copy assertions
```

**Test scenarios:**

- `-c outline` normal output: no `in 1 Collection:` headline; progress text contains `Searching "outline" Collection for:` and the collection name, not the query.
- Multi-collection: `Searching for "<query>" in N Collections:` headline retained; each phase label names its collection.
- `--simple-output` / verbose: output unchanged (no status lines).

**Verification:** `uv run pytest tests/unit/indexed/knowledge/commands/test_search.py -q` green.

---

## Dependencies

| Unit | Blocks | Blocked by |
|---|---|---|
| critical-bugs/1 | critical-bugs/2 | — |
| critical-bugs/2 | — | critical-bugs/1 |
| critical-bugs/3 | — | — |
| critical-bugs/4 | — | — |
| critical-bugs/5 | — | — |

---

## Progress

| Unit | Status |
|---|---|
| critical-bugs/1 | NOT STARTED |
| critical-bugs/2 | NOT STARTED |
| critical-bugs/3 | NOT STARTED |
| critical-bugs/4 | NOT STARTED |
| critical-bugs/5 | NOT STARTED |

---

## Open Questions

1. **Per-bug PR vs one branch.** All five units live on
   `claude/indexed-critical-bugs-oobe5g`. Confirm whether to split the security
   fixes (#123/#124) into their own PR ahead of the UX fixes, or ship the bundle
   as one.
