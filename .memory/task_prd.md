# Product Requirements Document: Dynamic Connector Architecture (KISS Version)

**Date:** 2025-10-12  
**Status:** 📋 PLANNING  
**Version:** 2.0 - SIMPLIFIED  
**Mode:** PLAN MODE  
**Philosophy:** KISS - Keep It Simple, Stupid

---

## Problem Statement

**Current Issue**: Adding a new connector requires modifying CLI code (imports + command functions)

**Desired State**: Add connectors without touching CLI code

**That's it.** Everything else is overengineering.

---

## Proposed Solution: Simple Registry Pattern

### Core Idea

Instead of:
```python
from connectors import FileSystemConnector, JiraConnector
```

Do this:
```python
registry = {"files": FileSystemConnector, "jira": JiraConnector}
connector_class = registry[type]
```

**Key Insight**: We already have a working `BaseConnector` protocol. We just need a dict to look up implementations.

---

## Architecture: Dead Simple

```
┌─────────────────────────────────────────┐
│ CLI create.py                           │
│                                         │
│ registry = {                            │
│   "files": FileSystemConnector,        │
│   "jira": JiraConnector,                │
│ }                                       │
│                                         │
│ connector = registry[type](**config)   │
│ index.add_collection(name, connector)  │
└─────────────────────────────────────────┘
```

**Where does registry come from?**

Option 1: **Hardcoded dict** (simplest, works today)
Option 2: **Entry points** (enables third-party, requires packaging)
Option 3: **Both** (entry points override hardcoded)

**Decision: Start with Option 3, but make Option 1 work perfectly first**

---

## Implementation Plan (KISS)

### Phase 1: Make It Work (1 day)

**Goal**: Dynamic loading with hardcoded registry

**Changes**:
1. Create `indexed/src/indexed/connectors/__init__.py`:
```python
"""Connector registry - simple dict mapping names to classes."""

from connectors import (
    FileSystemConnector,
    JiraConnector,
    JiraCloudConnector,
    ConfluenceConnector,
    ConfluenceCloudConnector,
)

# Simple registry - just a dict!
CONNECTORS = {
    "files": FileSystemConnector,
    "jira": JiraConnector,
    "jira-cloud": JiraCloudConnector,
    "confluence": ConfluenceConnector,
    "confluence-cloud": ConfluenceCloudConnector,
}

def get_connector_class(name: str):
    """Get connector class by name."""
    if name not in CONNECTORS:
        available = ", ".join(CONNECTORS.keys())
        raise ValueError(f"Unknown connector '{name}'. Available: {available}")
    return CONNECTORS[name]

def list_connectors():
    """List available connector names."""
    return list(CONNECTORS.keys())
```

2. Update `create.py`:
```python
"""Create command - now with dynamic connectors."""

import typer
from core.v1 import Index
from ..connectors import get_connector_class, list_connectors

app = typer.Typer()

@app.command()
def create(
    type: str = typer.Option(..., "--type", "-t", help="Connector type"),
    name: str = typer.Option(..., "--name", "-n", help="Collection name"),
    # TODO: Dynamic config parsing later
):
    """Create a collection."""
    connector_class = get_connector_class(type)
    
    # For now, prompt for config manually
    config = _prompt_for_config(type)
    
    connector = connector_class(**config)
    index = Index()
    index.add_collection(name, connector)
    typer.echo(f"✓ Created '{name}'")

def _prompt_for_config(type: str) -> dict:
    """Prompt for connector-specific config."""
    # SIMPLE: Just hardcode for now, improve later
    if type == "files":
        return {
            "path": typer.prompt("Path"),
            "include_patterns": [],
            "exclude_patterns": [],
        }
    elif type in ["jira", "jira-cloud"]:
        return {
            "url": typer.prompt("Jira URL"),
            "query": typer.prompt("JQL Query"),
            # auth from env vars
        }
    # etc.
```

**Result**: Works immediately, no breaking changes, enables `indexed create --type files`

---

### Phase 2: Add Entry Points (1 day)

**Goal**: Enable third-party connectors via pip install

**Changes**:
1. Add entry point discovery to registry:
```python
"""Connector registry with entry point support."""

from importlib.metadata import entry_points

# Built-in connectors (fallback)
CONNECTORS = {
    "files": FileSystemConnector,
    "jira": JiraConnector,
    # ...
}

def _discover_connectors():
    """Discover connectors from entry points."""
    connectors = CONNECTORS.copy()
    
    # Override with entry points (if installed)
    try:
        for ep in entry_points(group="indexed.connectors"):
            connectors[ep.name] = ep.load()
    except Exception:
        pass  # Fail gracefully
    
    return connectors

# Build registry on import
_REGISTRY = _discover_connectors()

def get_connector_class(name: str):
    return _REGISTRY[name]
```

