---
type: spec
scope: architecture-cleanup
parent: tech.md
updated: 2026-02-19
status: in-progress
---

# Architecture Cleanup Spec

Pre-v2 cleanup of surviving infrastructure: `indexed-config`, `utils`, CLI app, MCP server, and workspace tooling. Fixes structural issues now so the v2 core/connectors rewrite lands on a clean foundation.

**Assumes:** Core v1 and `indexed-connectors` are legacy — they will be replaced by v2, not cleaned up here.

---

## 1. Split `ConfigService` God Object — ✅ SHIPPED

> **Status:** Completed. `registry.py`, `workspace.py`, `env_writer.py` extracted. `service.py` is now a slim orchestrator. See [feature-config-tech.md](feature-config-tech.md) for implementation details.

**Problem:** `service.py` (657 lines) handles 5 distinct responsibilities: registry, I/O, validation, workspace preference management, and env file writing. Adding v2 config specs will make this worse.

**Current file:** `packages/indexed-config/src/indexed_config/service.py`

### Changes

Split into focused modules:

```
packages/indexed-config/src/indexed_config/
├── service.py          # ConfigService: get/set/delete/bind + singleton (slim orchestrator)
├── registry.py         # NEW: ConfigRegistry: register/unregister spec types
├── workspace.py        # NEW: WorkspaceManager: preference get/set/clear, conflict detection
├── env_writer.py       # NEW: EnvFileWriter: .env read/write, sensitive field routing
├── store.py            # UNCHANGED: TomlStore (already well-scoped)
├── provider.py         # UNCHANGED: Provider (already well-scoped)
├── storage.py          # UNCHANGED: StorageResolver + module functions
├── path_utils.py       # UNCHANGED
└── models.py           # UNCHANGED
```

#### `registry.py` — Extract from service.py

```python
class ConfigRegistry:
    """Manages registration of typed config specs at dot-paths."""

    def __init__(self) -> None:
        self._specs: Dict[str, Type[BaseModel]] = {}

    def register(self, spec: Type[T], *, path: str) -> None: ...
    def unregister(self, path: str) -> bool: ...
    def specs(self) -> Dict[str, Type[BaseModel]]: ...
    def has(self, path: str) -> bool: ...
```

Extracts: `ConfigService.register()`, `self._specs` dict.

#### `workspace.py` — Extract from service.py

```python
class WorkspaceManager:
    """Manages per-workspace storage mode preferences stored in global config."""

    def __init__(self, store: TomlStore, workspace: Path) -> None: ...

    def get_preference(self) -> Optional[StorageMode]: ...
    def set_preference(self, mode: StorageMode, ...) -> None: ...
    def clear_preference(self) -> bool: ...
    def get_config(self) -> Dict[str, str]: ...
    def has_conflict(self) -> bool: ...
    def get_differences(self) -> Dict[str, tuple[Any, Any]]: ...
```

Extracts: `get_workspace_preference()`, `set_workspace_preference()`, `clear_workspace_preference()`, `get_workspace_config()`, `has_config_conflict()`, `get_config_differences()`.

#### `env_writer.py` — Extract from service.py

```python
class EnvFileWriter:
    """Handles .env file read/write and sensitive field detection."""

    def __init__(self, env_path: Path) -> None: ...

    def write(self, key: str, value: str) -> None: ...
    def is_sensitive_field(self, field_name: str) -> bool: ...
    def field_to_env_var(self, field_name: str) -> str: ...
```

Extracts: `_write_to_env_file()`, `_is_sensitive_field()`, `_field_to_env_var()`, `_ENV_VAR_MAPPINGS`.

#### `service.py` — Slim orchestrator

After extraction, `ConfigService` becomes ~200 lines:

```python
class ConfigService:
    """Singleton config service. Orchestrates registry, store, and workspace."""

    _instance: ConfigService | None = None

    def __init__(self, *, workspace=None, mode_override=None):
        self._registry = ConfigRegistry()
        self._store = TomlStore(workspace=workspace, mode_override=mode_override)
        self._resolver = StorageResolver(workspace=workspace, mode_override=mode_override)
        self._workspace_mgr = WorkspaceManager(self._store, workspace or Path.cwd())
        self._env_writer = EnvFileWriter(...)

    # Delegates
    def register(self, spec, *, path): self._registry.register(spec, path=path)
    def bind(self) -> Provider: ...  # uses self._registry.specs()
    def get/set/delete: ...          # raw TOML ops (stays here, thin)

    # Expose sub-managers for direct access when needed
    @property
    def workspace(self) -> WorkspaceManager: ...
    @property
    def registry(self) -> ConfigRegistry: ...
```

### Public API impact

