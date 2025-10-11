# indexed-connectors

Document connectors for reading and indexing content from various sources including Jira, Confluence, and local file systems.

## Overview

`indexed-connectors` provides a standardized interface for discovering, reading, and converting documents from different sources. All connectors implement the `BaseConnector` protocol, making them interchangeable and easy to use with the indexed-core library.

## Supported Sources

### Jira
- **Jira Server/Data Center** - Self-hosted Jira instances
- **Jira Cloud** - Atlassian-hosted Jira

Both support:
- JQL-based issue filtering
- Token or username/password authentication
- Issue metadata and comments
- Automatic pagination

### Confluence
- **Confluence Server/Data Center** - Self-hosted Confluence instances
- **Confluence Cloud** - Atlassian-hosted Confluence

Both support:
- CQL-based page filtering
- Token or username/password authentication
- Page content and hierarchical comments
- Ancestor/breadcrumb tracking
- Automatic pagination

### Local Files
- Supports various file formats through the Unstructured library:
  - Text: `.txt`, `.md`, `.rst`
  - Documents: `.pdf`, `.docx`, `.pptx`
  - Code: `.py`, `.js`, `.ts`, `.java`, `.go`, etc.
  - Data: `.json`, `.yaml`, `.xml`, `.csv`
- Regex pattern-based file filtering
- Metadata preservation (page numbers, etc.)

## Features

- **Automatic Pagination** - Handles batched API calls transparently
- **Retry Logic** - Exponential backoff for transient failures
- **Document Caching** - Optional on-disk caching to speed up re-indexing
- **Flexible Authentication** - Multiple auth methods per source type
- **Error Handling** - Graceful degradation with configurable fail-fast mode

## Usage

### FileSystem Connector

```python
from connectors import FileSystemConnector

# Basic usage
connector = FileSystemConnector(path="./docs")

# With pattern filtering
connector = FileSystemConnector(
    path="./docs",
    include_patterns=[r".*\.md$", r".*\.txt$"],
    exclude_patterns=[r".*/node_modules/.*", r".*\.min\.js$"]
)
```

### Jira Cloud Connector

```python
from connectors import JiraCloudConnector

connector = JiraCloudConnector(
    url="https://company.atlassian.net",
    query="project = PROJ AND created >= -30d",
    email="user@example.com",
    api_token="your-api-token"
)
```

### Confluence Cloud Connector

```python
from connectors import ConfluenceCloudConnector

connector = ConfluenceCloudConnector(
    url="https://company.atlassian.net/wiki",
    query="space = DEV",
    email="user@example.com",
    api_token="your-api-token",
    read_all_comments=True  # Include nested comments
)
```

### Jira Server Connector

```python
from connectors import JiraConnector

connector = JiraConnector(
    url="https://jira.example.com",
    query="assignee = currentUser()",
    token="bearer-token"  # or use login/password
)
```

### Confluence Server Connector

```python
from connectors import ConfluenceConnector

connector = ConfluenceConnector(
    url="https://confluence.example.com",
    query="space = MYSPACE AND type = page",
    token="bearer-token"  # or use login/password
)
```

## Connector Protocol

All connectors implement the `BaseConnector` protocol from `core.v1.connectors`:

```python
@runtime_checkable
class BaseConnector(Protocol):
    @property
    def reader(self):
        """Document reader instance"""
        ...
    
    @property
    def converter(self):
        """Document converter instance"""
        ...
    
    @property
    def connector_type(self) -> str:
        """Connector type identifier"""
        ...
```

This allows connectors to be used interchangeably:

```python
from core.v1 import Index

index = Index()
index.add_collection("my-collection", connector)  # Works with any connector!
```

## Authentication

### Atlassian Cloud (Jira/Confluence)
- Email + API token (generate at https://id.atlassian.com/manage/api-tokens)

### Server/Data Center (Jira/Confluence)
- Bearer token (recommended)
- Username + password (basic auth)

## Dependencies

- **indexed-utils** - Shared utilities (retry, batching, progress)
- **requests** - HTTP client for API calls
- **beautifulsoup4** - HTML parsing for Confluence pages
- **langchain** - Text splitting and chunking
- **unstructured** - Multi-format document parsing

## Development

This package is part of the indexed monorepo workspace. Use `uv` for dependency management:

```bash
# Install dependencies
uv sync --all-groups

# Run tests
uv run pytest packages/indexed-connectors
```

## License

See LICENSE file in the project root.
