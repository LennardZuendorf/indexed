# Configuration Management System Guide

This package provides unified, typed configuration management with hierarchical merging and sensitive field handling.

## Package Overview

**Location:** `packages/indexed-config/`

**Purpose:**
- Provide centralized configuration service singleton
- Support hierarchical configuration (TOML, env, CLI)
- Validate configuration with Pydantic models
- Route sensitive fields to .env files
- Enable both global (~/.indexed/) and local (./.indexed/) storage modes

**Key Responsibilities:**
- Load and parse TOML configuration files
- Merge configuration from multiple sources (priorities)
- Validate all configuration against Pydantic schemas
- Provide typed access to configuration values
- Handle sensitive credential storage

**Key Files:**
```
src/indexed_config/
├── service.py              # ConfigService singleton
├── store.py                # TOML file I/O and parsing
├── provider.py             # Typed configuration provider
├── storage.py              # Storage mode resolution
├── path_utils.py           # Dot-path utilities for nested access
├── models.py               # Shared configuration models
└── __init__.py             # Public API
```

## Configuration Hierarchy

Configuration merges from multiple sources with strict priority (increasing):

```
1. Pydantic model defaults (LOWEST)
2. Global config (~/.indexed/config.toml)
3. Workspace config (./.indexed/config.toml)
4. Environment variables (INDEXED__section__key=value)
5. CLI arguments (HIGHEST)
```

### Priority Example

```toml
# ~/.indexed/config.toml (Global)
[core.v1.search]
max_docs = 10

# ./.indexed/config.toml (Workspace, overrides global)
[core.v1.search]
max_docs = 20

# Command line (overrides all)
# max_docs = 30 (passed via CLI)

# Result: max_docs = 30
```

## Storage Modes

### Global Mode (Default)

Configuration stored in user's home directory:

```
~/.indexed/
├── config.toml                    # Configuration
├── .env                           # Sensitive credentials
└── data/
    └── collections/
        └── {collection-name}/
```

**Use Case:** Default behavior, collections shared across projects

**Activate:**
```bash
indexed index create ... --storage-mode global
# or default (no flag)
```

### Local Mode

Configuration stored in project directory:

```
./.indexed/
├── config.toml                    # Project configuration
├── .env                           # Project credentials
└── data/
    └── collections/
        └── {collection-name}/
```

**Use Case:** Project-specific collections, isolated from other projects

**Activate:**
```bash
indexed index create ... --storage-mode local
# or
export INDEXED__storage__mode=local
indexed index create ...
```

**Auto-detect:** If `./.indexed/config.toml` exists, uses local mode by default.

## ConfigService API

Singleton service for configuration management:

```python
from indexed_config import ConfigService

# Get singleton instance
config = ConfigService.instance()

# Access configuration values
max_docs = config.get("core.v1.search.max_docs")

# Get nested configuration as dict
search_config = config.get("core.v1.search")

# Get typed configuration
from core.v1.config_models import SearchConfig
search_config: SearchConfig = config.get_typed("core.v1.search", SearchConfig)

# Set configuration value
config.set("core.v1.search.max_docs", 20)

# Delete configuration value
config.delete("core.v1.search.max_docs")

# Validate entire configuration
config.validate()

# Check if required fields are present
missing = config.validate_requirements()
if missing:
    print(f"Missing required fields: {missing}")
```

## Configuration Registration

Components register their configuration specs at startup:

```python
from indexed_config import ConfigService
from pydantic import BaseModel

class MyComponentConfig(BaseModel):
    """Configuration for my component."""
    option1: str
    option2: int = 10

# Register configuration
config = ConfigService.instance()
config.register(
    spec=MyComponentConfig,
    path="components.my_component",  # Dot-path for TOML
)

# Later: Get typed config
my_config: MyComponentConfig = config.get_typed(
    "components.my_component",
    MyComponentConfig,
)
```

## Configuration Schemas

### Core Configuration

#### Indexing Configuration

