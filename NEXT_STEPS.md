# Next Steps: Versioning Strategy Implementation

## ✅ What We Just Decided

**Versioning Approach:** **Option B - Layers Within Versions** (`v1/engine`, `v2/engine`)

### Why This Approach?

1. ✅ Complete isolation between versions (v1, v2 are independent)
2. ✅ Clean imports: `from indexed.v1 import create_collection`
3. ✅ You already have `indexed-utils` for shared code
4. ✅ Config/services differ enough that sharing creates problems
5. ✅ Industry standard (Django, FastAPI pattern)

### Structure

```
packages/
├── utils/              # Shared utilities (version-agnostic)
│   └── src/utils/     # Logger, batch processing, etc.
│
└── core/
    └── src/indexed/
        ├── v1/        # V1 Complete API
        │   ├── config.py
        │   ├── models.py
        │   ├── services/
        │   └── _engine/    # Private implementation
        └── v2/        # V2 Future API
```

## 📝 What's Been Updated

### Memory Files
- ✅ `.memory/brief.md` - Updated with current status and versioning decision
- ✅ `.memory/architecture.md` - Complete new architecture documented
- ✅ `.memory/task_prd.md` - Comprehensive PRD with all options analyzed
- ✅ `.memory/task_plan.md` - Detailed 5-phase implementation plan
- ✅ `VERSIONING_STRATEGY.md` - Executive summary in project root

## 🔧 What Needs Fixing (Phase 0)

### 1. Utils Package Structure

**Current Problem:**
```
packages/utils/src/
├── logger.py          # ❌ Files directly in src/
├── batch.py
└── progress_bar.py
```

**Should Be:**
```
packages/utils/src/utils/
├── __init__.py        # ← Need to create
├── logger.py          # ← Move here
├── batch.py           # ← Move here
└── progress_bar.py    # ← Move here
```

**Commands:**
```bash
cd packages/utils/src
mkdir -p utils
mv logger.py batch.py progress_bar.py utils/
# Create __init__.py (see below)
```

**utils/__init__.py content:**
```python
"""Indexed utilities - shared code for all versions."""

from .logger import setup_root_logger, get_logger
from .batch import batch_process
from .progress_bar import create_progress_bar

__all__ = [
    "setup_root_logger",
    "get_logger",
    "batch_process",
    "create_progress_bar",
]
```

### 2. Root pyproject.toml

**File:** `pyproject.toml` (root)

**Change:**
```toml
[tool.uv.workspace]
members = [
    "packages/utils",      # ← ADD THIS
    "packages/core",       # Update path
    "apps/cli"            # Update path
]
```

### 3. Utils pyproject.toml

**File:** `packages/utils/pyproject.toml`

**Changes:**
```toml
[project]
description = "Shared utilities for indexed document search system"  # Line 4: FIX
dependencies = [
    "loguru>=0.7.2",  # Line 11: UPDATE (was 0.0.2)
]

[tool.hatch.build.targets.wheel]
packages = ["src/utils"]  # Line 19: FIX (was ["src/"])
```

### 4. Core pyproject.toml

**File:** `packages/core/pyproject.toml`

**Add after line 9:**
```toml
dependencies = [
    "indexed-utils",  # ← ADD THIS FIRST
    "bs4>=0.0.2",
    # ... rest of dependencies
]

# At end of file, ADD:
[tool.uv.sources]
indexed-utils = { workspace = true }
```

**Also fix line 32:**
```toml
packages = ["src/indexed"]  # Was ["src/"]
```

### 5. CLI pyproject.toml

**File:** `apps/cli/pyproject.toml`

**Add after line 11:**
```toml
dependencies = [
    "indexed-core",
    "indexed-utils",  # ← ADD THIS
    "typer>=0.12.3",
    # ... rest
]
```

**Add to [tool.uv.sources]:**
```toml
[tool.uv.sources]
indexed-core = { workspace = true }
indexed-utils = { workspace = true }  # ← ADD THIS
```

## 🚀 Quick Start Commands

```bash
# 1. Fix utils package structure
cd packages/utils/src
mkdir -p utils
mv logger.py batch.py progress_bar.py utils/
cat > utils/__init__.py << 'EOF'
"""Indexed utilities - shared code for all versions."""

from .logger import setup_root_logger, get_logger
from .batch import batch_process
from .progress_bar import create_progress_bar

__all__ = [
    "setup_root_logger",
    "get_logger",
    "batch_process",
    "create_progress_bar",
]
EOF
cd ../../..

# 2. Update all pyproject.toml files (manually or with editor)
# See detailed changes above

# 3. Resync workspace
uv sync --all-groups

# 4. Test imports
uv run python -c "from utils import setup_root_logger; print('✅ Utils OK')"
uv run python -c "import indexed; print('✅ Core OK')"
```

## 📋 Phase 0 Checklist

- [ ] Create `packages/utils/src/utils/` directory
- [ ] Move utility files into `utils/` subdirectory
- [ ] Create `utils/__init__.py` with exports
- [ ] Update root `pyproject.toml` workspace members
- [ ] Update `packages/utils/pyproject.toml` (description, loguru, packages)
- [ ] Update `packages/core/pyproject.toml` (add indexed-utils dep)
- [ ] Update `apps/cli/pyproject.toml` (add indexed-utils dep)
- [ ] Run `uv sync --all-groups`
- [ ] Test: `uv run python -c "from utils import setup_root_logger"`
- [ ] Test: `uv run indexed-cli --help`

## 📚 Reference Documents

- **Quick Overview:** `VERSIONING_STRATEGY.md`
- **Complete Architecture:** `.memory/architecture.md`
- **Detailed PRD:** `.memory/task_prd.md` (all 3 options analyzed)
- **Implementation Plan:** `.memory/task_plan.md` (5 phases with timeline)
- **Project Status:** `.memory/brief.md`

## ⏭️ After Phase 0

Once all pyproject.toml fixes are done and workspace is working:

1. **Phase 1:** Create `indexed/v1/` structure
2. **Phase 2:** Update CLI imports to `indexed.v1`
3. **Phase 3:** Update test suite
4. **Phase 4:** Remove old structure
5. **Phase 5:** Documentation

**Estimated Total Time:** 12-19 hours (1-2 hours for Phase 0)

---

**Status:** Ready to begin Phase 0 implementation
**Next Action:** Fix utils package structure and update pyproject.toml files
