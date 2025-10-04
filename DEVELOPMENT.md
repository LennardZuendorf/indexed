# Development Guide

This guide explains how to work with the indexed-python monorepo.

## Architecture Overview

The project uses a **monorepo structure** with two packages:

```
indexed-python/
├── packages/
│   ├── indexed-core/      # Core library (shared business logic)
│   └── indexed-cli/       # CLI application and MCP server
├── pyproject.toml         # Workspace configuration
└── tests/                 # Test suite
```

### Package Responsibilities

**`indexed-core`** - Core library
- Document readers (Jira, Confluence, files)
- Vector indexing with FAISS
- Search functionality
- Business logic and services
- **Dependencies**: faiss-cpu, sentence-transformers, langchain, unstructured

**`indexed-cli`** - CLI application
- Command-line interface with Typer
- MCP server with FastMCP
- User interaction and presentation
- **Dependencies**: typer, rich, mcp, fastmcp + indexed-core

## Setup

### Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) package manager

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd indexed-python
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```
   
   This installs both packages in development mode along with all dependencies.

3. **Verify installation**
   ```bash
   uv run indexed-cli --help
   uv run indexed-mcp --help
   ```

## Development Workflow

### Running Commands

Use `uv run` to execute CLI commands:

```bash
# Run CLI
uv run indexed-cli inspect
uv run indexed-cli search "query"

# Run MCP server
uv run indexed-mcp --host localhost --port 8000
```

### Making Code Changes

#### Editing Core Library (`indexed-core`)

1. Make changes in `packages/indexed-core/src/indexed_core/`
2. No rebuild needed - changes take effect immediately (editable install)
3. Test your changes:
   ```bash
   uv run indexed-cli <command>
   ```

#### Editing CLI (`indexed-cli`)

1. Make changes in `packages/indexed-cli/src/indexed_cli/`
2. Test immediately:
   ```bash
   uv run indexed-cli <command>
   ```

### Adding Dependencies

#### To `indexed-core`:
```bash
cd packages/indexed-core
uv add <package-name>
```

#### To `indexed-cli`:
```bash
cd packages/indexed-cli
uv add <package-name>
```

#### Development dependencies (workspace level):
Edit the root `pyproject.toml` and add to `[dependency-groups]` section, then run:
```bash
uv sync
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_file.py

# Run with coverage
uv run pytest --cov=packages/indexed-core/src --cov=packages/indexed-cli/src
```

### Linting and Formatting

```bash
# Check code with ruff
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .

# Format code
uv run ruff format .

# Type checking with mypy
uv run mypy packages/indexed-core/src packages/indexed-cli/src
```

## Project Structure Details

### Core Library Structure

```
packages/indexed-core/src/indexed_core/
├── legacy/                    # Current implementation
│   ├── services/             # Business logic services
│   ├── sources/              # Data source readers
│   ├── indexes/              # Vector indexing
│   ├── utils/                # Utility functions
│   └── ...
└── config/                   # Configuration management
```

### CLI Structure

```
packages/indexed-cli/src/indexed_cli/
├── app.py                    # Main CLI application
├── commands/                 # Command implementations
│   ├── create.py            # Create collections
│   ├── search.py            # Search commands
│   ├── update.py            # Update collections
│   ├── delete.py            # Delete collections
│   └── legacy.py            # Legacy command proxies
└── server/
    └── mcp.py               # FastMCP server
```

## Common Tasks

### Creating a Test Collection

```bash
# From local files
uv run indexed-cli create files test-collection --basePath ./docs

# Inspect collections
uv run indexed-cli inspect

# Search
uv run indexed-cli search "query text"
```

### Debugging

1. Add print statements or use Python debugger
2. Run with verbose output (if implemented)
3. Check logs in `./data/` directory

### Building Packages

```bash
# Build indexed-core
cd packages/indexed-core
uv build

# Build indexed-cli
cd packages/indexed-cli
uv build
```

Built packages appear in `dist/` directories.

## Git Workflow

### Branch Strategy

- `main` - Stable production code
- `phase1-monorepo-migration` - Current migration work (temporary)
- Feature branches - `feature/description`
- Bug fixes - `fix/description`

### Committing Changes

```bash
# Stage changes
git add .

# Commit with descriptive message
git commit -m "feat: add new feature"

# Push
git push origin branch-name
```

### Commit Message Format

Follow conventional commits:
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Test updates
- `chore:` - Build/tooling changes

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError`:
```bash
# Reinstall in development mode
uv sync --reinstall
```

### Dependency Issues

```bash
# Clear cache and reinstall
rm -rf .venv
uv sync
```

### Build Issues

```bash
# Clean build artifacts
find . -type d -name "*.egg-info" -exec rm -rf {} +
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +
```

## Next Steps (Phase 2)

The current structure uses the legacy implementation in `indexed_core.legacy/`. 

**Phase 2** will involve:
- Implementing new LlamaIndex-based core in `indexed_core.llamaindex/`
- Gradually migrating from legacy to new implementation
- Enhanced CLI with rich UI components

See `.prd/MIGRATION_IMPLEMENTATION_PLAN.md` for details.

## Resources

- [uv Documentation](https://docs.astral.sh/uv/)
- [Typer Documentation](https://typer.tiangolo.com/)
- [FAISS Documentation](https://github.com/facebookresearch/faiss)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)

## Getting Help

- Check existing issues on GitHub
- Review PRD documents in `.prd/`
- Consult MIGRATION_IMPLEMENTATION_PLAN.md
