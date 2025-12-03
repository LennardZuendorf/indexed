# Config System - API Structure & Flow

## Overview

The config system is now fully implemented with `indexed-config` as the single source of truth. Components register their own config specs explicitly when they need them.

## API Structure

### ConfigService (Main API)

**Location**: `packages/indexed-config/src/indexed_config/service.py`

**Singleton Pattern**:
```python
from indexed_config import ConfigService

# Create instance (or get singleton)
config = ConfigService()
# OR
config = ConfigService.instance()  # Singleton pattern
```

**Exposed Methods**:

#### 1. `register(spec: Type[BaseModel], *, path: str) -> None`
Register a Pydantic config model at a dot-path.
- **Idempotent**: Can be called multiple times with same spec
- **Example**: `config.register(JiraCloudConfig, path="sources.jira")`

#### 2. `bind() -> Provider`
Load, merge, and validate all registered specs.
- Returns a `Provider` with typed config instances
- Raises `ValueError` if validation fails
- **Example**: `provider = config.bind()`

#### 3. `load_raw() -> Dict[str, Any]`
Load raw merged config (global + workspace + env).
- Returns dictionary of all config values
- **Example**: `raw = config.load_raw()`

#### 4. `get_raw() -> Dict[str, Any]`
Alias for `load_raw()` for consistency.
- **Example**: `raw = config.get_raw()`

#### 5. `save_raw(data: Dict[str, Any]) -> None`
Save config to workspace TOML file.
- Writes to `.indexed/config.toml`
- **Example**: `config.save_raw({"sources": {...}})`

#### 6. `get(dot_path: str) -> Any`
Get raw value at dot-path.
- **Example**: `url = config.get("sources.jira.url")`

#### 7. `set(dot_path: str, value: Any) -> None`
Set value at dot-path (writes to workspace TOML).
- **Example**: `config.set("sources.jira.url", "https://...")`

#### 8. `delete(dot_path: str) -> bool`
Delete key at dot-path (from workspace TOML).
- Returns `True` if deleted, `False` if not found
- **Example**: `config.delete("sources.old_connector")`

#### 9. `validate() -> List[Tuple[str, str]]`
Validate all registered specs.
- Returns list of `(path, error_message)` tuples
- Empty list means valid
- **Example**: `errors = config.validate()`

---

### Provider (Typed Config Access)

**Location**: `packages/indexed-config/src/indexed_config/provider.py`

**Created by**: `config.bind()`

**Exposed Methods**:

#### 1. `get(spec: Type[T]) -> T`
Get typed config instance by Pydantic model class.
- Type-safe return value
- Raises `KeyError` if spec not registered
- **Example**: `cfg = provider.get(JiraCloudConfig)`

#### 2. `get_by_path(path: str) -> BaseModel`
Get config instance by dot-path.
- Returns `BaseModel` instance
- Raises `KeyError` if path not registered
- **Example**: `cfg = provider.get_by_path("sources.jira")`

#### 3. `raw` (property)
Get raw merged config dictionary.
- Read-only property
- **Example**: `raw_dict = provider.raw`

---

### TomlStore (File I/O)

**Location**: `packages/indexed-config/src/indexed_config/store.py`

**Used internally by ConfigService**

**Methods**:
- `read() -> Dict[str, Any]` - Read and merge TOML files + env vars
- `write(data: Dict[str, Any]) -> None` - Write to workspace TOML

**Config Sources** (merged in order):
1. Global: `~/.config/indexed/config.toml`
2. Workspace: `./.indexed/config.toml`
3. Environment: `INDEXED__section__key=value`

---

## Complete Flow Diagrams

### Flow 1: CLI Command Using Connector

```
┌─────────────────────────────────────────────────────────────┐
│ 1. CLI Command Execution                                    │
│    $ indexed index create jira -c issues --url ... --jql ...│
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. CLI Command Handler                                      │
│    def create_jira(collection, url, jql, ...):              │
│        config = ConfigService()                             │
│        if url:                                              │
│            config.set("sources.jira.url", url)              │
│        if jql:                                              │
│            config.set("sources.jira.jql", jql)              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Connector Creation                                       │
│    connector = JiraCloudConnector.from_config(config)       │
│                                                             │
│    Inside from_config():                                    │
│    ├─ config.register(JiraCloudConfig,                      │
│    │                   path="sources.jira")                 │
│    ├─ provider = config.bind()                              │
│    ├─ cfg = provider.get(JiraCloudConfig)                   │
│    └─ return cls(url=cfg.url, email=cfg.get_email(), ...)  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Config Loading & Validation                              │
│                                                             │
│    TomlStore.read():                                        │
│    ├─ Read ~/.config/indexed/config.toml                    │
│    ├─ Read ./.indexed/config.toml                           │
│    ├─ Read INDEXED__* env vars                              │
│    └─ Deep merge all sources                                │
│                                                             │
│    ConfigService.bind():                                    │
│    ├─ For each registered spec:                             │
│    │  ├─ Extract config at path                             │
│    │  ├─ Validate with Pydantic                             │
│    │  └─ Create typed instance                              │
│    └─ Return Provider with all instances                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Connector Initialized                                    │
│    connector = JiraCloudConnector(                          │
│        url="https://company.atlassian.net",                 │
│        query="project = PROJ",                              │
│        email="user@company.com",                            │
│        api_token="<from ATLASSIAN_TOKEN env>"               │
│    )                                                        │
└─────────────────────────────────────────────────────────────┘
```

