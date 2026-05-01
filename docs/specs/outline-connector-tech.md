# Outline Wiki Connector — Technical Spec

**Status:** Proposed
**Author:** Engineering
**Date:** 2026-05-01

---

## Architecture Overview

The Outline connector follows the same three-file structure as every other connector in `packages/indexed-connectors/`:

```
packages/indexed-connectors/src/connectors/outline/
├── __init__.py                    # Public re-exports
├── schema.py                      # OutlineConfig (Pydantic)
├── outline_document_reader.py     # Async httpx reader
├── outline_document_converter.py  # Markdown → chunks via ParsingModule
└── connector.py                   # OutlineConnector (composes reader + converter)
```

**No Cloud/Server split.** Outline's REST API is identical between `https://app.getoutline.com` and any self-hosted deployment — same RPC endpoints, same `Authorization: Bearer ol_api_…` header, same response shapes. The only difference is the `base_url`. A single `OutlineConnector` handles both; the `url` field carries that distinction.

---

## Outline API Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /api/collections.list` | paginated | Enumerate workspace collections |
| `POST /api/documents.list` | paginated | List documents (filter by `collectionId`, `status`) |
| `POST /api/documents.info` | single | Fetch full document with Markdown body |
| `POST /api/attachments.list` | paginated | List attachments for a document |
| `GET /api/attachments.redirect?id=...` | redirect | Download attachment bytes (follows 302 to signed URL) |

**Authentication:** `Authorization: Bearer ol_api_XXXXX` header on every request.

**Pagination:** `POST` body accepts `{ offset: int, limit: int }`. Response contains `{ data: [...], pagination: { offset, limit, total } }`. Traverse by incrementing `offset += len(data)` until `offset >= total`.

**Document status:** Pass `status: "published"` in `documents.list` to exclude drafts and archived docs.

---

## Configuration Schema (`schema.py`)

```python
class OutlineConfig(BaseModel):
    url: str = Field(
        default="https://app.getoutline.com",
        description="Outline base URL — Cloud or self-hosted domain"
    )
    api_token: Optional[str] = Field(
        None, description="API token (env: OUTLINE_API_TOKEN)"
    )
    collection_ids: Optional[list[str]] = Field(
        None, description="Restrict to specific collection IDs (None = all)"
    )
    include_attachments: bool = Field(
        True, description="Download and OCR inline images and file attachments"
    )
    download_inline_images: bool = Field(
        True, description="Extract and download images referenced inline in Markdown"
    )
    ocr_enabled: bool = Field(True, description="Enable OCR for image attachments")
    max_chunk_tokens: int = Field(512, ge=64, le=2048)
    max_attachment_size_mb: int = Field(10, ge=1, le=100)
    batch_size: int = Field(50, ge=1, le=250)
    max_concurrent_requests: int = Field(10, ge=1, le=50)
    verify_ssl: bool = Field(
        True, description="Verify TLS certificates (disable for self-signed CAs)"
    )

    @field_validator("url", mode="before")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    def get_api_token(self) -> str:
        token = self.api_token or os.getenv("OUTLINE_API_TOKEN")
        if not token:
            raise ValueError("OUTLINE_API_TOKEN not set in config or environment")
        return token
```

**Namespace:** `sources.outline` (registered in `NAMESPACE_REGISTRY`).

**Sensitive field:** `api_token` is routed to `.env` by `ConfigService` (matches the pattern used by Jira and Confluence API tokens).

---

## Document Reader (`outline_document_reader.py`)

### Design

Mirrors `async_confluence_cloud_reader.py` exactly — sequential page listing, concurrent document body + attachment fetching within sliding windows:

```
Phase 1 (sequential):  collections.list  →  per-collection documents.list (paginated)
Phase 2 (windowed):    buffer 100 doc stubs
                       asyncio.gather → documents.info  (body + metadata)
                       asyncio.gather → attachment downloads  (if enabled)
Phase 3 (yield):       yield {"document": full_doc, "attachments": [...]}
```

### Key parameters

```python
class OutlineDocumentReader:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        collection_ids: Optional[list[str]] = None,
        batch_size: int = 50,
        max_concurrent_requests: int = 10,
        include_attachments: bool = True,
        download_inline_images: bool = True,
        max_attachment_size_mb: int = 10,
        number_of_retries: int = 3,
        retry_delay: float = 1.0,
        verify_ssl: bool = True,
    ): ...
```

