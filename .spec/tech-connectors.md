---
type: branch
scope: connectors
parent: tech.md
covers: connector protocol, implemented connectors, change tracking
updated: 2026-07-10
---

# Tech Branch: Connectors (`src/indexed/connectors/`)

Protocol-based data-source adapters. May import protocols/config/utils/parsing;
MUST NOT import core engine, CLI, or MCP (see [tech.md](tech.md) § Architectural Rules).

**Parent: [tech.md](tech.md).** Document parsing: [tech-parsing.md](tech-parsing.md).

---

## Connector Protocol

**File:** `src/indexed/protocols/connectors.py`

```python
from typing import Any, Iterator, Protocol, runtime_checkable

@runtime_checkable
class DocumentReader(Protocol):
    def get_number_of_documents(self) -> int: ...
    def read_all_documents(self) -> Iterator[Any]: ...
    def get_reader_details(self) -> dict: ...          # per-source "reader" block for the manifest

class DocumentConverter(Protocol):
    def convert(self, doc: Any) -> Iterator[ConvertedDocument]: ...

class BaseConnector(Protocol):
    @property
    def reader(self) -> DocumentReader: ...
    @property
    def converter(self) -> DocumentConverter: ...
    @property
    def connector_type(self) -> str: ...
    @classmethod
    def from_config(cls, config_service) -> "BaseConnector": ...
    @classmethod
    def from_manifest(cls, manifest, config_service, *, storage_path) -> ConnectorRun: ...
```

The protocols declare exactly what the engine calls — a connector missing a method is a
**mypy error**, not a runtime `AttributeError`. Reader fetches raw documents; Converter
transforms them into searchable chunks (text + metadata) via the parsing module.
`from_manifest` rebuilds `(reader, converter, deletions, post_run)` (a `ConnectorRun`) for
an incremental update from the collection's own manifest, so **core's update path is
source-agnostic** — one call for every connector, no per-type / `localFiles` branch.

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

(All paths under `src/indexed/connectors/`.)

---

## Credential Security — Origin Guard

**File:** `src/indexed/connectors/_url_guard.py`

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
