# Refactoring: Logging & Status System

## Summary

Cleaned up and standardized the logging and interactive status display system to follow KISS principles and improve code reusability.

## Changes Made

### 1. **Removed Dead Code** (`logger.py`)
- Deleted unused `LoguruRichHandler` class (lines 41-49)
- This class was defined but never instantiated or used

### 2. **Extracted Constants** (`logger.py`)
- Created `_LEVEL_COLORS` dict for log level color mapping
- Added `_get_level_color()` helper function
- Benefits:
  - Single source of truth for colors
  - Easy to maintain and update
  - Matches design system (cyan for INFO)

### 3. **Eliminated Code Duplication** (`search.py`)
- Removed duplicate search service calls (lines 64-82)
- Used conditional context manager approach
- Added `_NoOpContext` helper class for verbose mode
- Benefits:
  - DRY principle
  - Easier to maintain
  - Clearer intent

### 4. **Improved Naming** (`status.py`)
- Renamed `SearchStatus` → `OperationStatus`
- Added backwards compatibility alias
- Benefits:
  - More reusable (works for any operation)
  - Better semantic meaning
  - No breaking changes

### 5. **Better Documentation**
- Added clearer docstrings explaining automatic log capture
- Documented the context manager pattern
- Added usage examples

## Before & After

### Before: Duplicate Code
```python
if not is_verbose:
    with SearchStatus(console, initial_message=\"Starting search...\"):
        results = search_service(...)
else:
    results = search_service(...)
```

### After: Single Call
```python
context = OperationStatus(console, \"Starting search...\") if not is_verbose_mode() else _NoOpContext()
with context:
    results = search_service(...)
```

## Reusable Components

### OperationStatus
Can now be used for any long-running operation:
- Search operations
- Indexing operations
- Update operations
- Any CLI command that takes >1 second

### Usage Pattern
```python
from cli.components import OperationStatus
from cli.utils.console import console
from utils.logger import is_verbose_mode

# Automatically shows spinner in default mode, logs in verbose mode
context = OperationStatus(console, \"Processing...\") if not is_verbose_mode() else _NoOpContext()
with context:
    # Your long-running operation
    do_work()
```

## Design Principles Applied

1. **KISS (Keep It Simple, Stupid)**
   - Removed unnecessary classes
   - Simplified duplicate code
   - Clear, straightforward logic

2. **DRY (Don't Repeat Yourself)**
   - Extracted color constants
   - Eliminated duplicate search calls
   - Reusable helper functions

3. **Single Responsibility**
   - `OperationStatus`: Just manages spinner + log capture
   - `is_verbose_mode()`: Just checks mode
   - Each function does one thing well

4. **Open/Closed Principle**
   - `OperationStatus` open for extension (any operation)
   - Closed for modification (backwards compatible)

## Files Modified

- `packages/utils/src/utils/logger.py` - Removed dead code, extracted constants
- `apps/indexed-cli/src/cli/components/status.py` - Renamed, improved docs
- `apps/indexed-cli/src/cli/commands/search.py` - Removed duplication
- `apps/indexed-cli/src/cli/components/__init__.py` - Updated exports

## Testing

✅ Default mode: Clean output, spinner during search
✅ Verbose mode: Rich-formatted logs, no spinner
✅ Debug mode: Extended logs with DEBUG level
✅ Backwards compatibility: SearchStatus alias works
