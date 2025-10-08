# Core Library Versioning Strategy

## Executive Summary

The indexed-python core library needs a clear versioning strategy. Currently, only the `engine/` is versioned (`v1/`), while `config/` and `service/` layers remain unversioned. This document proposes a comprehensive versioning approach for the entire API surface.

## Current State

### What We Have
- ✅ Monorepo with apps and packages separated
- ✅ V1 engine working (Jira, Confluence, Files)
- ✅ Config management with Pydantic
- ✅ Service abstractions (embedding, storage)

### What's Problematic
- ❌ Only `engine/v1/` is versioned
- ❌ Config and service layers not versioned
- ❌ Import paths inconsistent (`main` vs `index` namespaces)
- ❌ No clear public/private API boundary
- ❌ Package naming mismatch (pyproject says `src/index`, but no `index/` dir)

## Recommended Approach: Hybrid Versioning

### Target Structure

```
packages/
├── indexed-utils/           # Shared utilities (NO versioning)
│   ├── pyproject.toml      # name = "indexed-utils"
│   └── src/utils/          # Import: from utils import ...
│       ├── __init__.py
│       ├── logger.py
│       ├── batch.py
│       └── progress_bar.py
│
├── indexed-connectors/      # Data source connectors (future)
│   ├── pyproject.toml      # name = "indexed-connectors"
│   └── src/connectors/     # Import: from connectors.jira import ...
│       ├── jira/           # Jira API + readers
│       ├── confluence/     # Confluence API + readers
│       └── files/          # File scanner + readers
│
└── core/
    ├── pyproject.toml       # name = "indexed-core"
    └── src/indexed/         # Import: from indexed.v1 import ...
        ├── __init__.py      # Default exports (v1)
        ├── py.typed
        │
        ├── v1/              # V1 Complete API
        │   ├── __init__.py # Public exports
        │   ├── api.py      # High-level functions
        │   ├── models.py   # Data models
        │   ├── config.py   # Configuration
        │   ├── services/   # Services (public)
        │   └── _engine/    # Engine (private)
        │       └── sources/  # Uses connectors package
        │
        └── v2/              # V2 API (future)
            └── ...
```

## Key Principles

1. **Complete Version Isolation**: Each version is self-contained
2. **Clear Public/Private**: Use `_` prefix for internal code
3. **Clean Imports**: `from indexed.v1 import ...`
4. **Explicit Exports**: Only public API in `__all__`
5. **Python Packaging Best Practice**: src/ layout with clear import namespaces

## V1 Public API Design

### High-Level Operations (Simple Use)

```python
from indexed.v1 import create_collection, search_collection
from indexed.v1.models import SourceConfig

source = SourceConfig(type="files", base_path="./docs")
create_collection("my-docs", source)
results = search_collection("query", collection="my-docs")
```

### Service Classes (Advanced Use)

```python
from indexed.v1.services import CollectionService, SearchService
from indexed.v1.config import load_config

config = load_config()
collection_svc = CollectionService(config)
search_svc = SearchService(config)
```

## Migration Strategy

### Phase 1: Create V1 Structure
- Create `indexed/v1/` with complete API
- Move utilities to `_internal/`
- Wrap existing engine in `v1/_engine/`
- Keep old imports working

### Phase 2: Update CLI
- Change imports to `indexed.v1`
- Remove `main` namespace references
- Update all commands

### Phase 3: Update Tests
- Use `indexed.v1` imports
- Maintain coverage
- Fix any issues

### Phase 4: Cleanup
- Remove old structure
- Update `pyproject.toml`
- Remove compatibility layer

### Phase 5: Documentation
- API docs
- Migration guide
- Examples

## Benefits

1. **Stability**: V1 API won't break when adding V2
2. **Clarity**: Clear what's public vs private
3. **Extensibility**: Easy to add new versions
4. **Usability**: Simple imports for CLI and future server
5. **Maintainability**: Clean boundaries reduce coupling

## Timeline

- Phase 1: 4-6 hours
- Phase 2: 2-3 hours
- Phase 3: 2-3 hours
- Phase 4: 1-2 hours
- Phase 5: 2-3 hours

**Total: 11-17 hours**

## Next Steps

1. Review and discuss this proposal
2. Get approval on approach
3. Create detailed subtasks
4. Begin implementation

---

For complete details, see `.memory/task_prd.md`
