# indexed-config

Configuration management for the indexed project with TOML-based storage, environment variable support, and dual storage modes.

## Overview

`indexed-config` provides a unified configuration system for indexed that supports:
- **TOML-based configuration** with hierarchical key-value storage
- **Dual storage modes**: Global (`~/.indexed/`) and local (`./.indexed/`)
- **Environment variable overrides** via `INDEXED__` prefix
- **Sensitive credential handling** via `.env` files
- **Pydantic-based validation** with typed configuration specs

## Features

### Storage Architecture

```
~/.indexed/                    # Global storage (default)
├── config.toml               # Global configuration
├── .env                      # Sensitive credentials
└── data/
    ├── collections/          # Index storage
    └── caches/               # Document caches

./.indexed/                    # Local storage (per-project)
├── config.toml               # Local configuration (overrides global)
├── .env                      # Local credentials
└── data/
    ├── collections/
    └── caches/
```

### Configuration Sources

Configuration is loaded and merged from multiple sources (later sources override earlier):

1. **Global config** (`~/.indexed/config.toml`)
2. **Local config** (`./.indexed/config.toml`)
3. **Environment variables** (`INDEXED__section__key=value`)

### Key Components

| Component | Description |
|-----------|-------------|
| `ConfigService` | Main service for configuration management |
| `TomlStore` | TOML file read/write with merge logic |
| `StorageResolver` | Path resolution based on storage mode |
| `Provider` | Typed configuration access after validation |

## Installation

This package is part of the indexed monorepo workspace. Requires **Python 3.11+**.

```bash
# Install with workspace
uv sync

# Or install standalone (for development)
cd packages/indexed-config
uv pip install -e .
```

## Usage

### Basic Configuration Access

```python
from indexed_config import ConfigService

# Get singleton instance
config = ConfigService.instance()

# Read raw configuration
raw = config.load_raw()

# Get specific value by dot-path
max_docs = config.get("search.max_docs")

# Set a value (writes to active config file)
config.set("search.max_docs", 20)
```

### Typed Configuration with Pydantic

```python
from pydantic import BaseModel
from indexed_config import ConfigService

# Define a typed config spec
class SearchConfig(BaseModel):
    max_docs: int = 10
    max_chunks: int = 30
    include_matched_chunks: bool = True

# Register and bind
config = ConfigService.instance()
config.register(SearchConfig, path="search")

# Get typed provider
provider = config.bind()

# Access typed config (type-safe!)
search_config = provider.get(SearchConfig)
print(search_config.max_docs)  # 10
```

### Storage Mode Control

```python
from indexed_config import ConfigService, StorageMode

# Force global storage
config = ConfigService.instance(mode_override="global")

# Force local storage
config = ConfigService.instance(mode_override="local")

# Check and set workspace preference
pref = config.get_workspace_preference()
config.set_workspace_preference("local")
```

### Storage Path Resolution

```python
from indexed_config import (
    get_global_root,
    get_local_root,
    get_collections_path,
    get_caches_path,
    has_local_storage,
    has_global_storage,
    ensure_storage_dirs,
)

# Get storage roots
global_root = get_global_root()  # ~/.indexed
local_root = get_local_root()    # ./.indexed

# Get data paths
collections = get_collections_path(global_root)  # ~/.indexed/data/collections
caches = get_caches_path(global_root)           # ~/.indexed/data/caches

# Check existence
if has_local_storage():
    print("Local .indexed directory exists")

# Ensure directories exist
ensure_storage_dirs(global_root)
```

### Handling Sensitive Values

```python
from indexed_config import ConfigService

config = ConfigService.instance()

# Set sensitive value (routes to .env file automatically)
config.set_value(
    "sources.jira.api_token",
    "secret-token",
    field_info={"sensitive": True, "env_var": "ATLASSIAN_TOKEN"}
)

# Or set non-sensitive value (routes to config.toml)
config.set_value("search.max_docs", 20)
```

### Configuration Validation

