# indexed-core

Core library for document indexing and semantic search using FAISS and sentence-transformers.

## Overview

`indexed-core` provides the foundational components for building searchable document collections with vector similarity search. It handles document indexing, embedding generation, and semantic search operations across multiple document sources.

## Features

| Feature | Description |
|---------|-------------|
| **Document Indexing** | Create searchable collections from various sources |
| **Semantic Search** | Vector similarity search using FAISS |
| **Embeddings** | Local embedding generation with sentence-transformers |
| **Collection Management** | Create, update, inspect, and delete collections |
| **Persistent Storage** | Disk-based storage with atomic operations |
| **Multiple Indexers** | Support for different FAISS index types |

## Installation

This package is part of the indexed monorepo workspace. Requires **Python 3.11+**.

```bash
# Install with workspace
uv sync

# Or standalone (for development)
cd packages/indexed-core
uv pip install -e .
```

## Usage

### Simple API (Index Class)

The `Index` class provides a clean, high-level interface:

```python
from core.v1 import Index
from connectors import FileSystemConnector, JiraCloudConnector

# Create index
index = Index()

# Add a file system collection
files = FileSystemConnector(path="./docs")
index.add_collection("docs", files)

# Add a Jira collection
jira = JiraCloudConnector(
    url="https://company.atlassian.net",
    query="project = PROJ",
    email="user@example.com",
    api_token="token",
)
index.add_collection("jira-issues", jira)

# Search across all collections
results = index.search("How do I configure authentication?")

# Search specific collection
results = index.search("bug in login", collection="jira-issues", max_results=5)

# Update collections
index.update("docs")  # Update specific collection
index.update()        # Update all collections

# Check status
all_status = index.status()
docs_status = index.status("docs")
print(f"Documents: {docs_status.number_of_documents}")
print(f"Chunks: {docs_status.number_of_chunks}")

# List and remove collections
print(index.list_collections())
index.remove("old-collection")
```

### Service Layer API

For more control, use the service layer directly:

```python
from core.v1.engine.services import (
    search,
    update,
    status,
    clear,
    SourceConfig,
)

# Search across all collections
results = search("authentication methods", max_docs=10, max_chunks=30)

# Search specific collection
config = SourceConfig(
    name="docs",
    type="files",
    base_url_or_path="./docs",
    indexer="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
)
results = search("query", configs=[config])

# Get collection statuses
all_statuses = status()
specific_status = status(["docs", "jira"])

# Clear collections
clear(["old-collection"])
```

### Factory API (Low-Level)

For complete control over indexing:

```python
from core.v1.engine.factories.create_collection_factory import create_collection_creator
from connectors import FileSystemConnector

# Create connector
connector = FileSystemConnector(path="./docs")

# Create collection using factory
creator = create_collection_creator(
    collection_name="docs",
    indexers=["indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"],
    document_reader=connector.reader,
    document_converter=connector.converter,
    use_cache=True,
)
creator.run()
```

## Architecture

### Core Components

```
indexed-core/
├── src/core/
│   └── v1/
│       ├── index.py              # High-level Index class
│       ├── connectors/           # Connector protocol definitions
│       │   ├── base.py          # BaseConnector protocol
│       │   └── metadata.py      # Connector metadata
│       │
│       └── engine/
│           ├── core/            # Document processing
│           │   ├── documents_collection_creator.py
│           │   └── documents_collection_searcher.py
│           │
│           ├── factories/       # Factory pattern for creation
│           │   ├── create_collection_factory.py
│           │   ├── search_collection_factory.py
│           │   └── update_collection_factory.py
│           │
│           ├── indexes/         # FAISS indexing
│           │   ├── embeddings/  # Sentence embeddings
│           │   ├── indexers/    # FAISS indexer implementations
│           │   └── indexer_factory.py
│           │
│           ├── persisters/      # Storage layer
│           │   └── disk_persister.py
│           │
│           └── services/        # Service layer API
│               ├── collection_service.py
│               ├── search_service.py
│               ├── inspect_service.py
│               └── models.py
```

### Connector Protocol

All document sources implement the `BaseConnector` protocol:

```python
from typing import Protocol

class BaseConnector(Protocol):
    @property
    def reader(self) -> DocumentReader:
        """Returns document reader for fetching documents."""
        ...

    @property
    def converter(self) -> DocumentConverter:
        """Returns converter for format transformation."""
        ...

    @property
    def connector_type(self) -> str:
        """Returns type identifier (e.g., 'jira', 'files')."""
        ...
```

### Indexer Configuration

Default indexer: `indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2`

Available components:
- **FAISS Index Types**: `IndexFlatL2`, `IndexFlatIP`
- **Embedding Models**: `all-MiniLM-L6-v2` (default), other sentence-transformer models

### Search Results

```python
# Results structure
{
    "collection_name": {
        "documents": [
            {
                "id": "doc-123",
                "title": "Authentication Guide",
                "content": "...",
                "metadata": {...},
            }
        ],
        "chunks": [
            {
                "document_id": "doc-123",
                "text": "Matched text chunk...",
                "score": 0.87,
            }
        ],
    }
}
```

### Collection Status

```python
from core.v1.engine.services import status

statuses = status()
for s in statuses:
    print(f"Collection: {s.name}")
    print(f"  Documents: {s.number_of_documents}")
    print(f"  Chunks: {s.number_of_chunks}")
    print(f"  Indexers: {s.indexers}")
    print(f"  Last Updated: {s.last_updated}")
```

## Storage

Collections are stored in the configured data directory:

```
~/.indexed/data/               # or ./.indexed/data/ for local mode
└── collections/
    └── <collection-name>/
        ├── manifest.json      # Collection metadata
        ├── documents.json     # Document metadata
        ├── chunks.json        # Chunked text data
        └── index.faiss        # FAISS vector index
```

## Dependencies

| Package | Purpose |
|---------|---------|
| **indexed-connectors** | Document source connectors |
| **indexed-utils** | Shared utilities |
| **faiss-cpu** | Vector similarity search |
| **sentence-transformers** | Text embedding generation |
| **langchain** | Text splitting and processing |
| **pydantic** | Configuration validation |
| **llama-index** | RAG query engine (optional) |

## Development

### Running Tests

```bash
# Run core tests
uv run pytest tests/packages/indexed-core -v

# Run specific test
uv run pytest tests/packages/indexed-core/test_documents_collection_creator.py -v

# With coverage
uv run pytest tests/packages/indexed-core --cov=core
```

### Code Quality

```bash
# Format
uv run ruff format packages/indexed-core/

# Lint
uv run ruff check packages/indexed-core/

# Type check
uv run mypy packages/indexed-core/src/
```

## License

See LICENSE file in the project root.
