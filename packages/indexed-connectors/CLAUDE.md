# Connector System Architecture Guide

This package implements a plugin-based connector system for ingesting documents from multiple data sources.

## Package Overview

**Location:** `packages/indexed-connectors/`

**Purpose:**
- Define connector protocol for extensibility
- Implement built-in connectors (Jira, Confluence, Files)
- Provide registry for dynamic connector instantiation
- Enable community contributions via plugin pattern

**Key Features:**
- **Protocol-based design:** All connectors implement `BaseConnector` protocol
- **Reader/Converter separation:** Clear separation of concerns
- **Lazy initialization:** Connectors created on-demand
- **Configuration-driven:** Connector behavior via Pydantic models
- **Memory efficient:** Document streaming (not loading all at once)

**Key Files:**
```
src/connectors/
├── base.py                         # BaseConnector protocol
├── models.py                       # Connector data models
├── protocol.py                     # Connector interface definitions
├── registry.py                     # Connector registry & factory
│
├── files/
│   ├── connector.py                # FileSystemConnector
│   ├── files_document_reader.py    # Reads files via Unstructured
│   ├── files_document_converter.py # Converts files to chunks
│   └── schema.py                   # LocalFilesConfig (Pydantic)
│
├── jira/
│   ├── connector.py                # JiraConnector, JiraCloudConnector
│   ├── jira_document_reader.py     # Jira Server/DC reader
│   ├── jira_cloud_document_reader.py
│   ├── unified_jira_document_reader.py
│   ├── jira_document_converter.py  # Converts issues to chunks
│   ├── jira_cloud_document_converter.py
│   ├── unified_jira_document_converter.py
│   └── schema.py                   # JiraConfig (Pydantic)
│
├── confluence/
│   ├── connector.py                # ConfluenceConnector, ConfluenceCloudConnector
│   ├── confluence_document_reader.py
│   ├── confluence_cloud_document_reader.py
│   ├── confluence_document_converter.py
│   ├── confluence_cloud_document_converter.py
│   └── schema.py                   # ConfluenceConfig (Pydantic)
│
└── document_cache_reader_decorator.py  # Caching decorator for readers
```

## Connector Protocol

All connectors implement the `BaseConnector` protocol:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class BaseConnector(Protocol):
    """Protocol for document source connectors."""

    @property
    def reader(self) -> DocumentReader:
        """Document reader for fetching raw documents."""
        ...

    @property
    def converter(self) -> DocumentConverter:
        """Document converter for transforming documents."""
        ...

    @property
    def connector_type(self) -> str:
        """Type identifier for this connector."""
        ...
```

**Advantages:**
- No inheritance required (duck typing)
- Easy to test connectors in isolation
- Type-safe via `@runtime_checkable`
- Enables community contributions without modifying core

## Connector Registry

Dynamic connector instantiation and discovery:

```python
from connectors.registry import (
    get_connector_class,
    get_config_class,
    get_config_namespace,
    list_connector_types,
)

# Get connector by type
ConnectorClass = get_connector_class("jira")  # JiraConnector

# Get configuration schema
ConfigClass = get_config_class("jira")  # JiraConfig

# Get config namespace (for hierarchical config)
namespace = get_config_namespace("jira")  # "sources.jira"

# List all available connectors
types = list_connector_types()  # ["files", "jira", "jiraCloud", "confluence", ...]
```

**Registry Entries:**

| Type | Connector Class | Config Class | Namespace |
|------|-----------------|--------------|-----------|
| `files` | `FileSystemConnector` | `LocalFilesConfig` | `sources.files` |
| `jira` | `JiraConnector` | `JiraConfig` | `sources.jira` |
| `jiraCloud` | `JiraCloudConnector` | `JiraCloudConfig` | `sources.jira` |
| `confluence` | `ConfluenceConnector` | `ConfluenceConfig` | `sources.confluence` |
| `confluenceCloud` | `ConfluenceCloudConnector` | `ConfluenceCloudConfig` | `sources.confluence` |

## Built-in Connectors

### 1. File System Connector

Indexes local files in various formats.

**Configuration:**
```toml
[sources.files]
path = "./documents"              # Directory to index
file_patterns = ["*.md", "*.pdf"] # Optional: specific patterns
exclude_patterns = [".*", "__*"]  # Optional: exclude patterns
```

**Pydantic Model:**
```python
class LocalFilesConfig(BaseModel):
    path: Path  # Required
    file_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
```

**Supported Formats:**
- PDF, DOCX, PPTX (via Unstructured)
- Markdown, plain text
- CSV, JSON
- 20+ formats total

**Reader Behavior:**
- Recursively walks directory
- Applies include/exclude patterns
- Yields one file per raw document
- Preserves file path and modification time

**Converter Behavior:**
- Parses document content via Unstructured
- Chunks by paragraph
- Preserves file path in metadata

**Example:**
```python
from connectors import FileSystemConnector
from connectors.files.schema import LocalFilesConfig

