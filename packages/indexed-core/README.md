# indexed-core

Core library for document indexing and semantic search with FAISS and sentence-transformers.

## Features

- **Document Indexing** - Create searchable collections from various sources
- **Semantic Search** - Vector similarity search using FAISS
- **Configuration Management** - Flexible config system with profiles and environment variables
- **Collection Management** - Create, update, inspect, and delete document collections
- **Multiple Sources** - Support for Jira, Confluence, and local files via connectors

## Architecture

### Core Components

- **Services** - High-level API for collection, search, inspect, and config operations
- **Factories** - Factory pattern for creating readers, converters, and indexers
- **Indexes** - FAISS-based vector indexing with sentence-transformers embeddings
- **Persisters** - Disk-based storage for collections and indexes
- **Config** - Pydantic-based configuration with TOML support

### Configuration

Configuration is managed via:
1. `indexed.toml` in project root
2. Environment variables (prefix: `INDEXED__`)
3. `.env` file
4. Runtime overrides

## Dependencies

- **indexed-connectors** - Document readers for various sources
- **indexed-utils** - Shared utilities (logging, retry, batching, progress)
- External: FAISS, sentence-transformers, LangChain, Pydantic
