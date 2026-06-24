---
type: branch
scope: connectors
parent: tech.md
covers: connector protocol, implemented connectors, change tracking
updated: 2026-06-15
---

# Tech Branch: Connectors (`indexed-connectors`)

Protocol-based data-source adapters. May import protocols/config/utils/parsing;
MUST NOT import core engine, CLI, or MCP (see [tech.md](tech.md) § Architectural Rules).

**Parent: [tech.md](tech.md).** Document parsing: [tech-parsing.md](tech-parsing.md).

---

## Connector Protocol

**File:** `packages/indexed-core/src/core/v1/connectors/base.py`

```python
from typing import Protocol, runtime_checkable, ClassVar, Any, Dict

@runtime_checkable
class BaseConnector(Protocol):
    META: ClassVar[Any]                       # optional metadata

    @property
    def reader(self): ...                     # read_all_documents(), get_number_of_documents()
    @property
    def converter(self): ...                  # raw doc → chunks via parsing module
    @property
    def connector_type(self) -> str: ...      # 'jira', 'confluence', 'files', …

    @classmethod
    def config_spec(cls) -> Dict[str, Dict[str, Any]]: ...   # required/optional config fields
    @classmethod
    def from_config(cls, config_service: Any) -> "BaseConnector": ...
```

Only `BaseConnector` is defined; `reader` / `converter` are duck-typed (there are
**no** separate `DocumentReader` / `DocumentConverter` protocol classes). The reader
fetches raw documents via `read_all_documents()`; the converter transforms them into
searchable chunks (text + metadata) via the parsing module.

---

## Implemented Connectors

| Connector | Location | Protocol | Auth |
|-----------|----------|----------|------|
| **FileSystemConnector** | `.../connectors/files/` | Local FS | None |
| **JiraConnector** (Server/DC) | `.../connectors/jira/` | REST API | Token, or login + password |
| **JiraCloudConnector** | `.../connectors/jira/` | REST API | Email + Token |
| **ConfluenceConnector** (Server/DC) | `.../connectors/confluence/` | REST API | Token, or login + password |
| **ConfluenceCloudConnector** | `.../connectors/confluence/` | REST API | Email + Token |
| **OutlineConnector** | `.../connectors/outline/` | REST API | Bearer token |

(All paths under `packages/indexed-connectors/src/`.)

---

## Change Tracking

`FileSystemConnector` supports incremental indexing via `ChangeTracker`:

| Strategy | Detection |
|----------|-----------|
| **git** | `git diff --name-status` between commits |
| **content_hash** | xxhash of contents vs stored state |
| **mtime** | modification time (faster, less reliable) |
| **auto** | git if `.git` exists, else `content_hash` |
| **none** | no detection — every document treated as added |

State persisted as `state.json`, updated after each successful run.
