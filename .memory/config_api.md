# Configuration API Documentation

## Overview

The `indexed-config` package provides a unified configuration system for the Indexed application. It follows a simple, explicit pattern where components register their own config specs when they need them.

## Core Principles

1. **Single Source of Truth**: `indexed-config` is THE config system
2. **Explicit Registration**: Components register their config specs at usage point
3. **Zero Coupling**: Config doesn't know about consumers
4. **Type Safety**: Pydantic validation throughout
5. **Version Awareness**: Namespaced paths support multiple versions (`core.v1.*`, `core.v2.*`)

## Architecture

```
Config Sources (Priority: Low → High)
├── Pydantic Model Defaults
├── Global Config (~/.config/indexed/config.toml)
├── Workspace Config (./.indexed/config.toml)
└── Environment Variables (INDEXED__*)

                ↓

        ConfigService
        ├── register(spec, path)
        ├── bind() → Provider
        ├── set(path, value)
        ├── delete(path)
        └── validate()

                ↓

          Provider
          ├── get(Type[T]) → T
          └── get_by_path(str) → BaseModel
```

## Basic Usage

### 1. Initialize ConfigService

```python
from indexed_config import ConfigService

# Create config service instance
config = ConfigService()
```

### 2. Register Config Specs and Use

```python
from indexed_config import ConfigService
from connectors.jira import JiraCloudConnector

# Initialize config
config = ConfigService()

# Connector registers its own config spec and extracts values
connector = JiraCloudConnector.from_config(config)
```

### 3. Override Config Values

```python
# Set config values (writes to workspace TOML)
config.set("sources.jira.base_url", "https://company.atlassian.net")
config.set("sources.jira.jql", "project = MYPROJ")

# Now create connector with overridden values
connector = JiraCloudConnector.from_config(config)
```

### 4. CRUD Operations

```python
# Read raw config
raw_config = config.load_raw()  # or config.get_raw()

# Set value
config.set("core.v1.indexing.chunk_size", 1024)

# Delete value
config.delete("sources.old_connector")

# Validate all registered specs
errors = config.validate()
if errors:
    for path, error in errors:
        print(f"Error at {path}: {error}")
```

## Connector Pattern

All connectors follow this pattern:

```python
from indexed_config import ConfigService
from .schema import MyConnectorConfig

class MyConnector:
    @classmethod
    def from_config(cls, config_service: ConfigService) -> "MyConnector":
        """Create connector from ConfigService.
        
        Registers config spec and extracts values.
        """
        # 1. Register our config spec
        config_service.register(MyConnectorConfig, path="sources.my_connector")
        
        # 2. Bind and get our config
        provider = config_service.bind()
        cfg = provider.get(MyConnectorConfig)
        
        # 3. Create instance with config values
        return cls(
            url=cfg.url,
            query=cfg.query,
            api_key=cfg.get_api_key(),  # Helper method for env vars
        )
```

## Available Connectors

### Jira Server/DC

```python
from indexed_config import ConfigService
from connectors.jira import JiraConnector

config = ConfigService()
# Optionally override config
config.set("sources.jira.url", "https://jira.company.com")
config.set("sources.jira.query", "project = PROJ")

connector = JiraConnector.from_config(config)
```

**Config Path**: `sources.jira`  
**Config Model**: `JiraConfig`  
**Required Fields**: `url`, `query`  
**Auth**: Token or login/password (from env vars)

### Jira Cloud

```python
from indexed_config import ConfigService
from connectors.jira import JiraCloudConnector

config = ConfigService()
config.set("sources.jira.url", "https://company.atlassian.net")
config.set("sources.jira.email", "user@company.com")
config.set("sources.jira.query", "project = PROJ")

connector = JiraCloudConnector.from_config(config)
```

**Config Path**: `sources.jira` (unified namespace for both Server and Cloud)  
**Config Model**: `JiraCloudConfig`  
**Required Fields**: `url`, `email`, `query`  
**Auth**: API token from `ATLASSIAN_TOKEN` env var

