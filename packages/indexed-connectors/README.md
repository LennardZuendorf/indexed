# indexed-connectors

Document connectors for Jira, Confluence, and local file systems with support for both Cloud and Server/Data Center versions.

## Overview

`indexed-connectors` provides standardized connector classes for ingesting documents from various sources. All connectors implement the `BaseConnector` protocol from `indexed-core`, ensuring seamless interoperability with the indexing framework.

## Supported Sources

| Connector | Type Key | Description |
|-----------|----------|-------------|
| `FileSystemConnector` | `files` | Local files and directories |
| `JiraConnector` | `jira` | Jira Server/Data Center |
| `JiraCloudConnector` | `jiraCloud` | Jira Cloud (Atlassian hosted) |
| `ConfluenceConnector` | `confluence` | Confluence Server/Data Center |
| `ConfluenceCloudConnector` | `confluenceCloud` | Confluence Cloud (Atlassian hosted) |

### File System Connector

Supports multiple document formats via [Unstructured](https://github.com/Unstructured-IO/unstructured):

| Category | Formats |
|----------|---------|
| **Text** | `.txt`, `.md`, `.rst` |
| **Documents** | `.pdf`, `.docx`, `.pptx`, `.odt` |
| **Code** | `.py`, `.js`, `.java`, `.go`, etc. |
| **Data** | `.csv`, `.json`, `.yaml`, `.xml`, `.parquet` |

**Features:**
- Regex-based include/exclude filtering
- Rich file metadata: path, size, timestamps, checksums
- Automatic format detection

### Jira Connectors

**Features:**
- JQL-based issue filtering
- Full issue metadata, fields, and comments
- Attachment download and indexing
- Author and timestamp tracking
- Robust pagination handling

### Confluence Connectors

**Features:**
- CQL-based page and space filtering
- Full page content with HTML parsing
- Hierarchical comment support (nested comments, authors, timestamps)
- Ancestor hierarchy tracking
- Attachment handling

## Installation

This package is part of the indexed monorepo workspace. Requires **Python 3.11+**.

```bash
# Install with workspace
uv sync

# Or standalone (for development)
cd packages/indexed-connectors
uv pip install -e .
```

## Usage

### File System Connector

```python
from connectors import FileSystemConnector

# Basic usage
connector = FileSystemConnector(path="./docs")

# With filtering
connector = FileSystemConnector(
    path="./docs",
    include_patterns=[r".*\.md$", r".*\.txt$"],
    exclude_patterns=[r".*/node_modules/.*", r".*\.min\.js$"],
)

# From configuration
from indexed_config import ConfigService

config = ConfigService.instance()
connector = FileSystemConnector.from_config(config, "sources.docs")
```

### Jira Cloud Connector

```python
from connectors import JiraCloudConnector

connector = JiraCloudConnector(
    url="https://company.atlassian.net",
    query="project = PROJ AND updated >= -90d",
    email="user@example.com",
    api_token="your-token",
    include_attachments=True,
)
```

### Jira Server/DC Connector

```python
from connectors import JiraConnector

connector = JiraConnector(
    url="https://jira.company.com",
    query="project = PROJ",
    token="bearer-token",  # or use login/password
)
```

### Confluence Cloud Connector

```python
from connectors import ConfluenceCloudConnector

connector = ConfluenceCloudConnector(
    url="https://company.atlassian.net/wiki",
    query="space = DEV",
    email="user@example.com",
    api_token="your-token",
    read_all_comments=True,
    include_attachments=False,
)
```

### Confluence Server/DC Connector

```python
from connectors import ConfluenceConnector

connector = ConfluenceConnector(
    url="https://confluence.company.com",
    query="space = DEV",
    token="bearer-token",  # or use login/password
)
```

### Using with Core Index

```python
from core.v1 import Index
from connectors import FileSystemConnector

index = Index()
connector = FileSystemConnector(path="./docs")
index.add_collection("my-docs", connector)
```

### Dynamic Connector Registry

```python
from connectors import (
    get_connector_class,
    get_config_class,
    list_connector_types,
)

# List available types
types = list_connector_types()
# ['files', 'jira', 'jiraCloud', 'confluence', 'confluenceCloud']

# Get connector class by type
ConnectorClass = get_connector_class("jiraCloud")

# Get config schema class
ConfigClass = get_config_class("jiraCloud")
```

## Connector Protocol

All connectors implement the `BaseConnector` protocol:

```python
class BaseConnector(Protocol):
    @property
    def reader(self) -> DocumentReader:
        """Document reader instance for fetching documents."""
        ...

    @property
    def converter(self) -> DocumentConverter:
        """Document converter for format transformation."""
        ...

    @property
    def connector_type(self) -> str:
        """String identifier (e.g., 'jira', 'confluence', 'files')."""
        ...
```

### Configuration Integration

Connectors support configuration-driven instantiation:

```python
# Define config spec
@classmethod
def config_spec(cls) -> Dict[str, Dict[str, Any]]:
    return {
        "url": {
            "type": "str",
            "required": True,
            "description": "Service base URL"
        },
        "api_token_env": {
            "type": "str",
            "required": False,
            "secret": True,
            "default": "ATLASSIAN_TOKEN",
            "description": "Env var containing API token"
        }
    }

# Create from config service
@classmethod
def from_config(cls, config_service, namespace: str) -> "Connector":
    ...
```

## Authentication

### Atlassian Cloud (Jira/Confluence)

Use email + API token:

```python
connector = JiraCloudConnector(
    url="https://company.atlassian.net",
    email="user@example.com",
    api_token="your-api-token",  # From https://id.atlassian.com/manage/api-tokens
    query="project = PROJ",
)
```

### Server/Data Center (Jira/Confluence)

**Bearer Token (recommended):**

```python
connector = JiraConnector(
    url="https://jira.company.com",
    token="bearer-token",
    query="project = PROJ",
)
```

**Basic Auth:**

```python
connector = JiraConnector(
    url="https://jira.company.com",
    login="username",
    password="password",
    query="project = PROJ",
)
```

## Project Structure

```
indexed-connectors/
├── src/connectors/
│   ├── __init__.py              # Package exports
│   ├── registry.py              # Dynamic connector registry
│   ├── document_cache_reader_decorator.py
│   │
│   ├── files/
│   │   ├── connector.py         # FileSystemConnector
│   │   ├── files_document_reader.py
│   │   ├── files_document_converter.py
│   │   └── schema.py           # Pydantic config schema
│   │
│   ├── jira/
│   │   ├── connector.py         # JiraConnector, JiraCloudConnector
│   │   ├── jira_document_reader.py
│   │   ├── jira_document_converter.py
│   │   ├── jira_cloud_document_reader.py
│   │   ├── jira_cloud_document_converter.py
│   │   ├── unified_jira_document_reader.py
│   │   ├── unified_jira_document_converter.py
│   │   └── schema.py
│   │
│   └── confluence/
│       ├── connector.py         # ConfluenceConnector, ConfluenceCloudConnector
│       ├── confluence_document_reader.py
│       ├── confluence_document_converter.py
│       ├── confluence_cloud_document_reader.py
│       ├── confluence_cloud_document_converter.py
│       └── schema.py
│
├── pyproject.toml
└── README.md
```

## Dependencies

| Package | Purpose |
|---------|---------|
| **indexed-utils** | Shared utilities (retry, batching, logging) |
| **requests** | HTTP client for API calls |
| **beautifulsoup4** | HTML parsing for Confluence pages |
| **langchain** | Text splitting and chunking |
| **unstructured** | Multi-format document parsing |
| **atlassian-python-api** | Atlassian API client |

## Development

### Running Tests

```bash
# Run connector tests
uv run pytest tests/packages/indexed-connectors -v

# Run specific connector
uv run pytest tests/packages/indexed-connectors/jira -v

# With coverage
uv run pytest tests/packages/indexed-connectors --cov=connectors
```

### Code Quality

```bash
# Format
uv run ruff format packages/indexed-connectors/

# Lint
uv run ruff check packages/indexed-connectors/

# Type check
uv run mypy packages/indexed-connectors/src/
```

## License

See LICENSE file in the project root.
