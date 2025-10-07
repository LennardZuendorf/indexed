# Project Brief - Indexed Python

## Product Overview

**Product Name**: Indexed - Document Search CLI  
**Status**: Phase 2 - Controller/Service Architecture Implementation  
**Current Branch**: `phase2-controller-service`

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

**Completed:**
- ✅ Monorepo migration (packages structure)
- ✅ Legacy implementation working (Jira, Confluence, Files connectors)
- ✅ Basic CLI commands functional
- ✅ MCP server integration
- ✅ FAISS vector storage with sentence-transformers

**In Progress (Phase 2):**
- 🔄 New controller/service architecture
- 🔄 Configuration system with Pydantic
- 🔄 Clean separation: Controllers → Services → Infrastructure
- 🔄 Cloud embedding support (OpenAI, Voyage AI)

**Planned:**
- 📋 Enhanced CLI with Rich UI components
- 📋 Improved error handling and validation
- 📋 Better progress indicators
- 📋 Migration tools from legacy to new architecture

## Key Features

### Current Features (Legacy)
- Multi-source document indexing (Jira, Confluence, Local Files)
- FAISS vector similarity search
- Sentence-transformers embeddings (local)
- Collection management
- MCP server for AI agent integration
- TOML configuration

### New Features (Phase 2)
- Controller/Service architecture
- Multiple embedding providers (OpenAI, Voyage AI, local)
- Enhanced configuration management
- Better error handling
- Improved testability

## Core Workflow

```bash
# Create a collection from local files
indexed-cli create files -c my-docs --basePath ./documents

# Search across collections
indexed-cli search "authentication methods" -c my-docs

# Inspect collections
indexed-cli inspect

# Start MCP server for AI agents
indexed-mcp
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
1. **Separation of Concerns**: Controllers → Services → Infrastructure
2. **Dependency Injection**: ServiceFactory pattern
3. **Configuration-Driven**: TOML + Pydantic models
4. **Testability**: All dependencies injected, easy to mock
5. **Type Safety**: Type hints throughout, Pydantic validation

## Current Tasks & Focus

### Active Development
- Implementing new controller/service architecture
- Adding cloud embedding providers
- Improving configuration management
- Enhancing error handling

### Success Criteria
- ✅ All existing commands work with new architecture
- ✅ Performance maintained or improved
- ✅ Cloud embeddings integrated
- ✅ Clean, testable codebase
- ✅ Backward compatible with existing data

## Project Goals

### Short-term (Current Phase)
1. Complete Phase 2 controller/service implementation
2. Integrate cloud embedding providers
3. Maintain backward compatibility
4. Improve code quality and testability

### Medium-term
1. Enhanced CLI with Rich UI components
2. Better progress indicators and feedback
3. Advanced search filtering
4. Collection health monitoring

### Long-term
1. Web server application (optional extension)
2. Advanced connectors (Git, Notion, etc.)
3. Multi-collection search optimization
4. Enterprise features

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
