# Migration Guide - Phase 1: Monorepo Structure

This document explains the Phase 1 migration from a single-package structure to a monorepo with separated concerns.

## Overview

**Phase 1** restructures the codebase into a proper monorepo while preserving all existing functionality. The old `src/` directory has been split into two packages:

- **`packages/indexed-core`** - Core library with business logic
- **`packages/indexed-cli`** - CLI application and MCP server

## What Changed

### Before (Old Structure)

```
indexed-python/
├── src/
│   ├── cli/            # CLI code
│   ├── commands/       # Command implementations  
│   ├── main/           # Core business logic
│   ├── server/         # MCP server
│   └── config/         # Configuration
├── pyproject.toml      # Single package configuration
└── tests/
```

###After (New Structure)

```
indexed-python/
├── packages/
│   ├── indexed-core/           # Core library package
│   │   ├── src/indexed_core/
│   │   │   ├── legacy/        # Migrated business logic
│   │   │   │   ├── services/
│   │   │   │   ├── sources/
│   │   │   │   ├── indexes/
│   │   │   │   ├── utils/
│   │   │   │   └── ...
│   │   │   └── config/
│   │   └── pyproject.toml
│   └── indexed-cli/            # CLI package  
│       ├── src/indexed_cli/
│       │   ├── app.py
│       │   ├── commands/
│       │   └── server/
│       └── pyproject.toml
├── pyproject.toml              # Workspace configuration
├── tests/
└── DEVELOPMENT.md
```

## Import Changes

All import paths have been updated to reflect the new structure:

### Old Imports (No Longer Valid)
```python
from main.services import create, search, update
from main.core import DocumentsCollectionCreator
from cli.app import app
```

### New Imports
```python
# In CLI code
from indexed_core.legacy.services import create, search, update
from indexed_core.legacy.core import DocumentsCollectionCreator  
import indexed_cli.app as app

# In core library code
from indexed_core.legacy.services import SomeService
from indexed_core.legacy.utils import some_utility
```

## Commands

All CLI commands work exactly as before:

```bash
# Old command
python -m cli.app inspect

# New command
uv run indexed-cli inspect
```

### Available Commands

| Command | Description | Status |
|---------|-------------|--------|
| `indexed-cli inspect` | List collections | ✅ Working |
| `indexed-cli create files` | Create file collection | ✅ Working |
| `indexed-cli create jira` | Create Jira collection | ✅ Working |
| `indexed-cli create confluence` | Create Confluence collection | ✅ Working |
| `indexed-cli search` | Search collections | ⚠️ Data format issue (Phase 2 fix) |
| `indexed-cli update` | Update collections | ✅ Working |
| `indexed-cli delete` | Delete collections | ✅ Working |
| `indexed-cli legacy` | Access legacy commands | ✅ Working |
| `indexed-mcp` | Start MCP server | ✅ Working |

## Setup Instructions

### For Existing Users

If you were using the old structure:

1. **Pull the latest changes**
   ```bash
   git checkout phase1-monorepo-migration
   git pull
   ```

2. **Reinstall dependencies**
   ```bash
   rm -rf .venv
   uv sync
   ```

3. **Verify installation**
   ```bash
   uv run indexed-cli --help
   ```

4. **Your data is safe!**
   - Existing collections in `./data/collections/` work as-is
   - No data migration needed
   - All existing functionality preserved

### For New Users

Follow the standard setup in [DEVELOPMENT.md](./DEVELOPMENT.md).

## Package Separation

### indexed-core (Core Library)

**Purpose**: Shared business logic that can be reused by CLI, server, or other applications

**Contents**:
- Document readers (Jira, Confluence, files)
- Vector indexing with FAISS
- Search services
- Utilities and helpers

**Dependencies**: faiss-cpu, sentence-transformers, langchain, unstructured, pydantic-settings

**Use Cases**:
- CLI application (current)
- Future web server
- Future API services
- Future UI applications

### indexed-cli (CLI Application)

**Purpose**: User-facing command-line interface and MCP server

**Contents**:
- Typer-based CLI commands
- User interaction and presentation
- FastMCP server for AI agents
- Command implementations

**Dependencies**: typer, rich, mcp, fastmcp, + indexed-core