2. Add entry points to `indexed-connectors/pyproject.toml`:
```toml
[project.entry-points."indexed.connectors"]
files = "connectors.files:FileSystemConnector"
jira = "connectors.jira:JiraConnector"
```

**Result**: Third-party connectors work with `pip install indexed-connector-github`

---

### Phase 3: Better Config (Optional, 2 days)

**Goal**: Stop hardcoding config prompts

**Approach**: Each connector provides a simple config helper

**Example**:
```python
# In connector package
class FileSystemConnector:
    # Existing code...
    
    @staticmethod
    def prompt_config():
        """Prompt user for config (CLI helper)."""
        return {
            "path": typer.prompt("Path"),
            "include_patterns": typer.prompt("Include patterns (optional)", default=""),
        }
    
    @staticmethod
    def config_fields():
        """Return field definitions for validation."""
        return {
            "path": {"type": str, "required": True, "description": "Path to files"},
            "include_patterns": {"type": list, "required": False},
        }
```

Then in CLI:
```python
def _prompt_for_config(connector_class) -> dict:
    """Prompt using connector's helper."""
    if hasattr(connector_class, "prompt_config"):
        return connector_class.prompt_config()
    else:
        # Fallback to manual prompts
        return {}
```

**Result**: Connectors control their own config UX

---

## What We're NOT Doing (Avoiding Overengineering)

### ❌ No Pydantic Schemas
**Why**: Connectors already validate config in `__init__`. Don't duplicate.
**Instead**: Use simple dicts, let connectors validate

### ❌ No ConnectorMetadata Dataclasses
**Why**: We don't need rich metadata to make this work
**Instead**: Connectors can optionally provide `__doc__`, `prompt_config()`, etc.

### ❌ No Manifest Files (connector.json)
**Why**: Entry points already provide discovery
**Instead**: Just use entry points (standard Python)

### ❌ No Registry Class
**Why**: A module-level dict is enough
**Instead**: Simple functions in `__init__.py`

### ❌ No Fancy CLI Subcommands
**Why**: `indexed create --type files` works fine
**Instead**: Keep simple flags

### ❌ No Separate Factory Functions
**Why**: Connectors are already factory functions (via `__init__`)
**Instead**: Call connector class directly

---

## Migration Path

### Current Command
```bash
indexed create files --name docs --path ./docs
```

### New Command (Phase 1)
```bash
indexed create --type files --name docs
# Interactive prompts for path
```

### Keep Old Commands (Deprecated)
```python
@app.command("files", deprecated=True)
def create_files(...):
    typer.echo("⚠️  Deprecated. Use: indexed create --type files")
    # Delegate to new command
```

---

## File Structure (Minimal)

```
indexed/
└── src/indexed/
    └── connectors/
        └── __init__.py          # Registry (50 lines)

indexed-connectors/
└── pyproject.toml               # Add entry points (5 lines)
```

**That's it.** No new packages, no complex structure.

---

## Testing Strategy (Simple)

1. **Unit test**: Registry returns correct classes
2. **Integration test**: `indexed create --type files` works
3. **E2E test**: Create collection, search it

**No need for**:
- Metadata validation tests
- Schema tests  
- Discovery mechanism tests
- Performance benchmarks

---

## Success Metrics (Realistic)

✅ **Must Have**:
- [ ] Can run `indexed create --type files --name docs`
- [ ] Adding new connector doesn't require CLI changes
- [ ] Existing commands still work (deprecated)

✅ **Nice to Have**:
- [ ] Third-party connectors work via pip install
- [ ] Config prompts are connector-specific

❌ **Don't Need**:
- Connector marketplace
- Version management
- Automatic dependency installation
- Rich metadata
- Documentation generation

---

## Timeline (Realistic)

- **Day 1**: Phase 1 - Basic registry (2 hours)
- **Day 2**: Phase 2 - Entry points (2 hours)
- **Day 3**: Phase 3 - Config helpers (optional, 4 hours)
- **Day 4**: Tests + docs (4 hours)

**Total: 1-2 days of actual work**

Not 4 weeks. Not 200 files. Just a simple registry.

---

## Decision: Start Even Simpler

**MVP (Minimum Viable Product)**:

1. Create registry dict in `indexed/connectors/__init__.py`
2. Update `create.py` to use registry
3. Add entry point discovery (10 lines)
4. Done.

**Later** (if needed):
- Better config prompts
- Connector helpers
- Third-party examples

---

## Code Changes (Complete)

### File 1: `indexed/src/indexed/connectors/__init__.py` (NEW)