```toml
[core.v1.indexing]
chunk_size = 512                  # Characters per chunk
chunk_overlap = 50                # Character overlap between chunks
batch_size = 32                   # Batch size for embedding generation
```

#### Search Configuration

```toml
[core.v1.search]
max_docs = 20                     # Maximum results per search
max_chunks = 5                    # Maximum chunks per document
min_score = 0.0                   # Minimum relevance score (0-1)
```

#### Vector Store Configuration

```toml
[core.v1.vector_store]
index_type = "IndexFlatL2"        # FAISS index type
# Options: IndexFlatL2, IndexIVFFlat, IndexHNSW
```

#### Embedding Configuration

```toml
[core.v1.embedding]
model_name = "all-MiniLM-L6-v2"  # Sentence-transformers model
# Options: all-MiniLM-L6-v2, all-mpnet-base-v2, multi-qa-distilbert-cos-v1
```

### Source Configuration (Connectors)

#### File System Source

```toml
[sources.files]
path = "./documents"              # Directory path
file_patterns = ["*.md", "*.pdf"] # Include patterns (optional)
exclude_patterns = [".*"]         # Exclude patterns (optional)
```

#### Jira Server/DC Source

```toml
[sources.jira]
url = "https://jira.company.com"
username = "user@company.com"
api_token = "secret"              # Via environment or .env
jql = "project = DOCS"            # Jira Query Language (optional)
include_comments = false
include_attachments = false
```

#### Jira Cloud Source

```toml
[sources.jira]
url = "https://company.atlassian.net"
email = "user@company.com"
api_token = "secret"              # Via environment or .env
jql = "project = DOCS"            # Optional
include_comments = false
include_attachments = false
```

#### Confluence Server/DC Source

```toml
[sources.confluence]
url = "https://confluence.company.com"
username = "user@company.com"
api_token = "secret"              # Via environment or .env
space_key = "DOCS"                # Optional: specific space
include_comments = false
include_attachments = false
```

#### Confluence Cloud Source

```toml
[sources.confluence]
url = "https://company.atlassian.net/wiki"
email = "user@company.com"
api_token = "secret"              # Via environment or .env
space_key = "DOCS"                # Optional: specific space
include_comments = false
include_attachments = false
```

### Application Configuration

```toml
[app.search]
max_results = 10                  # Default max results for CLI searches

[mcp]
log_level = "INFO"                # MCP server logging level
transport = "stdio"               # stdio, http, sse
port = 8000                       # HTTP port if using http transport
```

## Environment Variables

Configuration can be overridden via environment variables:

**Pattern:** `INDEXED__section__key=value`

**Examples:**
```bash
# Override search max_docs
export INDEXED__core__v1__search__max_docs=50

# Override Jira URL
export INDEXED__sources__jira__url=https://jira.example.com

# Override storage mode
export INDEXED__storage__mode=local

# Override MCP log level
export INDEXED__mcp__log_level=DEBUG
```

**Automatic Parsing:**
- `true`/`false` → boolean
- `123` → integer
- `[1,2,3]` → list
- `{"key": "value"}` → dict
- Otherwise → string

## Sensitive Field Handling

Certain fields are automatically routed to `.env` files:

**Sensitive Field Names:**
- `api_key`, `apiKey`, `api_key_secret`
- `token`, `access_token`, `refresh_token`
- `password`, `passwd`
- `secret`
- `username` (when paired with sensitive auth)
- Any field annotated with `Sensitive` type

**Example:**
```toml
# config.toml (world-readable)
[sources.jira]
url = "https://jira.company.com"
username = "user@company.com"
# api_token NOT in config.toml
```

```bash
# .env (should be .gitignored and carefully protected)
INDEXED__sources__jira__api_token=secret_token_here
```

**Why?** Prevents accidental credential commits and follows security best practices.

## TOML File Structure

Complete example configuration:

