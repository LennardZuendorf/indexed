# UV Monorepo Structure Implementation Guide

Based on research from the Medium article and uv documentation, here's how to restructure the indexed-python project into a proper uv monorepo.

## Current Structure Analysis

```
indexed-python/
├── src/
│   ├── cli/           # CLI application
│   ├── server/        # MCP server 
│   ├── main/          # Core functionality
│   ├── commands/      # CLI commands
│   └── config/        # Configuration
├── pyproject.toml     # Monolithic config
└── tests/
```

## Target Monorepo Structure

```
indexed-python/
├── packages/
│   ├── indexed-core/              # Core indexing library (--lib)
│   │   ├── pyproject.toml
│   │   ├── uv.lock
│   │   └── src/
│   │       └── indexed_core/
│   │           ├── __init__.py
│   │           ├── core/          # from src/main/core/
│   │           ├── services/      # from src/main/services/
│   │           ├── sources/       # from src/main/sources/
│   │           ├── indexes/       # from src/main/indexes/
│   │           ├── persisters/    # from src/main/persisters/
│   │           ├── factories/     # from src/main/factories/
│   │           └── utils/         # from src/main/utils/
│   └── indexed-cli/               # CLI application + MCP server (--app)
│       ├── pyproject.toml
│       ├── uv.lock
│       └── src/
│           └── indexed_cli/
│               ├── __init__.py
│               ├── app.py         # from src/cli/app.py
│               ├── commands/      # from src/commands/
│               ├── config/        # from src/config/
│               └── mcp.py         # from src/server/mcp.py
├── pyproject.toml                 # Root workspace configuration
├── uv.lock                        # Unified lock file
├── tests/                         # Integration tests
├── README.md
└── .gitignore
```

## Implementation Steps

### 1. Create Package Structure

```bash
# Create packages directory
mkdir -p packages/{indexed-core,indexed-cli}

# Initialize core library package
cd packages/indexed-core
uv init --lib indexed-core

# Initialize CLI application (includes MCP server)
cd ../indexed-cli
uv init indexed-cli

cd ../..
```

### 2. Root Workspace pyproject.toml

Replace current pyproject.toml with:

```toml
[project]
name = "indexed-workspace"
version = "0.1.0"
description = "Document indexing workspace with CLI, MCP server and core libraries"
readme = "README.md"
requires-python = ">=3.10"

# Workspace configuration
[tool.uv.workspace]
members = ["packages/*"]

# Global dependency sources
[tool.uv.sources]
indexed-core = { workspace = true }

[build-system]
requires = ["uv_build>=0.8.22,<0.9.0"]
build-backend = "uv_build"

# Development dependencies for the workspace
[dependency-groups]
dev = [
    "mypy>=1.17.1",
    "pytest>=8.4.1",
    "pytest-cov>=4.1.0", 
    "pytest-mock>=3.14.1",
    "ruff>=0.12.10",
]

# Ruff configuration
[tool.ruff]
extend-exclude = [
    "packages/indexed-core/src/indexed_core/legacy/**",
]

[tool.ruff.lint.per-file-ignores]
"packages/indexed-core/src/indexed_core/sources/confluence/confluence_cloud_document_reader.py" = ["E731"]
"packages/indexed-core/src/indexed_core/sources/confluence/confluence_document_reader.py" = ["E731"]
"packages/indexed-core/src/indexed_core/sources/jira/jira_cloud_document_reader.py" = ["E731"]
"packages/indexed-core/src/indexed_core/sources/jira/jira_document_reader.py" = ["E731"]

# Pytest configuration
[tool.pytest.ini_options]
testpaths = ["packages/*/tests", "tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--strict-config",
    "--cov=packages/indexed-core/src/indexed_core/services",
    "--cov-report=term-missing",
    "--cov-report=html:htmlcov"
]

# MyPy configuration
[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
ignore_missing_imports = true
```

### 3. Core Library (packages/indexed-core/pyproject.toml)

```toml
[project]
name = "indexed-core"
version = "0.1.0"
description = "Core document indexing and search functionality"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "bs4>=0.0.2",
    "faiss-cpu>=1.11.0",
    "langchain>=0.3.26",
    "requests>=2.32.4",
    "sentence-transformers>=5.0.0",
    "unstructured[all-docs]>=0.18.5",
    "pydantic-settings>=2.2.1",
    "platformdirs>=4.2.0",
]

[build-system]
requires = ["uv_build>=0.8.22,<0.9.0"]
build-backend = "uv_build"
```

### 4. CLI Application + MCP Server (packages/indexed-cli/pyproject.toml)

```toml
[project]
name = "indexed-cli"
version = "0.1.0"
description = "CLI application and MCP server for document indexing and search"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "typer>=0.12.3",
    "mcp>=1.13.0",
    "fastmcp>=2.11.3",
    "indexed-core",
]

[project.scripts]
indexed-cli = "indexed_cli.app:app"
indexed-mcp = "indexed_cli.mcp:main"

[tool.uv.sources]
indexed-core = { workspace = true }

[build-system]
requires = ["uv_build>=0.8.22,<0.9.0"]
build-backend = "uv_build"
```

### 5. Move Source Files

```bash
# Move core functionality
cp -r src/main/* packages/indexed-core/src/indexed_core/

# Move CLI files and MCP server
cp -r src/cli/* packages/indexed-cli/src/indexed_cli/
cp -r src/commands packages/indexed-cli/src/indexed_cli/
cp -r src/config packages/indexed-cli/src/indexed_cli/
cp src/server/mcp.py packages/indexed-cli/src/indexed_cli/

# Update imports in moved files to use new package structure
```

### 6. Update Import Statements

In CLI files, change imports from:
```python
from main.services.collection_service import CollectionService
```

To:
```python
from indexed_core.services.collection_service import CollectionService
```

In MCP server file, change imports similarly.

### 7. Initialize and Test

```bash
# Initialize the workspace
uv sync

# Test individual packages
cd packages/indexed-core
uv run python -c "import indexed_core; print('Core package works')"

cd ../indexed-cli
uv run indexed-cli --help
uv run indexed-mcp

# Run tests
cd ../..
uv run pytest
```

## Key Benefits

1. **Independent Packages**: Each component can be developed, tested, and released independently
2. **Shared Dependencies**: Common dependencies managed at workspace level
3. **Editable Installs**: Changes in core library immediately available to CLI and MCP
4. **Unified Locking**: Single uv.lock for consistent dependency resolution
5. **Better Organization**: Clear separation of concerns

## Workspace Commands

```bash
# Sync all packages
uv sync

# Run commands in workspace context
uv run indexed-cli --help
uv run indexed-mcp

# Add dependency to specific package
cd packages/indexed-core
uv add requests

# Add dependency to CLI package (which includes MCP)
cd ../indexed-cli
uv add some-package

# Add dev dependency to workspace
cd ../..
uv add --dev pytest

# Build all packages
uv build

# Run tests across workspace
uv run pytest
```

## Migration Notes

- Keep the legacy `src/` structure temporarily during migration
- Update all import paths gradually
- Test each package independently after moving files  
- Consider keeping `src/main/legacy/` files in core package for backward compatibility
- Update CI/CD pipelines to work with workspace structure