`__init__.py` keeps exporting `ConfigService` with the same interface. The split is internal — callers don't need to change. New classes are also exported for direct use when needed.

### Test impact

Existing tests pass unchanged (same `ConfigService` API). New unit tests added for `ConfigRegistry`, `WorkspaceManager`, `EnvFileWriter` in isolation.

---

## 2. Decompose MCP Server

**Problem:** `mcp/server.py` (527 lines) mixes tool definitions, config loading, result formatting, and a duplicated config access pattern (lifespan state + global fallback). Every tool/resource repeats the same 8-line config resolution block.

**Current file:** `apps/indexed/src/indexed/mcp/server.py`

### Changes

```
apps/indexed/src/indexed/mcp/
├── server.py           # FastMCP instance, lifespan, tool/resource registration (slim)
├── tools.py            # NEW: search(), search_collection() tool implementations
├── resources.py        # NEW: collections_list, collections_status, collection_status
├── formatting.py       # NEW: _format_search_results_for_llm() + future formatters
└── cli.py              # UNCHANGED: MCP CLI entry point
```

### Eliminate dual config loading

Remove the global `_mcp_config` / `_search_config` fallback pattern entirely. Use only the lifespan approach:

```python
# server.py
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[LifespanState]:
    yield {
        "mcp_config": _load_mcp_config(),
        "search_config": _load_search_config(),
    }
```

For tools that need config, extract a helper:

```python
# tools.py
def _get_config_from_ctx(ctx: Optional[Context], key: str, fallback_loader):
    """Single config resolution path — no more duplicated 8-line blocks."""
    if ctx is not None:
        try:
            state = ctx.fastmcp_context.lifespan_context
            if state and key in state:
                return state[key]
        except (AttributeError, TypeError):
            pass
    return fallback_loader()
```

This replaces the 4 identical copy-pasted config resolution blocks.

### `formatting.py`

Move `_format_search_results_for_llm()` here. This is the right home for any future format variations (compact, verbose, streaming).

### `server.py` after cleanup

~80 lines: FastMCP instance creation, lifespan, middleware setup, `main()`. Tools and resources imported and registered.

---

## 3. Establish Thin-Command Pattern in CLI

**Problem:** CLI command files are bloated (create.py: 707 lines, search.py: 477 lines, update.py: 418 lines). They mix argument parsing, business logic orchestration, Rich UI formatting, and service calls. When v2 core arrives, all of this gets rewritten.

**Goal:** Establish the pattern now so v2 commands are clean from the start.

### Architecture rule

```
Command file (CLI layer)        → Argument parsing + UI formatting ONLY
  ↓ calls
Service function (service layer) → Business logic orchestration
  ↓ calls
Engine (core layer)              → Implementation details
```

Commands should be **thin wrappers**: parse args, call a service, format output. No business logic.

### What to extract now

Don't rewrite the v1 commands — they're going away. Instead:

1. Create a `apps/indexed/src/indexed/knowledge/services/` directory with the pattern established
2. Move shared UI helpers (progress display, result formatting, credential prompting) into `apps/indexed/src/indexed/utils/` if not already there
3. Document the pattern in the CLI CLAUDE.md so v2 commands follow it

### Pattern for v2 commands

```python
# knowledge/commands/search.py — THIN
def search(
    query: str = typer.Argument(...),
    collection: str | None = typer.Option(None),
    max_results: int = typer.Option(10),
    output_format: str = typer.Option("card"),
) -> None:
    """Search indexed collections."""
    from ..services.search import execute_search
    from ...utils.formatters import format_search_results

    results = execute_search(query, collection=collection, max_results=max_results)
    format_search_results(results, format=output_format)
```

```python
# knowledge/services/search.py — BUSINESS LOGIC
def execute_search(query: str, *, collection=None, max_results=10) -> SearchResults:
    """Orchestrate search across collections. No UI concerns."""
    config = ConfigService.instance()
    # ... call core engine, handle errors, return typed results
```

### File size guideline

Command files should be <150 lines. If a command file exceeds 200 lines, business logic needs extraction.

---

## 4. Fix Early Flag Parsing Hack

**Problem:** `app.py` manually strips `--local`/`--global` from `sys.argv` before Typer processes them. This is fragile, breaks `--help` output for these flags, and uses module-level globals.

**Current code:** `app.py:47-61` (`_parse_early_storage_flags`) + `app.py:64` (globals) + `app.py:108` (consumption in callback)

### Solution: Use Typer's built-in callback mechanism