```toml
# Core indexing and search configuration
[core.v1.indexing]
chunk_size = 512
chunk_overlap = 50
batch_size = 32

[core.v1.search]
max_docs = 20
max_chunks = 5
min_score = 0.0

[core.v1.vector_store]
index_type = "IndexFlatL2"

[core.v1.embedding]
model_name = "all-MiniLM-L6-v2"

# Application-level configuration
[app.search]
max_results = 10

# MCP Server configuration
[mcp]
log_level = "INFO"
transport = "stdio"

# Data source configurations (optional, per collection)
[sources.files]
path = "./documents"

[sources.jira]
url = "https://jira.company.com"
username = "user@company.com"
# api_token via environment or .env

[sources.confluence]
url = "https://confluence.company.com"
username = "user@company.com"
# api_token via environment or .env

# Storage configuration
[storage]
mode = "global"  # global or local
```

## Usage Patterns

### Pattern 1: Get Configuration at Startup

```python
def main():
    """Application entry point."""
    # Initialize configuration singleton
    config = ConfigService.instance()

    # Get values with defaults
    max_results = config.get("app.search.max_results", default=10)

    # Run application
    run_app()
```

### Pattern 2: Component-Level Configuration

```python
from pydantic import BaseModel

class SearchConfig(BaseModel):
    """Search service configuration."""
    max_results: int = 20
    min_score: float = 0.0

class SearchService:
    def __init__(self):
        config = ConfigService.instance()
        self.config = config.get_typed("core.v1.search", SearchConfig)

    def search(self, query: str):
        # Use self.config.max_results
        pass
```

### Pattern 3: CLI Command with Configuration Override

```python
from typer import Option

def search_command(
    query: str = Argument(...),
    max_results: int = Option(None, help="Override max results"),
):
    """Search with optional CLI overrides."""
    config = ConfigService.instance()

    # Get from config or use CLI override
    max_results = max_results or config.get("app.search.max_results")

    # Perform search
    pass
```

### Pattern 4: Validate Configuration Before Use

```python
def validate_sources():
    """Validate source configurations before indexing."""
    config = ConfigService.instance()

    try:
        config.validate()
        print("Configuration is valid")
    except ValidationError as e:
        print(f"Configuration errors: {e}")

        # Get missing required fields
        missing = config.validate_requirements()
        if missing:
            prompt_user_for_fields(missing)
```

## StorageResolver

Internal utility for resolving storage paths:

```python
from indexed_config.storage import StorageResolver

resolver = StorageResolver()

# Get storage root (global or local)
storage_root = resolver.get_storage_root()
# Returns: Path("~/.indexed") or Path("./.indexed")

# Get data directory
data_dir = resolver.get_data_directory()
# Returns: Path("~/.indexed/data") or Path("./.indexed/data")

# Get collections directory
collections_dir = resolver.get_collections_directory()
# Returns: Path("~/.indexed/data/collections") or Path("./.indexed/data/collections")

# Get specific collection directory
collection_dir = resolver.get_collection_directory("my-docs")
# Returns: Path("~/.indexed/data/collections/my-docs")

# Get config file path
config_file = resolver.get_config_file()
# Returns: Path("~/.indexed/config.toml")

# Get .env file path
env_file = resolver.get_env_file()
# Returns: Path("~/.indexed/.env")
```

## TomlStore API

Internal utility for TOML file I/O:

```python
from indexed_config.store import TomlStore

store = TomlStore(config_path=Path("~/.indexed/config.toml"))

# Load TOML file
config_dict = store.load()

# Save TOML file
store.save(config_dict)

# Get value from TOML (dot-path notation)
value = store.get("core.v1.search.max_docs")

# Set value in TOML (creates intermediate keys as needed)
store.set("core.v1.search.max_docs", 25)

# Delete value from TOML
store.delete("core.v1.search.max_docs")

# Clear entire section
store.clear("core.v1.search")
```

## Testing Configuration

### Unit Testing Configuration Loading

```python
import tempfile
from pathlib import Path
from indexed_config import ConfigService

def test_load_global_config():
    """Test loading global configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "config.toml"
        config_file.write_text("""
[core.v1.search]
max_docs = 15
""")

        config = ConfigService(config_file=config_file)

        assert config.get("core.v1.search.max_docs") == 15
```

