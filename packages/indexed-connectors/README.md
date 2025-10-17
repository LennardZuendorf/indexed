# indexed-connectors

Connectors for reading, indexing, and converting rich metadata from diverse sources—Jira, Confluence, GitHub, local files, and more.

## Overview

`indexed-connectors` offers a unified architecture for discovering, ingesting, and transforming documents with context-rich metadata from a growing set of platforms and formats. All connectors implement the modernized `BaseConnector` protocol, ensuring seamless interoperability with the indexed-core framework and consistent metadata extraction.

## Supported Sources

### Jira
- **Jira Server/Data Center** – On-premises Jira
- **Jira Cloud** – Atlassian-hosted Jira

Features:
- JQL-based filtering
- Multi-modal authentication: API token, OAuth, or basic
- Full issue metadata, fields, and nested comments (authors, timestamps, attachments)
- Attachment download and indexing
- Robust pagination

### Confluence
- **Confluence Server/Data Center** – On-premises Confluence
- **Confluence Cloud** – Atlassian-hosted Confluence

Features:
- CQL-based page and space filtering
- Token, OAuth, or basic authentication
- Full page content, hierarchical/nested comments (with user/parent/created-at/updated-at), ancestor hierarchy
- Metadata extraction: revision, history, labels, author, timestamps
- Child/parent link resolution
- Attachment handling (download/index)

Features:
- Repository, issue, pull request, and comment ingestion
- Rich metadata (author, timestamps, status, labels, linked issues/PRs)
- Organization, repository, and branch filtering

### Local Files
- Unstructured local/remote sources:
  - Text: `.txt`, `.md`, `.rst`
  - Documents: `.pdf`, `.docx`, `.pptx`, `.odt`
  - Code: `.py`, `.js`, `.java`, `.go`, etc.
  - Data: `.csv`, `.json`, `.yaml`, `.xml`, `.parquet`
- Regex-based path filtering
- Rich file metadata: path, size, modified/created timestamps, checksums, page/section tracking

### Other Connectors (Preview)
- **Google Drive, Notion, Generic HTTP/REST, S3, and more** (via plugin entry points)

See [docs/CONNECTOR_MATRIX.md](../docs/CONNECTOR_MATRIX.md) for full compatibility.

## Key Features

- **Rich Metadata Extraction** – Every document and segment is annotated with provenance: source IDs, paths, authors, timestamps, context hierarchies, and more.
- **Automatic Pagination & Batching** – Handles large queries with efficient chunking.
- **Configurable Retries** – Exponential backoff for network/API errors.
- **Flexible Authentication** – Multiple auth methods per connector; secrets/passphrases supported.
- **On-Disk Document Cache** – Optional, greatly speeds up repeated or incremental indexing runs.
- **Selective Indexing** – Filter by pattern, date, status, or metadata.
- **Robust Error Handling** – Continue-on-error or fail-fast; exhaustive logs for failed records.

## Usage

### Example: Local File Connector

```python
from connectors import FileSystemConnector

# Minimal usage (direct instantiation)
connector = FileSystemConnector(path="./docs")

# With include/exclude filters
connector = FileSystemConnector(
    path="./docs",
    include_patterns=[r".*\.md$", r".*\.txt$"],
    exclude_patterns=[r".*/node_modules/.*", r".*\.min\.js$"],
    fail_fast=False  # Continue on errors (default)
)

# Config-driven instantiation (via ConfigService)
from core.v1.engine.services.config_service import ConfigService

config_service = ConfigService()
connector = FileSystemConnector.from_config(config_service, "sources.docs")

# Expected config structure in indexed.toml or settings:
# [sources.docs]
# path = "./my-docs"
# include_patterns = [".*\\.md$", ".*\\.txt$"]
# exclude_patterns = [".*/node_modules/.*"]
# fail_fast = false
```

### Example: Jira Cloud Connector

```python
from connectors import JiraCloudConnector

connector = JiraCloudConnector(
    url="https://company.atlassian.net",
    query="project = PROJ AND updated >= -90d",
    email="user@example.com",
    api_token="your-token",
    include_attachments=True
)
```

### Example: Confluence Cloud Connector

```python
from connectors import ConfluenceCloudConnector

connector = ConfluenceCloudConnector(
    url="https://company.atlassian.net/wiki",
    query="space = DEV",
    email="user@example.com",
    api_token="your-token",
    read_all_comments=True,        # Include nested comments in output
    include_attachments=False
)
```

## Connector Protocol

All connectors are based on the `BaseConnector` protocol from `core.v1.connectors`. Every connector must provide:

```python
@runtime_checkable
class BaseConnector(Protocol):
    @property
    def reader(self):
        """Document reader instance, yields docs with .metadata property"""
        ...
    
    @property
    def converter(self):
        """Document converter instance (standardizes internal document structure)"""
        ...
    
    @property
    def connector_type(self) -> str:
        """Human-readable connector type"""
        ...

    @property
    def metadata_schema(self) -> dict:
        """Dict describing metadata fields added to each document/chunk"""
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