```python
@app.callback(invoke_without_command=True)
def _init_app(
    ctx: typer.Context,
    local: bool = typer.Option(False, "--local", help="Use local .indexed/ storage"),
    global_: bool = typer.Option(False, "--global", help="Use global ~/.indexed/ storage"),
    verbose: bool = typer.Option(False, "--verbose", ...),
    log_level: Optional[str] = typer.Option(None, "--log-level", ...),
    json_logs: bool = typer.Option(False, "--json-logs", ...),
) -> None:
    """Initialize app with storage mode and logging."""
    if local and global_:
        console.print("[red]Error:[/red] Cannot use both --local and --global.")
        raise typer.Exit(1)

    mode_override = "local" if local else ("global" if global_ else None)

    # Store on context for commands to access
    ctx.ensure_object(dict)
    ctx.obj["mode_override"] = mode_override

    # ... logging setup ...
```

**Removes:** `_parse_early_storage_flags()`, `_EARLY_USE_LOCAL`, `_EARLY_USE_GLOBAL` globals, `sys.argv` mutation.

**If Typer conflicts exist** (the likely reason for the hack), investigate and document the specific conflict. If it's a Typer limitation with subcommand flag propagation, use `ctx.obj` as the propagation mechanism instead of sys.argv mutation.

---

## 5. Add Exception Hierarchy — ✅ SHIPPED

> **Status:** Completed. `indexed_config/errors.py` and `indexed/errors.py` exist and are in use. Exception hierarchy rooted in `IndexedError` with `ConfigurationError`, `StorageError`, `CLIError`, `MCPError` subtypes.

**Problem:** Error handling is inconsistent — some places raise `ValueError`, some catch `Exception` and pass silently, some return error dicts. No way to distinguish config errors from storage errors from engine errors.

### New module: `packages/indexed-config/src/indexed_config/errors.py`

```python
class IndexedError(Exception):
    """Base exception for all indexed errors."""

class ConfigurationError(IndexedError):
    """Invalid or missing configuration."""

class ConfigValidationError(ConfigurationError):
    """Pydantic validation failed for a config spec."""
    def __init__(self, path: str, detail: str):
        self.path = path
        super().__init__(f"Invalid config at '{path}': {detail}")

class StorageError(IndexedError):
    """Storage path resolution or I/O failure."""

class StorageConflictError(StorageError):
    """Both local and global configs exist with conflicting values."""
```

### New module: `apps/indexed/src/indexed/errors.py`

```python
from indexed_config.errors import IndexedError  # re-export base

class CLIError(IndexedError):
    """CLI-specific errors (invalid args, missing input)."""

class MCPError(IndexedError):
    """MCP server errors."""
```

### Migration

- Replace `ValueError(f"Invalid config for '{path}': {exc}")` in `service.py:206` with `ConfigValidationError`
- Replace bare `except Exception: pass` blocks with specific catches + logging
- MCP tools: catch `IndexedError` subtypes and return structured error dicts; let unexpected errors propagate

### Rule for v2

All v2 core/connector exceptions must inherit from `IndexedError`. This gives the CLI and MCP layers a single catch point.

---

## 6. Add Config Schema Versioning

**Problem:** No migration path when config structure changes. v2 core will change config namespaces (e.g., `core.v1.search` → `core.v2.search`). Without versioning, old configs silently produce wrong behavior.

### Add to config TOML files

```toml
[_meta]
schema_version = "1"

[core.v1.search]
max_docs = 10
```

### Implementation

In `TomlStore.read()`, after loading:

```python
def read(self) -> Dict[str, Any]:
    data = ...  # existing merge logic
    schema_version = data.pop("_meta", {}).get("schema_version", "1")
    data["_schema_version"] = schema_version
    return data
```

In `ConfigService.bind()`, check version and warn:

```python
def bind(self) -> Provider:
    raw = self.load_raw()
    version = raw.pop("_schema_version", "1")
    if version != CURRENT_SCHEMA_VERSION:
        warnings.warn(
            f"Config schema version {version} differs from expected {CURRENT_SCHEMA_VERSION}. "
            "Run 'indexed config migrate' to update.",
            stacklevel=2,
        )
    # ... rest of bind
```

### Migration command

Add `indexed config migrate` that reads config, applies transforms for version transitions, and writes back with updated schema version.

---

## 7. Clean Up `indexed-config` Public API

**Problem:** `__init__.py` exports 17 symbols including internal utilities (`get_resolver`, `reset_resolver`, `get_data_root`). This creates a surface area that's hard to maintain and leaks implementation details.

### Tiered exports

