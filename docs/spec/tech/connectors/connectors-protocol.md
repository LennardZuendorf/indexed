---
type: tech
updated: 2026-11-22
applies: "src/indexed/connectors/**"
---

# Connector Protocol

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