config = LocalFilesConfig(path="./docs")
connector = FileSystemConnector(config)

# Read documents
for raw_doc in connector.reader.read_all_documents():
    print(f"File: {raw_doc.source}")
    print(f"Content: {raw_doc.text[:100]}...")

# Convert to chunks
chunks = connector.converter.convert(raw_doc)
for chunk in chunks:
    print(f"Chunk: {chunk.text[:100]}...")
```

### 2. Jira Connector (Server & Cloud)

Indexes Jira issues with full metadata.

**Configuration (Server/DC):**
```toml
[sources.jira]
url = "https://jira.company.com"
username = "user@company.com"
api_token = "secret_token"       # Via environment or .env
jql = "project = MYPROJ AND type != Sub-task"
include_comments = true
include_attachments = true
```

**Configuration (Cloud):**
```toml
[sources.jira]
url = "https://company.atlassian.net"
email = "user@company.com"
api_token = "secret_token"       # Via environment or .env
jql = "project = MYPROJ"
include_comments = true
include_attachments = true
```

**Pydantic Models:**
```python
class JiraConfig(BaseModel):
    url: str
    username: str
    api_token: str  # Sensitive: routed to .env
    jql: str | None = None
    include_comments: bool = False
    include_attachments: bool = False

class JiraCloudConfig(BaseModel):
    url: str
    email: str
    api_token: str  # Sensitive: routed to .env
    jql: str | None = None
    include_comments: bool = False
    include_attachments: bool = False
```

**Reader Behavior:**
- Queries Jira API using JQL
- Fetches issue metadata, description, comments
- Downloads attachments if configured
- Handles pagination and rate limiting
- Caches responses for efficiency

**Converter Behavior:**
- Combines issue title + description
- Includes issue key and URL in metadata
- Splits issue comments into separate chunks
- Extracts text from attachments
- Preserves all metadata (assignee, status, labels, etc.)

**Example:**
```python
from connectors import JiraCloudConnector
from connectors.jira.schema import JiraCloudConfig

config = JiraCloudConfig(
    url="https://company.atlassian.net",
    email="user@company.com",
    api_token="token_from_env",
    jql="project = DOCS",
    include_comments=True,
)
connector = JiraCloudConnector(config)

# Read issues
for issue in connector.reader.read_all_documents():
    print(f"Key: {issue.metadata['key']}")
    print(f"Title: {issue.metadata['title']}")

# Convert to chunks
chunks = connector.converter.convert(issue)
for chunk in chunks:
    print(f"Chunk: {chunk.text[:100]}...")
    print(f"Source: {chunk.metadata['url']}")
```

### 3. Confluence Connector (Server & Cloud)

Indexes Confluence pages with hierarchy.

**Configuration (Server/DC):**
```toml
[sources.confluence]
url = "https://confluence.company.com"
username = "user@company.com"
api_token = "secret_token"       # Via environment or .env
space_key = "DOCS"               # Optional: specific space
include_comments = true
include_attachments = true
```

**Configuration (Cloud):**
```toml
[sources.confluence]
url = "https://company.atlassian.net/wiki"
email = "user@company.com"
api_token = "secret_token"       # Via environment or .env
space_key = "DOCS"               # Optional: specific space
include_comments = true
include_attachments = true
```

**Pydantic Models:**
```python
class ConfluenceConfig(BaseModel):
    url: str
    username: str
    api_token: str  # Sensitive: routed to .env
    space_key: str | None = None
    include_comments: bool = False
    include_attachments: bool = False

class ConfluenceCloudConfig(BaseModel):
    url: str
    email: str
    api_token: str  # Sensitive: routed to .env
    space_key: str | None = None
    include_comments: bool = False
    include_attachments: bool = False
```

**Reader Behavior:**
- Queries Confluence using CQL (Confluence Query Language)
- Fetches page hierarchy
- Downloads attachments if configured
- Handles pagination
- Preserves page relationships

**Converter Behavior:**
- Extracts page title and content
- Chunks by section or paragraph
- Preserves hierarchical information (parent page, space)
- Includes page URL and metadata
- Processes comments as separate chunks

**Example:**
```python
from connectors import ConfluenceCloudConnector
from connectors.confluence.schema import ConfluenceCloudConfig

config = ConfluenceCloudConfig(
    url="https://company.atlassian.net/wiki",
    email="user@company.com",
    api_token="token_from_env",
    space_key="DOCS",
    include_comments=True,
)
connector = ConfluenceCloudConnector(config)

# Read pages
for page in connector.reader.read_all_documents():
    print(f"Title: {page.metadata['title']}")
    print(f"Space: {page.metadata['space_key']}")

