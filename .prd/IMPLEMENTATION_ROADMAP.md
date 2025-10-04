# Implementation Roadmap - KISS Approach

## 🎯 Philosophy: CLI-First with Extensible Architecture

We're following KISS principles by implementing a CLI first, but with a monorepo architecture that's ready for future extensions. This gives us:

- **Immediate Value**: Working CLI for individual developers
- **Smart Foundation**: Extensible architecture without overengineering  
- **Clear Path**: Natural progression to server/UI when needed

## 📁 Current Repository Structure

```
indexed-python/
├── packages/
│   └── core/                    # 📦 indexed-core (shared library)
├── apps/
│   ├── cli/                     # 🖥️ indexed-cli (PHASE 1)
│   └── server/                  # 🌐 Future: indexed-server (PHASE 2+)
├── tests/                       # 🧪 Test suite
├── docs/                        # 📚 Documentation  
└── examples/                    # 📄 Usage examples
```

## 🚀 Implementation Phases

### Phase 1: CLI MVP (Focus Here First)
**Goal**: Get basic CLI working for individual developers

**Components to Build**:
- `packages/core/` - Core search library
  - LlamaIndex integration
  - FAISS vector store
  - Basic document ingestion (PDF, TXT, MD, DOCX)
  - Simple configuration management
- `apps/cli/` - CLI application
- `indexed source add folder` command
- `indexed search <query>` command  
- `indexed status` command
  - Basic progress indicators

**Success Criteria**:
- Install with `pip install indexed-cli`
- Index documents in under 1 minute
- Search results in under 1 second
- Clean, helpful CLI output

### Phase 2: Enhanced CLI (After MVP Works)
**Goal**: Improve CLI user experience

**Enhancements**:
- More file format support
- Better progress indicators and output
- Search filtering and sorting
- Collection management commands
- Configuration wizard

### Phase 3: Server Extension (Future)
**Goal**: Add web interface using same core

**New Components**:
- `apps/server/` - FastAPI web application
- REST API endpoints
- Simple web UI for search
- Multi-user support
- Hosted MCP server (not just local)

**Enhanced Infrastructure (Long-term)**:
- **Alternative Vector Stores**: Supabase pgvector, Qdrant for hosted/cloud deployments
- **Additional Embedding Models**: OpenAI, Cohere, or other cloud providers for server use
- **Hybrid Architecture**: Local FAISS + HuggingFace for CLI, cloud options for server

**Key**: Server uses the same `packages/core` library with pluggable storage/embedding backends

## 📋 MVP Feature Scope (Keep It Simple!)

### ✅ Include in MVP
- Basic document formats (PDF, TXT, MD, DOCX)
- Local vector storage with FAISS
- Simple CLI commands (index, search, list)
- HuggingFace embeddings (local, no API key needed)
- Local file-based configuration

### ❌ Skip for MVP (Add Later)
- Advanced file formats
- Complex search operators
- Multi-collection advanced features  
- Web interface
- Authentication
- Remote data sources (Jira, etc.)
- Cloud vector stores (Supabase pgvector, Qdrant)
- Alternative embedding providers (OpenAI, Cohere)
- Hosted MCP server

## 🛠 Technology Choices (Simplified)

**Core Stack (Phase 1)**:
- `llama-index-core` - Document processing and embeddings
- `faiss-cpu` - Local vector storage
- `typer` + `rich` - CLI framework with nice output
- `pydantic` - Configuration management
- `unstructured` - Document parsing

**Keep It Simple**:
- Start with `IndexFlatL2` in FAISS (simplest, most accurate)
- Use HuggingFace embeddings by default (no API key required)
- Store everything locally (no databases initially)
- Standard pip for packaging (not uv initially)

## 🎮 User Experience Focus

**Primary User**: Individual developer who wants to search their local documents

**Core Workflow** (Preserve existing `indexed` commands):
```bash
# Install  
pip install indexed-cli

# No setup needed (uses local HuggingFace embeddings by default)

# Use (same commands as existing system)
indexed source add folder --path ./my-documents --name "docs"
indexed source update docs
indexed search "how to deploy"
```

**Success = Working in under 2 minutes from install**

## 🔄 Development Workflow

1. **Start Simple**: Get basic indexing and search working
2. **Test Early**: Real documents, real queries
3. **Iterate Fast**: CLI makes testing easy
4. **Extend Gradually**: Add features based on actual usage
5. **Keep Core Clean**: Server will reuse everything

## 🎁 Benefits of This Approach

- **Fast to Market**: CLI MVP can ship quickly
- **Real Usage**: Get feedback from actual users
- **Clean Architecture**: Server extension will be straightforward  
- **No Waste**: Nothing built that isn't needed
- **User-Driven**: Features added based on real needs

## 📈 Extension Path

The monorepo structure makes future extensions natural:

1. **CLI works** → Users want to share with teammates
2. **Add server** → Same core, web interface  
3. **API demand** → REST endpoints using same search logic
4. **AI integration** → MCP layer on top of existing functionality

Each phase builds on the previous without rework.

---

**Next Step**: Start implementing `packages/core` with basic LlamaIndex + FAISS integration, then build simple CLI on top of it.