### Pagination loop (simplified)

```python
def _iter_document_stubs(self) -> Iterator[dict]:
    for collection_id in self._get_collection_ids():
        offset = 0
        while True:
            data = self._post("documents.list", {
                "collectionId": collection_id,
                "status": "published",
                "limit": self.batch_size,
                "offset": offset,
            })
            for doc in data["data"]:
                yield doc
            offset += len(data["data"])
            if offset >= data["pagination"]["total"]:
                break
```

The outer `read_all_documents()` buffers stubs into windows of 100 then calls `asyncio.run(self._fetch_window_async(window))`, identical to the Confluence cloud reader pattern at `async_confluence_cloud_reader.py:75-94`.

### Attachment handling

1. If `include_attachments=True`, call `POST /api/attachments.list` for each document (concurrently, within the same semaphore).
2. For each listed attachment under `max_attachment_size_mb`, `GET /api/attachments.redirect?id=...` (follow redirects) to retrieve bytes.
3. If `download_inline_images=True`, also scan the document's Markdown `text` field for inline image references matching `![...](<url>/api/attachments.redirect?id=...)` and download them the same way, deduplicating by attachment `id`.
4. Yield attachment bytes as `{"filename": "<title>.<ext>", "bytes": <data>, "mimeType": "<mime>", "id": "<uuid>"}`.

### Error handling

- 429 responses: caught by `execute_with_retry` → exponential backoff (base 1s, ×2 per attempt, max 60s, capped at `number_of_retries`).
- 4xx on a single document: log warning, skip that document, continue iterating.
- 5xx: retry with backoff; if all retries exhausted, log error and skip.
- SSL errors on self-hosted: surface as `httpx.ConnectError` with a hint to set `verify_ssl=False` in config.

---

## Document Converter (`outline_document_converter.py`)

### Design

Mirrors `unified_confluence_document_converter.py` but operates on Markdown directly (no BeautifulSoup HTML stripping needed — Outline bodies are already Markdown).

```python
class OutlineDocumentConverter:
    def convert(self, document: dict) -> list[dict]:
        doc = document["document"]
        return [{
            "id": doc["id"],
            "url": doc["url"],
            "modifiedTime": doc["updatedAt"],
            "text": self._build_full_text(document),
            "chunks": self._split_to_chunks(document),
        }]
```

### Title hierarchy

Outline documents carry a `parentDocumentId` field. The reader pre-builds a `{id: title}` map per collection so the converter can walk ancestors cheaply:

```python
def _build_title_path(self, doc: dict, title_map: dict[str, str]) -> str:
    parts: list[str] = []
    parent_id = doc.get("parentDocumentId")
    while parent_id and parent_id in title_map:
        parts.insert(0, title_map[parent_id])
        parent_id = None  # Outline only provides direct parent in documents.list
    parts.append(doc["title"])
    return " -> ".join(parts)
```

### Chunking

Body text is chunked via `ParsingModule.parse_bytes(text.encode(), "doc.md")` (lazy-loaded, same pattern as Confluence converter at `unified_confluence_document_converter.py:56-64`). The first chunk is always the title path (provides navigation context for search result display). Subsequent chunks are the semantic chunks from ParsingModule.

### Attachment parsing

Each `{"filename": ..., "bytes": ..., "mimeType": ...}` from the reader is passed to `ParsingModule.parse_bytes(bytes, filename)`. Docling handles PDF, DOCX, and images (OCR). Chunk entries include `"metadata": {"attachment": filename}` so callers can identify the source.

---

## Connector (`connector.py`)

```python
class OutlineConnector:
    META: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        name="outline",
        display_name="Outline Wiki (Cloud or self-hosted)",
        description="Index Outline Wiki documents and attachments via API key",
        config_class=OutlineConfig,
        version="1.0.0",
        min_core_version="1.0.0",
        example="indexed index create outline --collection wiki",
    )

    def __init__(self, config: OutlineConfig): ...

    @property
    def connector_type(self) -> str:
        return "outline"

    @classmethod
    def from_config(cls, config_service) -> "OutlineConnector":
        config_service.register(OutlineConfig, path="sources.outline")
        provider = config_service.bind()
        cfg = provider.get(OutlineConfig)
        return cls(cfg)
```

---

## Registry Wiring

### `packages/indexed-connectors/src/connectors/registry.py`