# Convert to chunks
chunks = connector.converter.convert(page)
for chunk in chunks:
    print(f"Chunk: {chunk.text[:100]}...")
    print(f"URL: {chunk.metadata['url']}")
```

## Data Models

### RawDocument

Output of DocumentReader:

```python
class RawDocument:
    """Raw document from source."""
    id: str                    # Unique identifier
    source: str                # Source URL or file path
    text: str                  # Full document text
    metadata: dict[str, Any]   # Source-specific metadata
```

### DocumentChunk

Output of DocumentConverter:

```python
class DocumentChunk:
    """Chunk ready for indexing."""
    id: str                    # Unique chunk identifier
    document_id: str           # Reference to source document
    text: str                  # Chunk text content
    sequence: int              # Sequence within document (0-indexed)
    metadata: dict[str, Any]   # Enriched metadata
```

## Reader & Converter Pattern

Each connector separates concerns into two components:

### DocumentReader

Fetches raw documents from source (iterator-based for memory efficiency):

```python
from typing import Iterator

class DocumentReader(Protocol):
    """Protocol for reading documents from a source."""

    def read_all_documents(self) -> Iterator[RawDocument]:
        """Read all documents from source, yielding one at a time."""
        ...
```

**Benefits:**
- Memory efficient (streams, doesn't load all at once)
- Can handle large result sets
- Easy to add caching/retry logic
- Testable in isolation

### DocumentConverter

Transforms raw documents to searchable chunks:

```python
from typing import Iterator

class DocumentConverter(Protocol):
    """Protocol for converting documents to chunks."""

    def convert(self, raw_doc: RawDocument) -> Iterator[DocumentChunk]:
        """Convert raw document to chunks, yielding one at a time."""
        ...
```

**Benefits:**
- Separates parsing from fetching
- Easy to customize chunking strategy
- Can apply different chunking per source type
- Testable in isolation

## Creating Custom Connectors

To add a new connector:

### Step 1: Define Configuration Model

```python
# custom/schema.py
from pydantic import BaseModel, Field

class CustomSourceConfig(BaseModel):
    """Configuration for custom source."""
    api_url: str = Field(..., description="API endpoint")
    api_key: str = Field(..., description="API authentication key")
    # More config fields...
```

### Step 2: Implement Reader

```python
# custom/custom_document_reader.py
from typing import Iterator
from connectors.models import RawDocument

class CustomDocumentReader:
    """Reader for custom source."""

    def __init__(self, config: CustomSourceConfig):
        self.config = config
        self.client = self._init_client()

    def _init_client(self):
        """Initialize API client."""
        # Setup authentication, etc.
        pass

    def read_all_documents(self) -> Iterator[RawDocument]:
        """Read documents from custom source."""
        for page in self.client.list_documents():
            for item in page:
                yield RawDocument(
                    id=item['id'],
                    source=item['url'],
                    text=item['content'],
                    metadata={
                        'title': item['title'],
                        'updated_at': item['updated_at'],
                    }
                )
```

### Step 3: Implement Converter

```python
# custom/custom_document_converter.py
from typing import Iterator
from connectors.models import RawDocument, DocumentChunk

class CustomDocumentConverter:
    """Converter for custom source."""

    def __init__(self, config: CustomSourceConfig):
        self.config = config

    def convert(self, raw_doc: RawDocument) -> Iterator[DocumentChunk]:
        """Convert raw document to chunks."""
        # Split text into chunks
        chunks = self._chunk_text(raw_doc.text, chunk_size=512)

        for i, chunk_text in enumerate(chunks):
            yield DocumentChunk(
                id=f"{raw_doc.id}_chunk_{i}",
                document_id=raw_doc.id,
                text=chunk_text,
                sequence=i,
                metadata={
                    **raw_doc.metadata,
                    'chunk_sequence': i,
                    'source': raw_doc.source,
                }
            )

    def _chunk_text(self, text: str, chunk_size: int) -> list[str]:
        """Split text into chunks."""
        # Implementation...
        pass
```

### Step 4: Implement Connector

```python
# custom/connector.py
from connectors.base import BaseConnector
from .schema import CustomSourceConfig
from .custom_document_reader import CustomDocumentReader
from .custom_document_converter import CustomDocumentConverter

class CustomConnector:
    """Connector for custom source."""

    def __init__(self, config: CustomSourceConfig):
        self._config = config
        self._reader = CustomDocumentReader(config)
        self._converter = CustomDocumentConverter(config)

    @property
    def reader(self) -> CustomDocumentReader:
        return self._reader

    @property
    def converter(self) -> CustomDocumentConverter:
        return self._converter

    @property
    def connector_type(self) -> str:
        return "custom"