```python
# __init__.py — Public API (what external packages should use)
from .service import ConfigService
from .provider import Provider
from .storage import StorageMode, StorageResolver
from .errors import (
    ConfigurationError,
    ConfigValidationError,
    StorageError,
    StorageConflictError,
)

# Storage convenience functions (commonly used by CLI)
from .storage import (
    get_global_root,
    get_local_root,
    get_collections_path,
    get_caches_path,
    has_local_config,
    has_global_config,
    ensure_storage_dirs,
)

__all__ = [
    # Core API
    "ConfigService",
    "Provider",
    "StorageMode",
    "StorageResolver",
    # Errors
    "ConfigurationError",
    "ConfigValidationError",
    "StorageError",
    "StorageConflictError",
    # Storage helpers
    "get_global_root",
    "get_local_root",
    "get_collections_path",
    "get_caches_path",
    "has_local_config",
    "has_global_config",
    "ensure_storage_dirs",
]
```

**Removed from public API:** `TomlStore`, `get_resolver`, `reset_resolver`, `get_config_path`, `get_env_path`, `get_data_root`, `has_local_storage`, `has_global_storage`. These are internal details — consumers should go through `ConfigService` or `StorageResolver`.

**Note:** `TomlStore` is still importable via `from indexed_config.store import TomlStore` for tests that need it. It's just not in `__all__`.

---

## 8. Remove Import-Time Side Effects (v2 Prep)

**Problem:** `core/v1/__init__.py` calls `ConfigService.instance()` and registers config specs at import time, wrapped in bare `except Exception: pass`. This is a v1 pattern that must not be repeated in v2.

### Architectural rule for v2

Config registration must be **explicit**, not triggered by imports:

```python
# BAD — v1 pattern (import-time side effect)
# core/v1/__init__.py
try:
    _svc = ConfigService.instance()
    _svc.register(IndexingConfig, path="core.v1.indexing")
except Exception:
    pass

# GOOD — v2 pattern (explicit registration)
# core/v2/config.py
def register_config(config_service: ConfigService) -> None:
    """Register all v2 config specs. Called by app initialization."""
    config_service.register(IndexingConfig, path="core.v2.indexing")
    config_service.register(SearchConfig, path="core.v2.search")
    config_service.register(EmbeddingConfig, path="core.v2.embedding")
```

Called from app initialization:

```python
# apps/indexed/src/indexed/app.py (in callback or startup)
from core.v2.config import register_config
config = ConfigService.instance()
register_config(config)
```

### Document this in CLAUDE.md

Add to the "DON'T" list:
- NEVER register config specs at module import time
- NEVER use bare `except Exception: pass` to silence config failures

---

## Execution Order

| Phase | Task | Depends On | Risk |
|-------|------|------------|------|
| **1** | Add exception hierarchy (#5) | — | Low: additive, no breaking changes |
| **2** | Split ConfigService (#1) | — | Medium: internal refactor, tests must pass |
| **3** | Clean up public API (#7) | #1, #5 | Low: just `__init__.py` changes |
| **4** | Fix early flag parsing (#4) | — | Medium: need to verify Typer compatibility |
| **5** | Add schema versioning (#6) | #1 | Low: additive |
| **6** | Decompose MCP server (#2) | — | Medium: test MCP tools still work |
| **7** | Establish thin-command pattern (#3) | — | Low: pattern + docs, minimal code change |
| **8** | Document v2 rules (#8) | All above | Low: docs only |

Phases 1–3 can run in parallel. Phase 4 is independent. Phase 6 is independent. Phase 7 is mostly documentation. Phase 8 is last.

---

## Updated Tech Spec Additions

The following architectural rules should be added to `tech.md` to prevent these issues in v2:

### Dependency Direction Rule

```
CLI/MCP (apps/) → Services → Core Engine → Protocols
                                         ↑
Config, Utils (packages/) ───────────────┘
```

- Dependencies flow **downward only**
- No package may import from a higher layer
- Protocols/interfaces live in the lowest layer that defines them
- Concrete implementations never imported by the layer above — use dependency injection

### File Size Limits

| File type | Max lines | Action when exceeded |
|-----------|-----------|---------------------|
| Command file | 150 | Extract business logic to service |
| Service file | 300 | Split by responsibility |
| Module file | 400 | Split into submodules |

### Config Registration Rule

Config specs are registered **explicitly** during app initialization, never at import time. Each package exports a `register_config(service: ConfigService)` function.

### Error Handling Rule

- All package exceptions inherit from `IndexedError`
- Never use bare `except Exception: pass`
- CLI layer catches `IndexedError` subtypes and formats for user
- MCP layer catches `IndexedError` subtypes and returns structured error dicts
- Unexpected exceptions propagate (crash with traceback in dev, structured error in prod)

### No Dual Code Paths

If a value can be accessed via dependency injection (e.g., lifespan state) AND via a global/singleton, pick one. Never maintain both with fallback logic between them.
