# Indexed - Product Requirements Document

## Overview

This directory contains the Product Requirements Document (PRD) for **indexed** - a simple, privacy-first command-line tool for semantic document search built on LlamaIndex and FAISS.

## 📁 PRD Structure

### Core Documentation
- **[prd.md](./prd.md)** - Business requirements, goals, user pains, market analysis
- **[tech.md](./tech.md)** - Technology stack, tools, and implementation choices
- **[architecture.md](./architecture.md)** - Code structure, repository infrastructure, deployment

### Current Implementation
- **[apps/cli.md](./apps/cli.md)** - CLI application specification (indexed-cli package)
- **[packages/core.md](./packages/core.md)** - Core search engine library (indexed-core package)

### Future Extensions  
- **apps/server.md.future** - Web server application (Phase 2)
- **packages/mcp-base.md.future** - MCP integration for AI agents (Phase 3)

### Additional Documentation
- **[feature-tiers.md](./feature-tiers.md)** - Open source vs Pro vs Enterprise features
- **[roadmap.md](./roadmap.md)** - Implementation timeline and milestones

## 🎆 Project Goals

1. **Simplicity**: One-command install and setup for document search
2. **Privacy**: All processing and storage happens locally
3. **Performance**: Sub-second search results on typical document collections
4. **Extensibility**: Clean architecture for future web UI and API extensions

## 🚀 Key Features

- **Semantic Search**: Understands meaning, not just keywords
- **Local-First**: All data stays on your machine
- **Fast Setup**: `pip install` and start searching in under 2 minutes
- **Multiple Formats**: PDF, DOCX, TXT, Markdown, and more
- **Developer-Friendly**: Clean CLI interface with helpful output

## 🏆 Extensible Architecture

```
indexed-python/
├── packages/
│   └── core/              # indexed-core library
├── apps/
│   ├── cli/               # indexed-cli (implement first)
│   └── server/            # Future: indexed-server

~/.indexed/
├── config.toml           # Configuration
└── data/                 # LlamaIndex collections and sources
```

## 🏗️ Design Principles

- **KISS**: Keep it simple and focused on core functionality
- **CLI-First**: Start with command-line interface, extend later
- **Local-First**: No network requests required for basic operation
- **Extensible**: Monorepo structure ready for server/UI extensions
- **Fast**: Optimized for quick indexing and sub-second search

## 🚀 Quick Start Example

```bash
# Install (Phase 1 - MVP)
pip install indexed-cli

# Setup and add sources (existing command structure)
indexed init
indexed source add folder --path ./my-documents --name "docs"
indexed source update docs

# Search semantically  
indexed search "deployment strategies"

# Search specific sources
indexed search "API examples" --sources docs

# Check status
indexed status
```

**Implementation Plan:**
- **Phase 1**: CLI + Core library (MVP) 
- **Phase 2**: Enhanced CLI features
- **Phase 3**: Web server extension using same core

---

*Last Updated: 2024-10-04*
*Version: 1.0 (CLI-First)*
