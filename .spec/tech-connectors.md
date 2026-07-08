---
type: branch
scope: connectors
parent: tech.md
covers: connector protocol, implemented connectors, change tracking
updated: 2026-07-07
---

# Tech Branch: Connectors (`indexed-connectors`)

Protocol-based data-source adapters. May import protocols/config/utils/parsing;
MUST NOT import core engine, CLI, or MCP (see [tech.md](tech.md) § Architectural Rules).

**Parent: [tech.md](tech.md).** Document parsing: [tech-parsing.md](tech-parsing.md).

---

## Connector Protocol

**File:** `packages/indexed-core/src/core/v1/connectors/base.py`

```python
from typing import Protocol, Iterator

class DocumentReader(Protocol):
    def read_documents(self) -> Iterator[RawDocument]:
        """Fetch documents from source."""
        ...

class DocumentConverter(Protocol):
    def convert(self, doc: RawDocument) -> Iterator[Document]:
        """Convert raw document to searchable chunks."""
        ...

class BaseConnector(Protocol):
    @property
    def reader(self) -> DocumentReader: ...
    @property
    def converter(self) -> DocumentConverter: ...
    @property
    def connector_type(self) -> str: ...
```

Reader fetches raw documents; Converter transforms them into searchable chunks
(text + metadata) via the parsing module.

---

## Implemented Connectors

| Connector | Location | Protocol | Auth |
|-----------|----------|----------|------|
| **FileSystemConnector** | `.../connectors/files/` | Local FS | None |
| **JiraCloudConnector** | `.../connectors/jira/` | REST API | Email + Token |
| **JiraServerConnector** | `.../connectors/jira/` | REST API | Email + Token |
| **ConfluenceCloudConnector** | `.../connectors/confluence/` | REST API | Email + Token |
| **ConfluenceServerConnector** | `.../connectors/confluence/` | REST API | Email + Token |
| **OutlineConnector** | `.../connectors/outline/` | REST API | Bearer token |

(All paths under `packages/indexed-connectors/src/`.)

---

## Credential Security — Origin Guard

**File:** `packages/indexed-connectors/src/connectors/_url_guard.py`

All credentialed attachment fetchers (Jira Server/DC, Confluence Server, Outline) call
`warn_if_off_origin(url, base_url)` before issuing any HTTP request. This function
compares scheme + hostname + **effective port** (missing ports normalized to the
scheme default — 443 for HTTPS, 80 for HTTP — so a base URL without an explicit port
still matches a default-port attachment, while a non-default port like `:8443` is a
different origin), logs a warning, and returns `False` on mismatch so the caller can
`return None` without crashing the indexing run.

```python
from connectors._url_guard import warn_if_off_origin

if not warn_if_off_origin(url, self.base_url):
    return None   # skip silently after logging warning
```

`is_same_origin(url, base_url)` is the primitive (bool only, no side effects).
`warn_if_off_origin` wraps it with logging and is the one to use in readers.

`is_cloud_host(url)` (same module) is the Cloud-vs-Server discriminator: it parses
the host **before** the `*.atlassian.net` suffix check, so a raw-URL substring like
`https://evil.com/x.atlassian.net` is not misread as Cloud (incomplete URL-substring
sanitization). The Jira/Confluence Cloud readers use it instead of a bare
`base_url.endswith(".atlassian.net")`.

**Exclusions:** `AsyncJiraCloudDocumentReader` — Jira Cloud serves attachment content
from `api.media.atlassian.com` (off-origin by design, URLs from Jira's own API, not
attacker-controlled). `AsyncConfluenceCloudDocumentReader` — constructs URLs as
`f"{self.base_url}/wiki{path}"` (always same-origin by construction; guard unnecessary).

---

## Change Tracking

`FileSystemConnector` supports incremental indexing via `ChangeTracker`:

| Strategy | Detection |
|----------|-----------|
| **git** | `git diff --name-status` between commits |
| **content-hash** | xxhash of contents vs stored state |
| **mtime** | modification time (faster, less reliable) |
| **auto** | git if `.git` exists, else content-hash |

State persisted as `state.json`, updated after each successful run.

**Correctness:** the git strategy is **content-hash-authoritative** — it reconciles
the diff against stored content hashes, so a file edited and then **reverted back to
its committed state** is still re-indexed (a name-status diff alone would miss it).
Git **C-quoted non-ASCII paths** (`"\303\244…"`) are unquoted to real filenames
before tracking.
