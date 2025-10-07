# Task PRD: Complete V2 LlamaIndex Integration and CLI Wiring

**Date:** 2025-10-06  
**Status:** 🟢 Active  
**Priority:** High  
**Estimated Effort:** 2-3 hours

---

## 📋 Problem Statement

The V2 architecture with LlamaIndex has been partially implemented:
- ✅ IndexController exists with basic CRUD API
- ✅ StorageService, EmbeddingService, RetrievalService implemented
- ❌ LoaderService is missing (controller imports it but doesn't exist)
- ❌ CLI still uses unnecessary Engine abstraction layer
- ❌ Package exports not properly configured
- ❌ CLI commands not wired to controller

**Core Issue:** The clean controller API exists but isn't usable because:
1. Missing LoaderService breaks the controller
2. Engine abstraction adds unnecessary complexity
3. CLI doesn't know how to import and use the controller

---

## 🎯 Goals

Create a clean, direct integration where:

```
CLI Commands → IndexController API → Services → LlamaIndex/FAISS
                    ↑
                    └── Also usable by: MCP Server, Future SDK
```

**Architecture Principles:**
- Controller exposes abstract API with config logic
- No mixing of patterns (remove Engine abstraction)
- Simple, direct imports: `from index import IndexController`
- Controller API usable by CLI, Server, SDK

---

## 👥 Target Users

**Primary:** Developers using the CLI tool
- Need fast, simple commands: `indexed index files ./docs`
- Want cloud embeddings for instant search (when HF token set)
- Expect workspace-based approach (not collection-based)

**Secondary:** Future SDK consumers
- Import and use IndexController in their own code
- Configure via constructor parameters
- Get typed responses

---

## ✅ Acceptance Criteria

### Must Have
- [ ] LoaderService implemented using LlamaIndex's SimpleDirectoryReader
- [ ] Package exports configured (`index/__init__.py`)
- [ ] Engine abstraction removed from CLI
- [ ] CLI commands wired directly to IndexController
- [ ] End-to-end flow works: index → search
- [ ] HuggingFace API token support for cloud embeddings
- [ ] Proper error messages and user feedback

### Nice to Have
- [ ] Progress indicators during indexing
- [ ] Stats display after operations
- [ ] Config file support for default settings

---

## 🔧 Technical Requirements

### LoaderService
- Use `llama_index.core.SimpleDirectoryReader`
- Support file pattern filtering
- Return LlamaIndex `Document` objects
- Handle errors gracefully (missing files, permissions)

### Package Structure
```python
# index/__init__.py should export:
from index.controller import IndexController
from index.models import SearchResult

__all__ = ["IndexController", "SearchResult"]
```

### CLI Commands
```bash
# New simple commands (no --engine flag)
indexed index files ./docs              # Index documents
indexed index search "query"            # Search indexed docs
indexed index stats                     # Show index stats
indexed index clear                     # Clear index
```

### Controller API
```python
controller = IndexController(
    collection_path=".indexed",              # Where to store index
    api_token=os.getenv("HUGGINGFACE_API_TOKEN"),  # Optional cloud embeddings
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    chunk_size=512,
    chunk_overlap=50
)

# CRUD operations
result = controller.create(source_dir="./docs", file_patterns=["*.md", "*.txt"])
results = controller.search(query="authentication", top_k=10)
stats = controller.get_stats()
controller.delete()
```

---

## 📦 Deliverables

### 1. LoaderService Implementation
**File:** `packages/indexed-core/src/index/services/loader.py`
- Use LlamaIndex SimpleDirectoryReader
- Support file pattern filtering
- Proper error handling

### 2. Package Exports
**File:** `packages/indexed-core/src/index/__init__.py`
- Export IndexController
- Export SearchResult
- Clean public API

### 3. Simplified CLI Commands
**File:** `apps/indexed-cli/src/indexed_cli/commands/index.py`
- Remove engine selection
- Direct controller instantiation
- Clear user feedback

### 4. Engine Cleanup
- Remove `apps/indexed-cli/src/indexed_cli/engines/v2_engine.py`
- Remove `apps/indexed-cli/src/indexed_cli/engines/base.py`
- Keep legacy_engine.py for backward compat (if needed)

### 5. Updated Documentation
**Memory Files:**
- Update `.memory/session_summary.md`
- Archive `.memory/llama_index_integration.md` (task complete)

---

## 🚫 Out of Scope

- Legacy command migration (keep existing legacy commands)
- MCP server updates (separate task)
- Advanced features (RAG, hybrid search, re-ranking)
- Configuration file system (can use defaults)
- Tests (incremental, separate task)

---

## 🧪 Testing Plan

### Manual Testing
```bash
# 1. Index documents
uv run indexed-cli index files ./test-docs

# Expected output:
# 🚀 Initializing IndexController...
# 📥 CREATE: Indexing documents from ./test-docs
# 🔨 Processing 5 documents with IngestionPipeline
# ✅ CREATE complete: 5 documents, 47 nodes

# 2. Search without HF token (local embeddings)
uv run indexed-cli index search "test query"

# Expected: Works but slower first time (~80s model load)

# 3. Search with HF token (cloud embeddings)
export HUGGINGFACE_API_TOKEN=hf_your_token
uv run indexed-cli index search "test query"

# Expected: Fast query (~1s)

# 4. Get stats
uv run indexed-cli index stats

# Expected: Show vector count, model info

# 5. Clear index
uv run indexed-cli index clear

# Expected: Index deleted successfully
```

### Validation Checks
- [ ] Documents successfully indexed
- [ ] Search returns relevant results
- [ ] HF token auto-detected and used
- [ ] Stats show correct counts
- [ ] Clear removes index files
- [ ] Error messages are helpful

---

## 📊 Success Metrics

- **Simplicity:** CLI commands work with simple, direct calls
- **Performance:** Search instant with HF token, acceptable without
- **Usability:** Clear error messages and feedback
- **Maintainability:** No unnecessary abstractions
- **Extensibility:** Easy to import and use controller in other contexts

---

## 🔗 Related Documents

- `.memory/architecture.md` - System architecture overview
- `.memory/tech.md` - Coding standards and tech stack
- `packages/indexed-core/src/index/controller.py` - Controller implementation

---

## 📝 Notes

**Design Decision:** Remove Engine abstraction
- **Why:** Adds complexity without clear benefit
- **Impact:** Simpler, more direct CLI → Controller integration
- **Trade-off:** Loss of easy legacy/v2 switching (acceptable - v2 is the path forward)

**HuggingFace Token:**
- Auto-detect from environment (HUGGINGFACE_API_TOKEN or HF_TOKEN)
- Used for cloud embeddings (instant queries)
- Falls back to local embeddings if not present

**Workspace-based Approach:**
- Index stored in `.indexed/` directory by default
- Can be overridden with `--workspace` or `collection_path` parameter
- Simpler than collection-based management

---

**End of PRD**