```python
from indexed_config import ConfigService
from pydantic import BaseModel

class JiraConfig(BaseModel):
    url: str
    email: str
    api_token: str

config = ConfigService.instance()
config.register(JiraConfig, path="sources.jira")

# Validate all registered specs
errors = config.validate()
for path, error in errors:
    print(f"Validation error at {path}: {error}")

# Check requirements for CLI prompting
result = config.validate_requirements(
    JiraConfig,
    namespace="sources.jira",
    cli_overrides={"url": "https://example.atlassian.net"}
)
print(f"Present: {result['present']}")
print(f"Missing: {result['missing']}")
```

### Conflict Detection

```python
from indexed_config import ConfigService

config = ConfigService.instance()

# Check if local and global configs have conflicts
if config.has_config_conflict():
    differences = config.get_config_differences()
    for path, (local_val, global_val) in differences.items():
        print(f"{path}: local={local_val}, global={global_val}")
```

## API Reference

### ConfigService

The main entry point for configuration management.

| Method | Description |
|--------|-------------|
| `instance()` | Get singleton instance |
| `reset()` | Reset singleton (for testing) |
| `load_raw()` | Load merged configuration as dict |
| `get(dot_path)` | Get value by dot-path |
| `set(dot_path, value)` | Set value by dot-path |
| `delete(dot_path)` | Delete value by dot-path |
| `register(spec, path)` | Register Pydantic model at path |
| `bind()` | Validate and return typed Provider |
| `validate()` | Validate all registered specs |
| `validate_requirements()` | Check required fields for prompting |
| `set_value()` | Set value with sensitive routing |
| `get_workspace_preference()` | Get storage mode preference |
| `set_workspace_preference()` | Set storage mode preference |
| `has_config_conflict()` | Check for local/global conflicts |
| `get_config_differences()` | Get differing values |
| `get_collections_path()` | Resolved collections directory |
| `get_caches_path()` | Resolved caches directory |
| `ensure_storage_dirs()` | Create storage directories |

### Storage Functions

| Function | Description |
|----------|-------------|
| `get_global_root()` | Returns `~/.indexed` |
| `get_local_root(workspace)` | Returns `./.indexed` |
| `get_config_path(root)` | Returns `{root}/config.toml` |
| `get_env_path(root)` | Returns `{root}/.env` |
| `get_data_root(root)` | Returns `{root}/data` |
| `get_collections_path(root)` | Returns `{root}/data/collections` |
| `get_caches_path(root)` | Returns `{root}/data/caches` |
| `has_local_storage()` | Check if `./.indexed` exists |
| `has_global_storage()` | Check if `~/.indexed` exists |
| `has_local_config()` | Check if local config.toml exists |
| `has_global_config()` | Check if global config.toml exists |
| `ensure_storage_dirs(root)` | Create all storage directories |

### StorageResolver

Stateful path resolution with mode awareness.

```python
from indexed_config import StorageResolver, StorageMode

resolver = StorageResolver(
    workspace=Path.cwd(),
    mode_override="local"  # or "global" or None
)

# Resolve paths
root = resolver.resolve_root()
collections = resolver.get_collections_path()
caches = resolver.get_caches_path()
config = resolver.get_config_path()
env = resolver.get_env_path()

# Check for conflicts
if resolver.has_conflict():
    print("Both local and global configs exist")

# Ensure directories
resolver.ensure_dirs()
```

## Environment Variables

Environment variables override configuration with the `INDEXED__` prefix:

```bash
# Structure: INDEXED__<SECTION>__<KEY>=value
export INDEXED__SEARCH__MAX_DOCS=20
export INDEXED__SEARCH__MAX_CHUNKS=50
export INDEXED__LOGGING__LEVEL=DEBUG
```

Nested sections use double underscores:

```bash
# sources.jira.base_url
export INDEXED__SOURCES__JIRA__BASE_URL=https://example.atlassian.net
```

## Dependencies

| Package | Purpose |
|---------|---------|
| **pydantic** | Configuration validation and typing |
| **platformdirs** | Cross-platform path resolution |
| **tomlkit** | TOML file handling with formatting preservation |

## Development

### Running Tests

```bash
# Run config package tests
uv run pytest tests/unit/indexed_config -v

# Run with coverage
uv run pytest tests/unit/indexed_config --cov=indexed_config
```

### Code Quality

```bash
# Format
uv run ruff format packages/indexed-config/

# Lint
uv run ruff check packages/indexed-config/

# Type check
uv run mypy packages/indexed-config/src/
```

## License

See LICENSE file in the project root.