```python
"""Simple connector registry."""

from importlib.metadata import entry_points
from connectors import (
    FileSystemConnector,
    JiraConnector,
    JiraCloudConnector,
    ConfluenceConnector,
    ConfluenceCloudConnector,
)

# Built-in connectors
_BUILTIN = {
    "files": FileSystemConnector,
    "jira": JiraConnector,
    "jira-cloud": JiraCloudConnector,
    "confluence": ConfluenceConnector,
    "confluence-cloud": ConfluenceCloudConnector,
}

def _load_entry_points():
    """Load connectors from entry points."""
    connectors = {}
    try:
        for ep in entry_points(group="indexed.connectors"):
            connectors[ep.name] = ep.load()
    except Exception:
        pass
    return connectors

# Registry = built-in + entry points
_REGISTRY = {**_BUILTIN, **_load_entry_points()}

def get_connector_class(name: str):
    """Get connector class by name."""
    if name not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys())
        raise ValueError(f"Unknown connector: {name}. Available: {available}")
    return _REGISTRY[name]

def list_connectors():
    """List available connector names."""
    return list(_REGISTRY.keys())

__all__ = ["get_connector_class", "list_connectors"]
```

### File 2: `indexed/src/indexed/knowledge/commands/create.py` (SIMPLIFIED)

```python
"""Create command with dynamic connectors."""

import os
import typer
from core.v1 import Index
from ...connectors import get_connector_class, list_connectors

app = typer.Typer(help="Create collections")

@app.command()
def create(
    type: str = typer.Option(..., "--type", "-t", help=f"Connector type: {', '.join(list_connectors())}"),
    name: str = typer.Option(..., "--name", "-n", help="Collection name"),
):
    """Create a new collection.
    
    Examples:
        indexed create --type files --name docs
        indexed create --type jira --name issues
    """
    # Get connector class
    connector_class = get_connector_class(type)
    
    # Prompt for config (simple version)
    config = _prompt_config(type)
    
    # Create connector and collection
    connector = connector_class(**config)
    index = Index()
    typer.echo(f"Creating collection '{name}'...")
    index.add_collection(name, connector)
    typer.echo(f"✓ Collection '{name}' created")


def _prompt_config(type: str) -> dict:
    """Simple config prompts."""
    if type == "files":
        return {
            "path": typer.prompt("Path to files"),
            "include_patterns": None,
            "exclude_patterns": None,
        }
    elif type in ["jira", "jira-cloud"]:
        url = typer.prompt("Jira URL")
        query = typer.prompt("JQL Query")
        
        is_cloud = url.endswith(".atlassian.net")
        if is_cloud:
            email = os.getenv("ATLASSIAN_EMAIL")
            token = os.getenv("ATLASSIAN_TOKEN")
            if not email or not token:
                typer.echo("Error: Set ATLASSIAN_EMAIL and ATLASSIAN_TOKEN", err=True)
                raise typer.Exit(1)
            return {"url": url, "query": query, "email": email, "api_token": token}
        else:
            token = os.getenv("JIRA_TOKEN")
            return {"url": url, "query": query, "token": token}
    
    elif type in ["confluence", "confluence-cloud"]:
        # Similar to jira
        pass
    
    return {}


# Keep legacy commands (deprecated)
@app.command("files", hidden=True, deprecated=True)
def legacy_files(
    name: str = typer.Option(..., "--name", "-n"),
    path: str = typer.Option(..., "--path", "-p"),
    include: list[str] = typer.Option(None, "--include"),
    exclude: list[str] = typer.Option(None, "--exclude"),
):
    """[DEPRECATED] Use 'indexed create --type files' instead."""
    typer.echo("⚠️  Deprecated: Use 'indexed create --type files'", err=True)
    
    from connectors import FileSystemConnector
    connector = FileSystemConnector(path=path, include_patterns=include, exclude_patterns=exclude)
    index = Index()
    index.add_collection(name, connector)
    typer.echo(f"✓ Collection '{name}' created")
```

### File 3: `packages/indexed-connectors/pyproject.toml` (ADD)

```toml
[project.entry-points."indexed.connectors"]
files = "connectors.files.connector:FileSystemConnector"
jira = "connectors.jira.connector:JiraConnector"
jira-cloud = "connectors.jira.connector:JiraCloudConnector"
confluence = "connectors.confluence.connector:ConfluenceConnector"
confluence-cloud = "connectors.confluence.connector:ConfluenceCloudConnector"
```

---

## That's It!

**3 files. ~150 lines total. Done.**

No complex metadata. No registries. No factories. No schemas.
Just a dict that maps names to classes.

**It works. It's extensible. It's KISS.**

---

## Future Enhancements (If Needed)

1. **Better Config Prompts**: Add `prompt_config()` method to connectors
2. **Config Validation**: Add `validate_config()` method to connectors  
3. **Connector Info**: Add `get_info()` classmethod returning name/description
4. **Interactive Mode**: `indexed create` shows menu of connectors

**But don't build them now. Build them when needed.**

---

**Status**: ✅ **READY FOR IMPLEMENTATION**  
**Complexity**: 🟢 **SIMPLE**  
**Timeline**: **1-2 days**
