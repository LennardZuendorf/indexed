# FileSystem Connector

The FileSystem connector enables indexing of documents from your local file system. It supports a wide variety of file formats and provides flexible filtering capabilities through regex patterns.

## Features

- **Multiple File Formats**: Supports text files (`.txt`, `.md`, `.rst`), documents (`.pdf`, `.docx`, `.pptx`), code files, and more via the Unstructured library
- **Pattern-based Filtering**: Include and exclude files using regex patterns
- **Error Handling**: Choose between fail-fast mode or continue-on-error
- **Rich Metadata**: Extracts file path, size, timestamps, and other metadata
- **BaseConnector Compliance**: Implements config-driven instantiation for seamless integration

## Installation

The FileSystem connector is part of the `indexed-connectors` package:

```bash
uv add indexed-connectors
```

## Usage

### Direct Instantiation

```python
from connectors.files.connector import FileSystemConnector

# Basic usage - index all files in a directory
connector = FileSystemConnector(path="./docs")

# With pattern filtering
connector = FileSystemConnector(
    path="./docs",
    include_patterns=[r".*\.md$", r".*\.txt$"],  # Only markdown and text files
    exclude_patterns=[r".*/node_modules/.*", r".*\.test\..*"],  # Exclude node_modules and test files
    fail_fast=False  # Continue on errors (default)
)

# Use with Index
from core.v1 import Index

index = Index()
index.add_collection("my-docs", connector)
```

### Config-driven Instantiation

The connector can also be instantiated from configuration, following the BaseConnector protocol:

```python
from connectors.files.connector import FileSystemConnector
from core.v1.engine.services.config_service import ConfigService

config_service = ConfigService()
connector = FileSystemConnector.from_config(config_service, "sources.docs")
```

**Configuration Structure** (in `indexed.toml` or settings):

```toml
[sources.docs]
path = "./documentation"
include_patterns = [".*\\.md$", ".*\\.rst$"]
exclude_patterns = [".*/build/.*", ".*/\\.git/.*"]
fail_fast = false
```

## Configuration Reference

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | `str` | Yes | - | Root directory path to scan for files |
| `include_patterns` | `list[str]` | No | `[".*"]` | Regex patterns for files to include |
| `exclude_patterns` | `list[str]` | No | `[]` | Regex patterns for files to exclude |
| `fail_fast` | `bool` | No | `False` | Stop on first error (True) or continue (False) |

### Pattern Examples

Include only specific file types:
```python
include_patterns=[r".*\\.md$", r".*\\.txt$", r".*\\.pdf$"]
```

Exclude common directories:
```python
exclude_patterns=[
    r".*/node_modules/.*",
    r".*/__pycache__/.*",
    r".*/\\.git/.*",
    r".*/build/.*",
    r".*/dist/.*"
]
```

Include only code files in `src` directory:
```python
include_patterns=[r"src/.*\\.(py|js|ts|java)$"]
exclude_patterns=[r".*test.*", r".*\\.min\\..*"]
```

## BaseConnector Protocol

The FileSystemConnector implements the `BaseConnector` protocol from `core.v1.connectors.base`:

```python
@property
def reader(self) -> FilesDocumentReader:
    """Document reader for discovering and reading files"""

@property
def converter(self) -> FilesDocumentConverter:
    """Document converter for standardizing format"""

@property
def connector_type(self) -> str:
    """Returns 'localFiles'"""

@classmethod
def config_spec(cls) -> dict:
    """Returns configuration specification"""

@classmethod
def from_config(cls, config_service, namespace: str) -> FileSystemConnector:
    """Create connector from ConfigService"""
```

## Error Handling

By default, the connector continues processing files even if some files fail to read (`fail_fast=False`). This ensures maximum coverage when indexing large directories with potentially problematic files.

Set `fail_fast=True` to stop immediately on the first error:

```python
connector = FileSystemConnector(
    path="./docs",
    fail_fast=True  # Stop on first error
)
```

## Examples

### Index Markdown Documentation

```python
connector = FileSystemConnector(
    path="./docs",
    include_patterns=[r".*\\.md$"],
    exclude_patterns=[r".*/node_modules/.*"]
)
```

### Index Python Source Code

```python
connector = FileSystemConnector(
    path="./src",
    include_patterns=[r".*\\.py$"],
    exclude_patterns=[
        r".*/__pycache__/.*",
        r".*test.*",
        r".*/\\..*"  # Hidden files/directories
    ]
)
```

### Index Mixed Content

```python
connector = FileSystemConnector(
    path="./project",
    include_patterns=[
        r".*\\.(md|txt|rst)$",  # Documentation
        r".*\\.(py|js|ts)$",     # Code
        r".*\\.(json|yaml|toml)$" # Config files
    ],
    exclude_patterns=[
        r".*/node_modules/.*",
        r".*/\\.git/.*",
        r".*/build/.*",
        r".*/dist/.*"
    ]
)
```

## Supported File Formats

Through the Unstructured library, the connector supports:

- **Text**: `.txt`, `.md`, `.rst`
- **Documents**: `.pdf`, `.docx`, `.pptx`, `.odt`
- **Code**: `.py`, `.js`, `.java`, `.go`, `.ts`, `.jsx`, `.tsx`, etc.
- **Data**: `.csv`, `.json`, `.yaml`, `.xml`
- And many more...

## See Also

- [BaseConnector Protocol](/packages/indexed-core/src/core/v1/connectors/base.py)
- [FilesDocumentReader](./files_document_reader.py)
- [FilesDocumentConverter](./files_document_converter.py)
- [Main Connectors README](../../README.md)
