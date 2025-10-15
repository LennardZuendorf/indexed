# Implementation Plan: Dynamic Connector Architecture (KISS Version)

**Date:** 2025-10-12  
**Status:** 📋 PLANNING  
**Version:** 2.0 - SIMPLIFIED  
**Mode:** PLAN MODE  
**Philosophy:** KISS - Keep It Simple, Stupid

---

## Overview

Transform hardcoded connector imports into a simple registry pattern.

**Core Principle**: Use a dict. That's it.

---

## The Entire Implementation

### Step 1: Create Registry (30 minutes)

**File**: `indexed/src/indexed/connectors/__init__.py` (NEW, ~50 lines)

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
            try:
                connectors[ep.name] = ep.load()
            except Exception:
                pass  # Skip broken connectors
    except Exception:
        pass  # No entry points available
    return connectors

# Registry = built-in + entry points (entry points override)
_REGISTRY = {**_BUILTIN, **_load_entry_points()}

def get_connector_class(name: str):
    """Get connector class by name.
    
    Raises:
        ValueError: If connector not found
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(f"Unknown connector: {name}. Available: {available}")
    return _REGISTRY[name]

def list_connectors():
    """List available connector names."""
    return sorted(_REGISTRY.keys())

__all__ = ["get_connector_class", "list_connectors"]
```

**Test**: 
```python
# tests/connectors/test_registry.py
def test_get_connector_class():
    from indexed.connectors import get_connector_class
    from connectors import FileSystemConnector
    
    cls = get_connector_class("files")
    assert cls == FileSystemConnector

def test_unknown_connector():
    from indexed.connectors import get_connector_class
    import pytest
    
    with pytest.raises(ValueError, match="Unknown connector"):
        get_connector_class("doesnt-exist")
```

---

### Step 2: Update Create Command (1 hour)

**File**: `indexed/src/indexed/knowledge/commands/create.py` (REPLACE)

```python
"""Create command with dynamic connectors."""

import os
import typer
from core.v1 import Index
from ...connectors import get_connector_class, list_connectors

app = typer.Typer(help="Create collections")


@app.command()
def create(
    type: str = typer.Option(..., "--type", "-t", help="Connector type"),
    name: str = typer.Option(..., "--name", "-n", help="Collection name"),
):
    """Create a new collection from a data source.
    
    Available connector types: files, jira, jira-cloud, confluence, confluence-cloud
    
    Examples:
        indexed create --type files --name docs
        indexed create --type jira --name issues
    """
    try:
        connector_class = get_connector_class(type)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        typer.echo(f"\nAvailable types: {', '.join(list_connectors())}")
        raise typer.Exit(1)
    
    # Prompt for config
    typer.echo(f"Configure {type} connector:")
    config = _prompt_config(type)
    
    # Create connector
    try:
        connector = connector_class(**config)
    except Exception as e:
        typer.echo(f"Error creating connector: {e}", err=True)
        raise typer.Exit(1)
    
    # Create collection
    index = Index()
    typer.echo(f"\nCreating collection '{name}'...")
    index.add_collection(name, connector)
    typer.echo(f"✓ Collection '{name}' created successfully")


def _prompt_config(type: str) -> dict:
    """Prompt for connector-specific configuration.
    
    TODO: Move this to connectors themselves via optional method
    """
    if type == "files":
        path = typer.prompt("Path to files/directory")
        include = typer.prompt("Include patterns (optional, comma-separated)", default="")
        exclude = typer.prompt("Exclude patterns (optional, comma-separated)", default="")
        
        return {
            "path": path,
            "include_patterns": [p.strip() for p in include.split(",")] if include else None,
            "exclude_patterns": [p.strip() for p in exclude.split(",")] if exclude else None,
        }
    
    elif type in ["jira", "jira-cloud"]:
        url = typer.prompt("Jira URL")
        query = typer.prompt("JQL Query")
        
        is_cloud = url.endswith(".atlassian.net")
        if is_cloud:
            email = os.getenv("ATLASSIAN_EMAIL")
            token = os.getenv("ATLASSIAN_TOKEN")
            if not email or not token:
                typer.echo("\nError: Set ATLASSIAN_EMAIL and ATLASSIAN_TOKEN environment variables", err=True)
                raise typer.Exit(1)
            return {"url": url, "query": query, "email": email, "api_token": token}
        else:
            token = os.getenv("JIRA_TOKEN")
            if not token:
                typer.echo("\nError: Set JIRA_TOKEN environment variable", err=True)
                raise typer.Exit(1)
            return {"url": url, "query": query, "token": token}
    
    elif type in ["confluence", "confluence-cloud"]:
        url = typer.prompt("Confluence URL")
        query = typer.prompt("CQL Query")
        
        is_cloud = url.endswith(".atlassian.net")
        if is_cloud:
            email = os.getenv("ATLASSIAN_EMAIL")
            token = os.getenv("ATLASSIAN_TOKEN")
            if not email or not token:
                typer.echo("\nError: Set ATLASSIAN_EMAIL and ATLASSIAN_TOKEN environment variables", err=True)
                raise typer.Exit(1)
            return {"url": url, "query": query, "email": email, "api_token": token}
        else:
            token = os.getenv("CONF_TOKEN")
            if not token:
                typer.echo("\nError: Set CONF_TOKEN environment variable", err=True)
                raise typer.Exit(1)
            return {"url": url, "query": query, "token": token}
    
    return {}


# Legacy commands (keep for backward compatibility)
@app.command("files", hidden=True, deprecated=True)
def legacy_files(
    name: str = typer.Option(..., "--name", "-n"),
    path: str = typer.Option(..., "--path", "-p"),
    include: list[str] = typer.Option(None, "--include"),
    exclude: list[str] = typer.Option(None, "--exclude"),
):
    """[DEPRECATED] Use 'indexed create --type files' instead."""
    typer.echo("⚠️  Deprecated: Use 'indexed create --type files --name <name>'", err=True)
    
    from connectors import FileSystemConnector
    connector = FileSystemConnector(path=path, include_patterns=include, exclude_patterns=exclude)
    
    index = Index()
    index.add_collection(name, connector)
    typer.echo(f"✓ Collection '{name}' created")


@app.command("jira", hidden=True, deprecated=True)
def legacy_jira(
    name: str = typer.Option(..., "--name", "-n"),
    url: str = typer.Option(..., "--url", "-u"),
    query: str = typer.Option(..., "--query", "-q"),
):
    """[DEPRECATED] Use 'indexed create --type jira' instead."""
    typer.echo("⚠️  Deprecated: Use 'indexed create --type jira --name <name>'", err=True)
    
    from connectors import JiraConnector, JiraCloudConnector
    
    is_cloud = url.endswith(".atlassian.net")
    if is_cloud:
        email = os.getenv("ATLASSIAN_EMAIL")
        token = os.getenv("ATLASSIAN_TOKEN")
        connector = JiraCloudConnector(url=url, query=query, email=email, api_token=token)
    else:
        token = os.getenv("JIRA_TOKEN")
        connector = JiraConnector(url=url, query=query, token=token)
    
    index = Index()
    index.add_collection(name, connector)
    typer.echo(f"✓ Collection '{name}' created")


@app.command("confluence", hidden=True, deprecated=True)
def legacy_confluence(
    name: str = typer.Option(..., "--name", "-n"),
    url: str = typer.Option(..., "--url", "-u"),
    query: str = typer.Option(..., "--query", "-q"),
):
    """[DEPRECATED] Use 'indexed create --type confluence' instead."""
    typer.echo("⚠️  Deprecated: Use 'indexed create --type confluence --name <name>'", err=True)
    
    from connectors import ConfluenceConnector, ConfluenceCloudConnector
    
    is_cloud = url.endswith(".atlassian.net")
    if is_cloud:
        email = os.getenv("ATLASSIAN_EMAIL")
        token = os.getenv("ATLASSIAN_TOKEN")
        connector = ConfluenceCloudConnector(url=url, query=query, email=email, api_token=token)
    else:
        token = os.getenv("CONF_TOKEN")
        connector = ConfluenceConnector(url=url, query=query, token=token)
    
    index = Index()
    index.add_collection(name, connector)
    typer.echo(f"✓ Collection '{name}' created")
```

**Test**:
```python
# tests/cli/test_create_dynamic.py
def test_create_files(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, [
        "create",
        "--type", "files",
        "--name", "test",
    ], input=f"{tmp_path}\n\n\n")
    
    assert result.exit_code == 0
    assert "created successfully" in result.output
```

---

### Step 3: Add Entry Points (15 minutes)

**File**: `packages/indexed-connectors/pyproject.toml` (MODIFY)

Add this section:

```toml
[project.entry-points."indexed.connectors"]
files = "connectors.files.connector:FileSystemConnector"
jira = "connectors.jira.connector:JiraConnector"
jira-cloud = "connectors.jira.connector:JiraCloudConnector"
confluence = "connectors.confluence.connector:ConfluenceConnector"
confluence-cloud = "connectors.confluence.connector:ConfluenceCloudConnector"
```

**Test**:
```bash
uv run indexed create --type files --name test
# Should work after re-installing package
```

---

### Step 4: Update CLI Registration (5 minutes)

**File**: `indexed/src/indexed/knowledge/cli.py` (VERIFY)

Make sure new create command is registered:
```python
from .commands.create import app as create_app

app.add_typer(create_app, name="create")
```

---

## Testing

### Unit Tests (30 minutes)

```python
# tests/connectors/test_registry.py
def test_builtin_connectors():
    """Test built-in connectors are available."""
    connectors = list_connectors()
    assert "files" in connectors
    assert "jira" in connectors

def test_get_connector():
    """Test getting connector by name."""
    cls = get_connector_class("files")
    assert cls.__name__ == "FileSystemConnector"

def test_unknown_connector():
    """Test error for unknown connector."""
    with pytest.raises(ValueError):
        get_connector_class("nonexistent")
```

### Integration Tests (30 minutes)

```python
# tests/cli/test_create_command.py
def test_create_files_interactive(tmp_path):
    """Test creating files collection interactively."""
    runner = CliRunner()
    result = runner.invoke(
        create,
        ["--type", "files", "--name", "test"],
        input=f"{tmp_path}\n\n\n"
    )
    assert result.exit_code == 0

def test_legacy_command_works(tmp_path):
    """Test legacy command still works."""
    runner = CliRunner()
    result = runner.invoke(
        legacy_files,
        ["--name", "test", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "Deprecated" in result.output
```

---

## Documentation

### User Docs (30 minutes)

**Update**: `README.md`

Add section:
```markdown
## Creating Collections

Create collections from various data sources:

### Local Files
```bash
indexed create --type files --name docs
# Prompts for: path, include patterns, exclude patterns
```

### Jira
```bash
# Set environment variables first
export ATLASSIAN_EMAIL=your@email.com
export ATLASSIAN_TOKEN=your-token

indexed create --type jira-cloud --name issues
# Prompts for: URL, JQL query
```

### Legacy Commands (Deprecated)
Old commands still work but are deprecated:
```bash
indexed create files --name docs --path ./docs  # OLD WAY
indexed create --type files --name docs         # NEW WAY
```
```

---

## Timeline

**Total: 3-4 hours of actual work**

- [ ] **30 min**: Create registry module
- [ ] **60 min**: Update create command
- [ ] **15 min**: Add entry points
- [ ] **5 min**: Verify CLI registration
- [ ] **60 min**: Tests (unit + integration)
- [ ] **30 min**: Documentation

**That's it. Done in half a day.**

---

## Future Enhancements (Optional)

These can be added later **if needed**:

### 1. Connector Self-Description (Optional)

Allow connectors to describe themselves:

```python
class FileSystemConnector:
    @classmethod
    def get_info(cls):
        """Optional: Return connector info."""
        return {
            "name": "files",
            "display_name": "Local Files",
            "description": "Index local filesystem documents",
        }
    
    @classmethod
    def prompt_config(cls):
        """Optional: Custom config prompting."""
        return {
            "path": typer.prompt("Path"),
            # ...
        }
```

Then in CLI:
```python
if hasattr(connector_class, "prompt_config"):
    config = connector_class.prompt_config()
else:
    config = _prompt_config(type)  # Fallback
```

### 2. List Connectors Command (Optional)

```python
@app.command("list")
def list_available():
    """List available connector types."""
    for name in list_connectors():
        typer.echo(f"  - {name}")
```

### 3. Interactive Connector Selection (Optional)

```python
@app.command()
def create_interactive():
    """Interactive mode - choose connector from menu."""
    connectors = list_connectors()
    
    typer.echo("Available connectors:")
    for i, name in enumerate(connectors, 1):
        typer.echo(f"  {i}. {name}")
    
    choice = typer.prompt("Select connector", type=int)
    type = connectors[choice - 1]
    
    # Continue with normal flow...
```

**But don't build these now. Only if users ask for them.**

---

## What We're NOT Building

- ❌ Pydantic schemas
- ❌ Metadata dataclasses
- ❌ Manifest files
- ❌ Factory pattern
- ❌ Registry classes
- ❌ Separate packages
- ❌ Documentation generation
- ❌ Marketplace
- ❌ Versioning
- ❌ Dependency management

**Why?** Because we don't need them. The simple solution works.

---

## Success Criteria

✅ **Must Have**:
- [ ] Can run `indexed create --type files --name docs`
- [ ] Adding entry point adds new connector (no CLI changes)
- [ ] Legacy commands work with deprecation warning

✅ **Nice to Have**:
- [ ] Error messages are helpful
- [ ] Tests pass
- [ ] Documentation updated

---

## File Changes Summary

**New Files**: 1
- `indexed/src/indexed/connectors/__init__.py` (~50 lines)

**Modified Files**: 2
- `indexed/src/indexed/knowledge/commands/create.py` (replace, ~150 lines)
- `packages/indexed-connectors/pyproject.toml` (add 5 lines)

**Total New Code**: ~200 lines
**Deleted Code**: ~100 lines (old create functions)
**Net Change**: +100 lines

---

**Status**: ✅ **READY TO IMPLEMENT**  
**Complexity**: 🟢 **VERY SIMPLE**  
**Timeline**: **3-4 hours**  
**Risk**: 🟢 **LOW** (minimal changes, backward compatible)