### Confluence Server/DC

```python
from indexed_config import ConfigService
from connectors.confluence import ConfluenceConnector

config = ConfigService()
config.set("sources.confluence.url", "https://confluence.company.com")
config.set("sources.confluence.query", "space = DEV")

connector = ConfluenceConnector.from_config(config)
```

**Config Path**: `sources.confluence`  
**Config Model**: `ConfluenceConfig`  
**Required Fields**: `url`, `query`  
**Auth**: Token or login/password (from env vars)

### Confluence Cloud

```python
from indexed_config import ConfigService
from connectors.confluence import ConfluenceCloudConnector

config = ConfigService()
config.set("sources.confluence.url", "https://company.atlassian.net/wiki")
config.set("sources.confluence.email", "user@company.com")
config.set("sources.confluence.query", "space = DEV")

connector = ConfluenceCloudConnector.from_config(config)
```

**Config Path**: `sources.confluence` (unified namespace for both Server and Cloud)  
**Config Model**: `ConfluenceCloudConfig`  
**Required Fields**: `url`, `email`, `query`  
**Auth**: API token from `ATLASSIAN_TOKEN` env var

### File System

```python
from indexed_config import ConfigService
from connectors.files import FileSystemConnector

config = ConfigService()
config.set("sources.files.path", "./documents")
config.set("sources.files.include_patterns", ["*.md", "*.txt"])

connector = FileSystemConnector.from_config(config)
```

**Config Path**: `sources.files`  
**Config Model**: `FileSystemConfig`  
**Required Fields**: `path`  
**Optional**: `include_patterns`, `exclude_patterns`, `fail_fast`

## Core v1 Config Models

### Indexing Configuration

```python
from indexed_config import ConfigService
from core.v1.config_models import CoreV1IndexingConfig

config = ConfigService()
config.register(CoreV1IndexingConfig, path="core.v1.indexing")

provider = config.bind()
indexing_cfg = provider.get(CoreV1IndexingConfig)

print(indexing_cfg.chunk_size)  # 512 (default)
print(indexing_cfg.chunk_overlap)  # 50 (default)
```

**Config Path**: `core.v1.indexing`  
**Fields**:
- `chunk_size` (int, default: 512)
- `chunk_overlap` (int, default: 50)
- `batch_size` (int, default: 32)

### Embedding Configuration

```python
from core.v1.config_models import CoreV1EmbeddingConfig

config.register(CoreV1EmbeddingConfig, path="core.v1.embedding")
provider = config.bind()
embedding_cfg = provider.get(CoreV1EmbeddingConfig)
```

**Config Path**: `core.v1.embedding`  
**Fields**:
- `provider` (str, default: "sentence-transformers")
- `model_name` (str, default: "all-MiniLM-L6-v2")
- `dimension` (int, optional)
- `batch_size` (int, default: 64)
- `device` (str, optional)

### Search Configuration

```python
from core.v1.config_models import CoreV1SearchConfig

config.register(CoreV1SearchConfig, path="core.v1.search")
provider = config.bind()
search_cfg = provider.get(CoreV1SearchConfig)
```

**Config Path**: `core.v1.search`  
**Fields**:
- `max_docs` (int, default: 10)
- `max_chunks` (int, default: 30)
- `include_full_text` (bool, default: False)
- `score_threshold` (float, optional)

## Configuration File Format

### Workspace Config (`.indexed/config.toml`)

```toml
[sources.jira]
url = "https://company.atlassian.net"
email = "user@company.com"
query = "project = PROJ AND updated >= -30d"

[sources.confluence]
url = "https://company.atlassian.net/wiki"
email = "user@company.com"
query = "space = DEV"
read_all_comments = true

[sources.files]
path = "./documents"
include_patterns = ["*.md", "*.txt", "*.pdf"]
exclude_patterns = ["*.draft.md"]
fail_fast = false

[core.v1.indexing]
chunk_size = 512
chunk_overlap = 50
batch_size = 32

[core.v1.embedding]
provider = "sentence-transformers"
model_name = "all-MiniLM-L6-v2"
batch_size = 64

[core.v1.search]
max_docs = 10
max_chunks = 30
include_full_text = false
```

