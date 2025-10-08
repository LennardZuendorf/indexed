# Project Brief - Indexed Python

## Product Overview

**Product Name**: Indexed - Document Search CLI  
**Status**: Phase 1 Complete ✅ | Phase 2 Standardization In Progress 🔄  
**Current Branch**: building 
**Last Updated**: 2025-10-08

## What We're Building

A simple, privacy-first command-line tool for semantic document search built on modern vector search technology (FAISS + embeddings). The system allows developers to index local documents and perform fast semantic searches without sending data to third parties.

## Core Value Proposition

1. **Privacy-First**: All processing and storage happens locally
2. **Semantic Search**: Understands meaning, not just keywords
3. **Simple Setup**: Fast installation and intuitive CLI commands
4. **Developer-Friendly**: Clean CLI interface with helpful output

## Target Users

**Primary User: Individual Developer** 👨‍💻
- Software engineers, researchers, technical writers
- Need to search through project documentation, notes, code comments
- Want fast, semantic search through personal document collections
- Value privacy and local-first approach

## Current Architecture Status

### Monorepo Structure (Implemented)
```
indexed-python/
├── apps/
│   └── indexed-cli/          # CLI + MCP Server application
├── packages/
│   └── indexed-core/         # Core library (legacy + new implementation)
├── tests/                    # Test suite
└── data/                     # Local data storage
```

### Current Implementation State

**Phase 1: Monorepo Migration ✅ COMPLETE (2025-10-08)**
- ✅ Monorepo structure established (apps/, packages/)
- ✅ All packages properly configured
- ✅ CLI commands fully functional
- ✅ MCP server working with search and inspect tools
- ✅ All imports and dependencies resolved
- ✅ Legacy code preserved and working

**Phase 2: Standardization & Refactoring 🔄 IN PROGRESS**
- 📋 Unified configuration management system
- 📋 Standardized connector interface (protocol-based)
- 📋 Clean core service API
- 📋 Simplified import paths
- 📋 Legacy migration with deprecation warnings
- 📋 Comprehensive documentation

**Phase 3: Enhancements 📋 PLANNED**
- 📋 Enhanced CLI with Rich UI components
- 📋 Additional connectors (Git, Notion)
- 📋 Additional embedding providers (OpenAI, Voyage AI)
- 📋 Performance optimizations

## Key Features

### Current Features (Legacy)
- Multi-source document indexing (Jira, Confluence, Local Files)
- FAISS vector similarity search
- Sentence-transformers embeddings (local)
- Collection management
- MCP server for AI agent integration
- TOML configuration

### Planned Features (Next Phases)
- Enhanced CLI output with Rich components
- Web server UI for browser-based search
- Better error handling and user feedback
- Progress indicators and status updates
- Improved configuration management

## Target API & Workflow

**Python API (Core V1)**
```python
# Collection-based API
from core.v1 import Index, Config
from core.v1.connectors import JiraConnector, FileSystemConnector

# Initialize
config = Config.from_file("indexed.toml")  # Reads [indexer.v1] section
index = Index(config)

# Add collections
jira = JiraConnector(config)
index.add_collection(jira, name="jira")

files = FileSystemConnector('./docs')
index.add_collection(files, name="docs")

# Search all collections
results = index.search("authentication methods")

# Search specific collection
results = index.search(collection="jira", query="What was project xyz?")

# Inspect
stats = index.inspect()  # All collections
stats = index.inspect(collection="jira")  # Specific collection
```

**CLI (Dual Command Groups)**
```bash
# Collection management
indexed-cli add files ./documents --name docs
indexed-cli add jira --name jira
indexed-cli list
indexed-cli remove docs

# Search operations
indexed-cli search "authentication methods"           # All collections
indexed-cli search "query" --collection jira          # Specific collection

# Maintenance
indexed-cli update jira
indexed-cli inspect
indexed-cli inspect --collection docs

# Config commands - configuration management
indexed-cli config show
indexed-cli config set KEY VALUE
indexed-cli config validate
indexed-cli config init

# MCP server for AI agents
indexed-mcp
```

**Config File (Versioned)**
```toml
# indexed.toml
[indexer.v1]
embedding_model = "all-MiniLM-L6-v2"
storage_path = ".indexed/v1"  # Automatically versioned
chunk_size = 512
```

## Technical Foundation

**Core Stack:**
- Python 3.10+ (using uv for package management)
- FAISS for vector storage
- Sentence-transformers / OpenAI / Voyage AI for embeddings
- Typer for CLI framework
- FastMCP for AI agent integration
- Pydantic for configuration and data validation

**Architecture Principles:**
1. **KISS First**: Simple, clean API over complex patterns
2. **Versioned API**: `core.v1` with versioned config and storage (`.indexed/v1/`)
3. **Dual CLI**: Separate index commands (operations) and config commands (management)
4. **Monorepo Structure**: Clean separation of apps and packages
5. **Type Safety**: Type hints where they add value, Pydantic for config validation

## Current Tasks & Focus

### Active Development
- Monorepo structure completion and dependency fixes
- CLI restoration and namespace adjustments
- Package versioning and import structure
- Getting basic functionality working again

### Success Criteria
- ✅ Monorepo structure properly configured
- ✅ CLI commands functional and working
- ✅ Dependencies resolved (uv.lock fixed)
- ✅ Enhanced CLI output with Rich components
- ✅ Web server UI ready for use

## Project Goals

### Short-term (Current Phase)
1. Complete monorepo restructuring and get CLI working
2. Fix pyproject.toml files and dependency issues
3. Restore basic functionality (index, search, inspect)
4. Ensure all packages import and work correctly

### Medium-term
1. Enhanced CLI with Rich UI components
2. Better progress indicators and user feedback
3. Improved error messages and validation
4. Command structure optimization

### Long-term
1. Web server UI development
2. HTTP API for browser-based interface
3. Core V2 API with enhanced features (different config structure, no conflicts with v1)
4. Advanced connectors and enterprise features

## Development Principles

**KISS (Keep It Simple, Stupid)**
- Start with simplest solution that works
- Add complexity only when needed
- Prefer clarity over cleverness

**Quality First**
- Type hints and validation everywhere
- Comprehensive testing
- Clear error messages
- Good documentation

**Privacy & Local-First**
- Default to local processing
- Cloud features are optional
- User data never leaves their machine (unless explicitly configured)

## Links & Resources

- Architecture: See `ARCHITECTURE.md` and `.memory/architecture.md`
- Tech Stack: See `.memory/tech.md`
- Development Guide: See `DEVELOPMENT.md`
- PRD Documents: See `.prd/` directory
- Implementation Plans: See `PHASE2_IMPLEMENTATION_PLAN.md`
