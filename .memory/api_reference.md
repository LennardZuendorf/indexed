# API Reference - Core V1

## Overview

The Indexed V1 API provides a collection-based document indexing and search system. One `Index` manages multiple named collections (e.g., "jira", "docs", "confluence"), each searchable individually or collectively.

## Core Classes

### Index

Main entry point for managing collections and searching.

```python
from core.v1 import Index, Config

config = Config.from_file("indexed.toml")
index = Index(config)
```

#### Methods

**`add_collection(connector, name: str, **kwargs) -> CollectionStats`**
```python
# Add a collection using a connector
from core.v1.connectors import FileSystemConnector, JiraConnector

files = FileSystemConnector('./docs')
stats = index.add_collection(files, name="docs")

jira = JiraConnector(config)
stats = index.add_collection(jira, name="jira")
```

**`search(query: str, collection: str | None = None, top_k: int = 10) -> List[SearchResult]`**
```python
# Search all collections
results = index.search("authentication methods")

# Search specific collection
results = index.search(query="What was project xyz?", collection="jira")

# Limit results
results = index.search("query", top_k=5)
```

**`update(collection: str) -> UpdateStats`**
```python
# Re-index a collection (detects changes)
stats = index.update("jira")
```

**`remove_collection(name: str) -> None`**
```python
# Remove a collection completely
index.remove_collection("docs")
```

**`list_collections() -> List[str]`**
```python
# Get list of all collection names
collections = index.list_collections()  # ["jira", "docs", "confluence"]
```

**`inspect(collection: str | None = None) -> IndexStats`**
```python
# Get stats for all collections
stats = index.inspect()

# Get stats for specific collection
stats = index.inspect(collection="jira")
```

---

### Config

Configuration management with versioned TOML support.

```python
from core.v1 import Config

# Load from file (reads [indexer.v1] section)
config = Config.from_file("indexed.toml")

# Create with defaults
config = Config()

# Override specific values
config = Config(
    embedding_model="all-MiniLM-L6-v2",
    storage_path=".indexed/v1",
    chunk_size=512
)
```

#### Configuration File Structure

```toml
# indexed.toml
[indexer.v1]
embedding_model = "all-MiniLM-L6-v2"
storage_path = ".indexed/v1"
chunk_size = 512
chunk_overlap = 50

# Jira connector config
[indexer.v1.jira]
url = "https://jira.example.com"
token = "your-token"
query = "project = MYPROJECT"

# Confluence connector config
[indexer.v1.confluence]
url = "https://confluence.example.com"
token = "your-token"
space = "MYSPACE"
```

---

### Connectors

Document source connectors.

```python
from core.v1.connectors import (
    FileSystemConnector,
    JiraConnector,
    ConfluenceConnector
)
```

**`FileSystemConnector(path: str, **kwargs)`**
```python
connector = FileSystemConnector(
    path='./docs',
    patterns=['*.md', '*.txt'],  # Optional file patterns
    recursive=True               # Optional recursion
)
```

**`JiraConnector(config: Config, **kwargs)`**
```python
# Uses config from [indexer.v1.jira] section
connector = JiraConnector(config)

# Or override
connector = JiraConnector(
    config,
    url="https://jira.example.com",
    query="project = MYPROJECT AND created >= -30d"
)
```

**`ConfluenceConnector(config: Config, **kwargs)`**
```python
# Uses config from [indexer.v1.confluence] section
connector = ConfluenceConnector(config)

# Or override
connector = ConfluenceConnector(
    config,
    url="https://confluence.example.com",
    space="MYSPACE"
)
```

---

## Complete Usage Examples

### Basic Usage

```python
from core.v1 import Index, Config
from core.v1.connectors import FileSystemConnector

# Initialize
config = Config.from_file("indexed.toml")
index = Index(config)

# Add a collection
docs = FileSystemConnector('./my-docs')
index.add_collection(docs, name="docs")

# Search
results = index.search("How do I authenticate?")

for result in results:
    print(f"{result.title}: {result.snippet}")
    print(f"Score: {result.score}, Collection: {result.collection}")
```

### Multi-Collection Setup

```python
from core.v1 import Index, Config
from core.v1.connectors import FileSystemConnector, JiraConnector, ConfluenceConnector

# Initialize
config = Config.from_file("indexed.toml")
index = Index(config)

# Add multiple collections
index.add_collection(FileSystemConnector('./docs'), name="docs")
index.add_collection(JiraConnector(config), name="jira")
index.add_collection(ConfluenceConnector(config), name="confluence")

# List all collections
print(index.list_collections())  # ["docs", "jira", "confluence"]

# Search all
all_results = index.search("authentication")

# Search specific collection
jira_results = index.search("authentication", collection="jira")

# Get stats
overall_stats = index.inspect()
jira_stats = index.inspect(collection="jira")
```

### Update Workflow

```python
from core.v1 import Index, Config

# Load existing index
config = Config.from_file("indexed.toml")
index = Index(config)

# Update specific collection (re-reads and re-embeds changes)
stats = index.update("jira")
print(f"Updated {stats.documents_updated} documents")

# Remove old collection
index.remove_collection("old-docs")

# Add new collection
from core.v1.connectors import FileSystemConnector
index.add_collection(FileSystemConnector('./new-docs'), name="new-docs")
```

---

## Data Models

### SearchResult

```python
class SearchResult:
    title: str              # Document title
    snippet: str            # Relevant text snippet
    score: float            # Similarity score (0-1)
    collection: str         # Source collection name
    document_id: str        # Unique document ID
    metadata: dict          # Additional metadata
```

### IndexStats

```python
class IndexStats:
    total_documents: int
    total_chunks: int
    collections: dict[str, CollectionStats]  # Per-collection stats
    storage_size_bytes: int
    last_updated: datetime
```

### CollectionStats

```python
class CollectionStats:
    name: str
    document_count: int
    chunk_count: int
    last_updated: datetime
    connector_type: str
```

---

## CLI Commands

See the CLI for user-friendly commands built on this API:

```bash
# Collection management
indexed-cli add files ./docs --name docs
indexed-cli add jira --name jira
indexed-cli list
indexed-cli remove docs

# Search
indexed-cli search "query"
indexed-cli search "query" --collection jira

# Maintenance
indexed-cli update jira
indexed-cli inspect
indexed-cli inspect --collection docs
```

---

## Version Information

**API Version**: v1  
**Storage Path**: `.indexed/v1/`  
**Config Section**: `[indexer.v1]`  

Future versions (v2, v3) will coexist without conflicts.