```

### Step 5: Register Connector

```python
# custom/__init__.py
from .connector import CustomConnector
from .schema import CustomSourceConfig

__all__ = ["CustomConnector", "CustomSourceConfig"]
```

Then register in the registry:

```python
# connectors/registry.py
CONNECTOR_REGISTRY = {
    "custom": ("connectors.custom", "CustomConnector", "CustomSourceConfig", "sources.custom"),
    # ... other connectors
}
```

## Caching & Performance

### Document Cache Decorator

The package provides a caching decorator for readers to avoid re-fetching:

```python
from connectors.document_cache_reader_decorator import CachedDocumentReader

def read_all_documents() -> Iterator[RawDocument]:
    # This can be expensive - make it cacheable
    pass

# Wrap with caching
cached_reader = CachedDocumentReader(
    delegate_reader=self,
    cache_dir="~/.indexed/caches",
    ttl_seconds=3600,  # 1 hour cache
)

# Reads use cache if available
for doc in cached_reader.read_all_documents():
    yield doc
```

### Batch Processing

For APIs with pagination/rate limits:

```python
from utils import execute_with_retry, read_items_in_batches

def read_all_documents(self) -> Iterator[RawDocument]:
    # Use utils for batching and retrying
    for items_batch in read_items_in_batches(
        fetch_fn=self.client.list_items,
        batch_size=100,
    ):
        for item in items_batch:
            yield RawDocument(...)
```

## Error Handling

### Graceful Degradation

Connectors should handle errors gracefully:

```python
def read_all_documents(self) -> Iterator[RawDocument]:
    for item in self.client.list_items():
        try:
            yield RawDocument(
                id=item['id'],
                source=item['url'],
                text=item['content'],
                metadata=item.get('metadata', {}),
            )
        except Exception as e:
            logger.warning(f"Failed to read item {item['id']}: {e}")
            # Continue with next item instead of failing entire read
            continue
```

### Rate Limiting

Use exponential backoff for API rate limits:

```python
from utils import execute_with_retry

def fetch_item(self, item_id: str):
    return execute_with_retry(
        fn=lambda: self.client.get_item(item_id),
        max_attempts=3,
        base_delay=1.0,  # Start at 1 second
        backoff_multiplier=2.0,  # Double each retry
    )
```

## Testing Connectors

### Unit Testing Reader

```python
from unittest.mock import MagicMock
from connectors.custom.custom_document_reader import CustomDocumentReader
from connectors.custom.schema import CustomSourceConfig

def test_reader_yields_documents():
    """Test that reader yields documents from API."""
    config = CustomSourceConfig(
        api_url="https://api.example.com",
        api_key="test_key",
    )

    reader = CustomDocumentReader(config)
    reader.client = MagicMock()
    reader.client.list_documents.return_value = [
        [{"id": "1", "content": "test", "url": "http://example.com/1"}]
    ]

    docs = list(reader.read_all_documents())

    assert len(docs) == 1
    assert docs[0].id == "1"
```

### Unit Testing Converter

```python
from connectors.custom.custom_document_converter import CustomDocumentConverter
from connectors.models import RawDocument

def test_converter_creates_chunks():
    """Test that converter splits document into chunks."""
    config = CustomSourceConfig(...)
    converter = CustomDocumentConverter(config)

    raw_doc = RawDocument(
        id="doc-1",
        source="http://example.com",
        text="Very long text " * 1000,
        metadata={"title": "Test"},
    )

    chunks = list(converter.convert(raw_doc))

    assert len(chunks) > 1
    assert all(len(c.text) <= 512 for c in chunks)
    assert all(c.document_id == "doc-1" for c in chunks)
```

## Performance Characteristics

### File System Connector
- **Speed:** Very fast (local I/O only)
- **Memory:** Low (streams files)
- **Scalability:** Excellent (handles 100K+ files)

### Jira Connector
- **Speed:** Medium (depends on network, issue count)
- **Memory:** Low (pagination limits in-memory size)
- **Scalability:** Good (tested with 10K+ issues)

### Confluence Connector
- **Speed:** Medium (depends on network, page count)
- **Memory:** Low (pagination and caching)
- **Scalability:** Good (tested with 50K+ pages)

## Related Documentation

- **[Root CURSOR.md](../../CURSOR.md)** - Project overview
- **[Core Engine CURSOR.md](../../packages/indexed-core/CURSOR.md)** - Engine architecture
- **[Configuration CURSOR.md](../../packages/indexed-config/CURSOR.md)** - Config system
- **[Utilities CURSOR.md](../../packages/utils/CURSOR.md)** - Utilities
- **[.cursor/rules/tech/architecture.mdc](../../.cursor/rules/tech/architecture.mdc)** - Full architecture

---

**Last Updated:** January 24, 2026
