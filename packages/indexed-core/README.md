# indexed-core

Core library for document indexing and semantic search using FAISS and sentence-transformers.

## Overview

`indexed-core` provides the foundational components for building searchable document collections with vector similarity search. It handles document indexing, embedding generation, and semantic search operations across multiple document sources.

## Features

- **Document Indexing** - Create searchable collections from various sources (Jira, Confluence, local files)
- **Semantic Search** - Vector similarity search using FAISS with sentence-transformers embeddings
- **Configuration Management** - Flexible config system with profiles, environment variables, and TOML support
- **Collection Management** - Create, update, inspect, and delete document collections
- **Multiple Indexers** - Support for different FAISS index types and embedding models
- **Persistent Storage** - Disk-based storage for collections and indexes with atomic operations

## Architecture

### Core Components

- **Services** - High-level API for collection, search, inspect, and config operations
- **Factories** - Factory pattern for creating readers, converters, and indexers
- **Indexes** - FAISS-based vector indexing with sentence-transformers embeddings
- **Persisters** - Disk-based storage for collections and indexes
- **Config** - Pydantic-based configuration with TOML support and validation

### Configuration

Configuration is managed via multiple sources with the following precedence (highest to lowest):

1. Runtime overrides (programmatic)
2. Environment variables (prefix: `INDEXED__`)
3. `.env` file
4. `indexed.toml` in project root
5. Built-in defaults

## Usage

### Simple API (v1)

```python
from core.v1 import Index
from connectors import FileSystemConnector

# Create index
index = Index()

# Add a collection
connector = FileSystemConnector(path="./docs")
index.add_collection("docs", connector)

# Search
results = index.search("How do I configure authentication?")
```

### Service Layer API

```python
from core.v1.engine.services import create, search, status
from core.v1.engine.services.models import SourceConfig

# Define source configuration
config = SourceConfig(
    name="my-docs",
    type="localFiles",
    base_url_or_path="./docs",
    indexer="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"
)

# Create collection
create([config])

# Search across collections
results = search("authentication methods", max_docs=10)

# Check status
statuses = status()
```

## Dependencies

- **indexed-connectors** - Document readers for Jira, Confluence, and file systems
- **indexed-utils** - Shared utilities (logging, retry, batching, progress)
- **FAISS** - Vector similarity search
- **sentence-transformers** - Text embeddings
- **LangChain** - Text splitting and processing
- **Pydantic** - Configuration validation

## Development

This package is part of the indexed monorepo workspace. Use `uv` for dependency management:

```bash
# Install dependencies
uv sync --all-groups

# Run tests
uv run pytest packages/indexed-core
```

## License

See LICENSE file in the project root.