### Flow 2: Config CRUD Operations

```
┌─────────────────────────────────────────────────────────────┐
│ READ Operation                                              │
│                                                             │
│ config = ConfigService()                                    │
│ raw = config.load_raw()                                     │
│ # OR                                                        │
│ value = config.get("sources.jira.url")                      │
│                                                             │
│ Flow:                                                       │
│ ConfigService → TomlStore.read() → Merge files → Return    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ CREATE/UPDATE Operation                                     │
│                                                             │
│ config = ConfigService()                                    │
│ config.set("sources.jira.url", "https://...")              │
│                                                             │
│ Flow:                                                       │
│ ConfigService.set()                                         │
│ ├─ Load current raw config                                  │
│ ├─ Set value at dot-path                                    │
│ └─ TomlStore.write() → .indexed/config.toml                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ DELETE Operation                                            │
│                                                             │
│ config = ConfigService()                                    │
│ deleted = config.delete("sources.old_connector")            │
│                                                             │
│ Flow:                                                       │
│ ConfigService.delete()                                      │
│ ├─ Load current raw config                                  │
│ ├─ Delete key at dot-path                                   │
│ ├─ TomlStore.write() → .indexed/config.toml                 │
│ └─ Return True/False                                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ VALIDATE Operation                                          │
│                                                             │
│ config = ConfigService()                                    │
│ config.register(JiraCloudConfig, path="sources.jira")       │
│ config.register(CoreV1IndexingConfig, path="core.v1.indexing")│
│ errors = config.validate()                                  │
│                                                             │
│ Flow:                                                       │
│ ConfigService.validate()                                    │
│ ├─ Load raw config                                          │
│ ├─ For each registered spec:                                │
│ │  ├─ Extract config at path                                │
│ │  ├─ Try to validate with Pydantic                         │
│ │  └─ Collect errors if validation fails                    │
│ └─ Return list of (path, error) tuples                      │
└─────────────────────────────────────────────────────────────┘
```

### Flow 3: Typed Config Access

```
┌─────────────────────────────────────────────────────────────┐
│ Type-Safe Config Access                                     │
│                                                             │
│ from indexed_config import ConfigService                    │
│ from connectors.jira import JiraCloudConfig                 │
│                                                             │
│ config = ConfigService()                                    │
│ config.register(JiraCloudConfig, path="sources.jira")       │
│                                                             │
│ provider = config.bind()  # Validates all registered specs  │
│ cfg = provider.get(JiraCloudConfig)  # Type: JiraCloudConfig│
│                                                             │
│ # Now use typed config                                      │
│ print(cfg.url)           # Type-safe attribute access       │
│ print(cfg.email)         # IDE autocomplete works           │
│ token = cfg.get_api_token()  # Helper methods available     │
└─────────────────────────────────────────────────────────────┘
```

## Config Model Structure

### Connector Config Models

**Location**: `packages/indexed-connectors/src/connectors/*/schema.py`

**Available Models**:
- `JiraConfig` - Jira Server/DC config
- `JiraCloudConfig` - Jira Cloud config
- `ConfluenceConfig` - Confluence Server/DC config
- `ConfluenceCloudConfig` - Confluence Cloud config
- `FileSystemConfig` - File system connector config

**Pattern**:
```python
from pydantic import BaseModel, Field
import os

class JiraCloudConfig(BaseModel):
    url: str = Field(..., description="Jira Cloud URL")
    email: str = Field(..., description="Email")
    query: str = Field(..., description="JQL query")
    api_token: str = Field(..., description="API token")
    
    # Helper methods for env var access
    def get_api_token(self) -> str:
        return self.api_token or os.getenv("ATLASSIAN_TOKEN", "")
```

### Core v1 Config Models

**Location**: `packages/indexed-core/src/core/v1/config_models.py`