```python
CONNECTOR_REGISTRY = {
    ...,
    "outline": OutlineConnector,
}
CONFIG_REGISTRY = {
    ...,
    "outline": OutlineConfig,
}
NAMESPACE_REGISTRY = {
    ...,
    "outline": "sources.outline",
}
```

### `packages/indexed-connectors/src/connectors/__init__.py`

```python
from .outline.connector import OutlineConnector
```

---

## CLI Command (`apps/indexed/src/indexed/knowledge/commands/create.py`)

New subcommand `indexed index create outline` modelled exactly on `create_confluence`:

```bash
indexed index create outline \
  --collection wiki \
  --url https://app.getoutline.com \
  --token ol_api_... \
  [--collection-id abc123,def456] \
  [--include-attachments] \
  [--no-ocr] \
  [--force] [--use-cache] [--local] [--verbose]
```

**Interactive prompts (when fields missing):**

1. `Outline URL [https://app.getoutline.com]:` — Enter → Cloud default; any string → self-hosted.
2. `Outline API Token:` — masked, stored in `.env`.

**Verbose log lines:**
```
INFO  Connecting to Outline at https://app.getoutline.com (Cloud)
INFO  Connecting to Outline at https://wiki.acme.internal (self-hosted)
```

---

## Files Changed

### New files

| Path | Purpose |
|------|---------|
| `packages/indexed-connectors/src/connectors/outline/__init__.py` | Public exports |
| `packages/indexed-connectors/src/connectors/outline/schema.py` | `OutlineConfig` |
| `packages/indexed-connectors/src/connectors/outline/outline_document_reader.py` | Async reader |
| `packages/indexed-connectors/src/connectors/outline/outline_document_converter.py` | Converter |
| `packages/indexed-connectors/src/connectors/outline/connector.py` | `OutlineConnector` |
| `tests/unit/indexed_connectors/outline/__init__.py` | Test package |
| `tests/unit/indexed_connectors/outline/test_init.py` | Registry membership |
| `tests/unit/indexed_connectors/outline/test_connector.py` | `from_config` round-trip |
| `tests/unit/indexed_connectors/outline/test_readers.py` | Pagination, collection filtering |
| `tests/unit/indexed_connectors/outline/test_reader_attachments.py` | Attachment download, size cap, retry |
| `tests/unit/indexed_connectors/outline/test_converters.py` | Chunk emission, title path, OCR |
| `docs/specs/outline-connector-product.md` | Product spec |
| `docs/specs/outline-connector-tech.md` | This document |

### Modified files

| Path | Change |
|------|--------|
| `packages/indexed-connectors/src/connectors/__init__.py` | Add `OutlineConnector` import + `__all__` entry |
| `packages/indexed-connectors/src/connectors/registry.py` | Add `"outline"` to all three registries |
| `apps/indexed/src/indexed/knowledge/commands/create.py` | Add `create_outline` Typer command + `OutlineConfig` lazy-load |

---

## Testing Plan

### Unit tests

| File | Scenarios |
|------|-----------|
| `test_init.py` | `"outline"` in `CONNECTOR_REGISTRY`, `CONFIG_REGISTRY`, `NAMESPACE_REGISTRY`; `OutlineConnector` importable from `connectors` |
| `test_connector.py` | `OutlineConnector.from_config` with mocked `ConfigService`; `connector_type == "outline"`; `repr` contains URL |
| `test_readers.py` | Pagination terminates at `total`; offset increments correctly; `collection_ids=None` fetches collections first; `collection_ids=[id]` skips collections call |
| `test_reader_attachments.py` | Inline image regex extracts URLs; oversized attachment skipped with warning; 429 triggers retry; attachment bytes land in yielded dict |
| `test_converters.py` | Title path from `parentDocumentId`; body chunks emitted; attachment chunk has `metadata.attachment`; no crash on empty body |

### Integration / smoke test

See product spec § Success Metrics for the end-to-end Cloud + self-hosted verification steps.

---

## Performance Characteristics

| Dimension | Estimate |
|-----------|---------|
| 1,000 published docs, no attachments | ~30s (50 docs/batch, 10 concurrent body fetches) |
| 1,000 docs + inline images | ~90s (image downloads add ~60s depending on sizes) |
| CLI startup overhead | 0ms (lazy-loaded, no module-level ML imports) |
| Memory footprint | Low — streaming iterator, no full workspace in memory |