**Use Cases**:
- Local CLI usage
- MCP server for AI agent integration

## Development Workflow Changes

### Running the CLI

**Before**:
```bash
python -m cli.app <command>
# OR
python src/cli/app.py <command>
```

**After**:
```bash
uv run indexed-cli <command>
```

### Making Code Changes

**Before**:
- Edit files in `src/`
- All code in one place

**After**:
- **Core logic**: Edit `packages/indexed-core/src/indexed_core/`
- **CLI code**: Edit `packages/indexed-cli/src/indexed_cli/`
- Changes take effect immediately (editable install)

### Adding Dependencies

**Before**:
```bash
pip install <package>
# OR add to pyproject.toml dependencies
```

**After**:
```bash
# For core library
cd packages/indexed-core
uv add <package>

# For CLI
cd packages/indexed-cli  
uv add <package>

# Then sync workspace
cd ../..
uv sync
```

## Configuration and Data

### Data Directories

**No changes required!** All data directories remain in the same location:

- Collections: `./data/collections/`
- Caches: `./data/caches/`
- Configuration: Same as before

### Backward Compatibility

The new structure is fully backward compatible with existing:
- Collection data
- Configuration files
- Cache files
- MCP setup

## Known Issues

### Search Command Data Format

The `search` command has a data format issue where results aren't properly formatted for display. This is a legacy code issue that will be fixed in Phase 2 when we migrate to LlamaIndex.

**Workaround**: Use the `legacy` commands or JSON output:
```bash
# Use legacy search
uv run indexed-cli legacy collection-search --collection test-collection --query "search term"

# Or use JSON output
uv run indexed-cli search "search term" --json
```

## Testing

### Verify Migration Success

Run these commands to ensure everything works:

```bash
# 1. Check CLI help
uv run indexed-cli --help

# 2. List collections
uv run indexed-cli inspect

# 3. Create test collection  
mkdir test-docs
echo "# Test" > test-docs/test.md
uv run indexed-cli create files test-collection --basePath ./test-docs

# 4. Inspect again
uv run indexed-cli inspect

# 5. Check MCP server
uv run indexed-mcp --help
```

All commands should work without errors.

## Troubleshooting

### "ModuleNotFoundError: No module named 'indexed_core'"

**Solution**: Reinstall packages
```bash
uv sync --reinstall
```

### "ModuleNotFoundError: No module named 'main'"

**Solution**: You're trying to run old code. Use `uv run indexed-cli` instead of `python -m cli.app`

### CLI Commands Don't Work

**Solution**: Make sure you're in the project root and run:
```bash
uv sync
uv run indexed-cli --help
```

### Import Errors in Custom Code

If you have custom code that imports from the old structure, update imports:

```python
# Old
from main.services import search

# New  
from indexed_core.legacy.services import search
```

## Next Steps - Phase 2

Phase 1 establishes the monorepo foundation. **Phase 2** will:

1. **Implement LlamaIndex Integration**
   - Replace custom implementation with LlamaIndex
   - New code in `indexed_core.llamaindex/`
   - Gradual migration from `legacy/` to new implementation

2. **Enhanced CLI**
   - Rich UI components
   - Better progress indicators
   - Interactive configuration

3. **Fix Known Issues**
   - Resolve search command data format issue
   - Improve error handling
   - Add more comprehensive testing

See `.prd/MIGRATION_IMPLEMENTATION_PLAN.md` for full Phase 2 details.

## Benefits of This Migration

✅ **Clean Separation**: Core logic separate from CLI concerns  
✅ **Reusability**: Core library can be used by future server/UI  
✅ **Extensibility**: Easy to add new packages (server, web UI)  
✅ **Maintainability**: Clear boundaries and responsibilities  
✅ **Modern Tooling**: Proper use of uv workspaces  
✅ **Backward Compatible**: All existing functionality preserved  

## Questions?

- Check [DEVELOPMENT.md](./DEVELOPMENT.md) for development workflow
- See `.prd/` directory for product requirements and plans
- Review `pyproject.toml` files for package configurations

## Migration Timeline

- ✅ **Phase 1 Complete** (Current): Monorepo structure established
- 🔄 **Phase 2 Next**: LlamaIndex integration and enhanced CLI
- 📅 **Phase 3 Future**: Web server and UI extensions