**Available Models**:
- `CoreV1IndexingConfig` - Indexing pipeline settings
- `CoreV1EmbeddingConfig` - Embedding generation settings
- `CoreV1StorageConfig` - Vector storage settings
- `CoreV1SearchConfig` - Search behavior settings
- `PathsConfig` - File system paths
- `MCPConfig` - MCP server settings
- `PerformanceConfig` - Performance and caching
- `LoggingConfig` - Logging configuration

## Configuration Paths

### Namespacing Convention

**Format**: `category.subcategory.field`

**Connector Configs** (`sources.*`):
```
sources.jira                    # Jira (both Server/DC and Cloud)
sources.confluence              # Confluence (both Server/DC and Cloud)
sources.files                   # File System
```

**Core v1 Configs** (`core.v1.*`):
```
core.v1.indexing               # Indexing pipeline
core.v1.embedding              # Embedding generation
core.v1.storage                # Vector storage
core.v1.search                 # Search behavior
```

**Infrastructure Configs**:
```
paths                          # File system paths
mcp                            # MCP server
performance                    # Performance settings
logging                        # Logging configuration
```

## Usage Examples

### Example 1: Simple Connector Usage

```python
from indexed_config import ConfigService
from connectors.jira import JiraCloudConnector

# Initialize config
config = ConfigService()

# Set config values (optional, can also be in TOML file)
config.set("sources.jira.url", "https://company.atlassian.net")
config.set("sources.jira.email", "user@company.com")
config.set("sources.jira.query", "project = PROJ")

# Create connector (registers its own config spec)
connector = JiraCloudConnector.from_config(config)

# Connector is now ready to use
```

### Example 2: Manual Registration and Validation

```python
from indexed_config import ConfigService
from connectors.jira import JiraCloudConfig
from core.v1.config_models import CoreV1IndexingConfig

config = ConfigService()

# Register multiple specs
config.register(JiraCloudConfig, path="sources.jira")
config.register(CoreV1IndexingConfig, path="core.v1.indexing")

# Validate before using
errors = config.validate()
if errors:
    for path, error in errors:
        print(f"Error at {path}: {error}")
    exit(1)

# Bind and get typed configs
provider = config.bind()
jira_cfg = provider.get(JiraCloudConfig)
indexing_cfg = provider.get(CoreV1IndexingConfig)

# Use typed configs
print(f"Jira URL: {jira_cfg.url}")
print(f"Chunk size: {indexing_cfg.chunk_size}")
```

### Example 3: CLI Config Commands

```python
# indexed/src/indexed/config/cli.py

from indexed_config import ConfigService

def inspect():
    """Show merged config."""
    config = ConfigService()
    raw = config.load_raw()
    print(json.dumps(raw, indent=2))

def set_config(key: str, value: str):
    """Set config value."""
    config = ConfigService()
    config.set(key, coerce_value(value))
    print(f"✓ Set {key} = {value}")

def delete_config(key: str):
    """Delete config key."""
    config = ConfigService()
    if config.delete(key):
        print(f"✓ Deleted {key}")
    else:
        print(f"Key not found: {key}")

def validate():
    """Validate all registered specs."""
    config = ConfigService()
    # Register known specs
    config.register(JiraCloudConfig, path="sources.jira")
    # ... register others
    
    errors = config.validate()
    if errors:
        print("Validation errors:")
        for path, msg in errors:
            print(f"  {path}: {msg}")
    else:
        print("✓ Configuration is valid")
```

## Key Design Decisions

1. **Explicit Registration**: Components register their own config specs when they need them (no auto-discovery magic)

2. **Zero Coupling**: ConfigService doesn't know about any consumers; consumers know about ConfigService

3. **Idempotent Registration**: Calling `register()` multiple times with same spec is safe

4. **Type Safety**: All config access through Pydantic models with full type hints

5. **Version Awareness**: Namespaced paths (`core.v1.*`, `core.v2.*`) support multiple API versions

6. **Extensibility**: Adding new connectors/versions requires zero changes to config system

## Summary

**ConfigService API**:
- `register(spec, path)` - Register config model
- `bind()` - Validate and get Provider
- `set(path, value)` - Write config
- `delete(path)` - Remove config
- `validate()` - Check all registered specs
- `load_raw()` / `get_raw()` - Get raw config dict
- `get(path)` - Get raw value at path

**Provider API**:
- `get(Type[T])` - Get typed config by class
- `get_by_path(str)` - Get config by path
- `raw` - Get raw config dict

**Pattern**:
```python
config = ConfigService()
config.set("sources.connector.field", value)  # Optional override
connector = Connector.from_config(config)     # Registers & extracts config
```

This design is simple, explicit, type-safe, and infinitely extensible! 🎉

