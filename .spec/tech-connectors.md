---
type: branch
scope: connectors
parent: tech.md
covers: connector protocol, implemented connectors, change tracking
updated: 2026-11-09
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
**ty error**, not a runtime `AttributeError`. Reader fetches raw documents; Converter
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

---

## Query-Time Git Helper (`utils/git_meta.py`)

Indexing is not the only consumer of git: `search --changed-since` and
`--git-provenance` ask the *query* side the same questions. The shared helper lives in
`src/indexed/utils/git_meta.py` — `utils` is the only layer both `core` and
`connectors` may import (a connector-local helper would break the import edges).

- Stdlib `subprocess` only, every call a list argv with `timeout=5`, a checked return
  code, and **all** exceptions swallowed to `None`/empty: a git problem must never
  break a search. The child env strips leaked `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`/
  `GIT_OBJECT_DIRECTORY`/`GIT_CEILING_DIRECTORIES` and pins `GIT_TERMINAL_PROMPT=0`,
  `LC_ALL=C` — the same hygiene as `change_tracker.py`.
- `repo_toplevel` / `is_git_repo` — `git rev-parse --show-toplevel`.
- `changed_paths(repo, ref)` — union of `git diff --name-only <ref> --` (REF's tree vs
  the **working tree**, so committed, staged and unstaged changes all count) and
  `git ls-files --others --exclude-standard` for untracked work. Two legs: a plain
  `git diff` and a `--cached` diff add nothing this one call does not already see.
  An invalid ref returns `None` (verified up front via
  `rev-parse --verify <ref>^{commit}`) — a typo must never look like "nothing changed".
- `last_commit(repo, path)` — ONE `git log -1 --format=…` per file, giving
  `{commit, short, author, email, committedAt, subject}`. **No blame-by-line in this
  slice**: provenance is document-level, so a file's history is one cheap call, not a
  per-chunk `git blame`.
- `snapshot_is_current(base_path, source_id, modified_time, indexed_at=None)` — compares
  a node's indexed `modified_time` with the file's mtime now (`os.path` + `stat`, no
  subprocess). The stored value is offset-aware UTC, so the comparison is
  zone-independent; an offset-less (legacy) value is judged instead against the
  manifest's `updatedTime`, which is zone-free. `last_commit` answers for the file as it
  is on disk, so retrieval attaches provenance only while this says the indexed
  snapshot still describes it.
- `repo_relative(repo, base_path, source_id)` — document ids are base-path-relative
  (`v1_adapter.py:35-36`), git pathspecs are repo-relative; this rebases with `os.path`
  arithmetic only (no symlink resolution, no filesystem probe).
- **No global cache.** Callers memoize per search call, so a long-lived MCP server
  cannot serve stale git facts.