### Environment Variables

Override any config value using environment variables:

```bash
# Format: INDEXED__section__subsection__key=value
export INDEXED__sources__jira__url="https://company.atlassian.net"
export INDEXED__core__v1__indexing__chunk_size=1024

# Secrets (referenced by config)
export ATLASSIAN_TOKEN="your-api-token"
export JIRA_TOKEN="your-jira-token"
export CONF_TOKEN="your-confluence-token"
```

## Advanced Usage

### Manual Registration and Binding

```python
from indexed_config import ConfigService
from connectors.jira import JiraCloudConfig
from core.v1.config_models import CoreV1IndexingConfig

config = ConfigService()

# Register multiple specs
config.register(JiraCloudConfig, path="sources.jira")
config.register(CoreV1IndexingConfig, path="core.v1.indexing")

# Bind once to validate all
provider = config.bind()

# Get typed configs
jira_cfg = provider.get(JiraCloudConfig)
indexing_cfg = provider.get(CoreV1IndexingConfig)

# Use configs
print(f"Jira URL: {jira_cfg.url}")
print(f"Chunk size: {indexing_cfg.chunk_size}")
```

### Path-Based Access

```python
# Get config by path (useful for dynamic access)
provider = config.bind()
jira_cfg = provider.get_by_path("sources.jira")
```

### Validation

```python
# Validate all registered specs
errors = config.validate()

if errors:
    print("Configuration errors found:")
    for path, error in errors:
        print(f"  {path}: {error}")
else:
    print("Configuration is valid!")
```

## Migration from Old Config System

### Old Pattern (Deprecated)

```python
# ❌ OLD - Don't use
from core.v1.config import ConfigService as OldConfigService

config = OldConfigService.get_instance()
settings = config.get()
jira_config = settings.sources.jira
```

### New Pattern

```python
# ✅ NEW - Use this
from indexed_config import ConfigService
from connectors.jira import JiraCloudConnector

config = ConfigService()
connector = JiraCloudConnector.from_config(config)
```

## Best Practices

1. **Let connectors handle their config**: Don't manually navigate config, let `from_config()` do it
2. **Register at usage point**: Register specs where you need them, not globally
3. **Use environment variables for secrets**: Never put tokens/passwords in TOML files
4. **Validate early**: Call `config.validate()` after registration to catch errors early
5. **Use typed access**: Prefer `provider.get(Type)` over raw dict access

## Troubleshooting

### "Config spec not found" Error

```python
# ❌ Error: Forgot to register
provider = config.bind()
cfg = provider.get(JiraCloudConfig)  # KeyError!

# ✅ Fix: Register first
config.register(JiraCloudConfig, path="sources.jira")
provider = config.bind()
cfg = provider.get(JiraCloudConfig)  # Works!
```

### "Invalid config" Error

```python
# Config validation failed
# Check the error message for which field is invalid
try:
    provider = config.bind()
except ValueError as e:
    print(f"Config error: {e}")
    # Fix the config file or set the missing value
    config.set("sources.jira.url", "https://company.atlassian.net")
```

### Environment Variables Not Working

```bash
# ❌ Wrong format
export JIRA_URL="..."  # Won't work

# ✅ Correct format
export INDEXED__sources__jira__url="..."  # Works!
```

## Summary

The new config system is:
- **Simple**: Just `ConfigService()` and `from_config()`
- **Explicit**: Components register what they need
- **Extensible**: Add new connectors without touching config
- **Type-safe**: Pydantic validation throughout
- **Version-aware**: Support multiple core versions

For more examples, see the connector implementations in `packages/indexed-connectors/src/connectors/`.