### Unit Testing Configuration Merging

```python
def test_env_override_config():
    """Test environment variable overriding config file."""
    import os

    config = ConfigService()
    os.environ["INDEXED__core__v1__search__max_docs"] = "30"

    # Reload configuration
    config._reload_from_env()

    assert config.get("core.v1.search.max_docs") == 30

    # Cleanup
    del os.environ["INDEXED__core__v1__search__max_docs"]
```

### Unit Testing Configuration Validation

```python
from pydantic import BaseModel, ValidationError

class TestConfig(BaseModel):
    required_field: str
    optional_field: str = "default"

def test_validate_configuration():
    """Test configuration validation."""
    config = ConfigService()

    # Valid configuration
    valid = {"required_field": "value"}
    validated = TestConfig(**valid)
    assert validated.required_field == "value"

    # Invalid configuration (missing required field)
    invalid = {}
    with pytest.raises(ValidationError):
        TestConfig(**invalid)
```

## Common Patterns & Best Practices

### Best Practice 1: Lazy ConfigService Initialization

```python
# ✅ GOOD - Initialize when needed
def my_command():
    config = ConfigService.instance()  # Only when command runs
    value = config.get("...")
    pass

# ❌ BAD - Module-level initialization
config = ConfigService.instance()  # Slows down CLI startup for --help

def my_command():
    value = config.get("...")
    pass
```

### Best Practice 2: Use Typed Configuration

```python
# ✅ GOOD - Type-safe access
from core.v1.config_models import SearchConfig

config = ConfigService.instance()
search_config = config.get_typed("core.v1.search", SearchConfig)
value = search_config.max_docs  # IDE autocomplete, type checking

# ❌ BAD - String-based access
value = config.get("core.v1.search.max_docs")  # No type safety
```

### Best Practice 3: Validate Before Use

```python
# ✅ GOOD - Validate configuration
config = ConfigService.instance()
try:
    config.validate()
except ValidationError as e:
    print(f"Invalid configuration: {e}")
    sys.exit(1)

# ❌ BAD - Assume configuration is valid
config = ConfigService.instance()
value = config.get("required.field")  # May be None or invalid
```

### Best Practice 4: Use Dot-Paths for Nested Access

```python
# ✅ GOOD - Dot-path for nested values
value = config.get("core.v1.search.max_docs")

# ❌ BAD - Manual dictionary navigation
config_dict = config.get("core.v1.search")
value = config_dict.get("max_docs")  # Error-prone
```

## Troubleshooting

### Configuration Not Loading

**Problem:** Configuration file exists but not being read.

**Solution:**
```python
from indexed_config.storage import StorageResolver

resolver = StorageResolver()
config_file = resolver.get_config_file()
print(f"Looking for config at: {config_file}")
print(f"File exists: {config_file.exists()}")
```

### Environment Variables Not Applied

**Problem:** Environment variables defined but not affecting configuration.

**Solution:**
```bash
# Ensure correct environment variable format
export INDEXED__section__key=value

# For example:
export INDEXED__core__v1__search__max_docs=50

# Verify it's set
echo $INDEXED__core__v1__search__max_docs
```

### Sensitive Fields in Config

**Problem:** Accidentally committed API tokens to config.toml.

**Solution:**
1. Remove token from config.toml
2. Set via environment variable: `export INDEXED__sources__jira__api_token=token`
3. Or add to .env file (which is .gitignored)
4. Rotate the compromised token

## Related Documentation

- **[Root CURSOR.md](../../CURSOR.md)** - Project overview
- **[CLI CURSOR.md](../../apps/indexed/CURSOR.md)** - CLI commands
- **[Core Engine CURSOR.md](../../packages/indexed-core/CURSOR.md)** - Engine architecture
- **[Connectors CURSOR.md](../../packages/indexed-connectors/CURSOR.md)** - Connector system
- **[Utilities CURSOR.md](../../packages/utils/CURSOR.md)** - Utilities

---

**Last Updated:** January 24, 2026
