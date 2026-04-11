# Wire v2 Core into CLI + MCP (Phase 2)

The v2 core engine for indexed is complete and merged at `packages/indexed-core/src/core/v2/`. It's a LlamaIndex-powered replacement for v1's custom FAISS engine, with HuggingFace ONNX embeddings and pluggable vector stores. **104 tests passing.** It's NOT yet accessible via CLI or MCP — those still point at v1. Your job is to wire v2 into the app layer.

## What exists (DO NOT modify)

**Package:** `packages/indexed-core/src/core/v2/`

- `core.v2.Index`, `core.v2.IndexConfig` — user-facing facade with same API as v1
- `core.v2.config.register_config(config_service)` — explicit config registration function (MUST be called at app startup, never at import time)
- `core.v2.services` — service layer with same API contract as v1:
  - `create(name, connector, *, embed_model_name, store_type, collections_dir, progress)`
  - `update(name, connector, ...)`
  - `clear(names, collections_dir)`
  - `search(query, *, configs, max_docs, max_chunks, include_matched_chunks, ...)`
  - `SearchService` (stateful)
  - `status(names, collections_dir)`, `inspect(name, collections_dir)`
- `core.v2.services.models` — re-exports v1 models (`SourceConfig`, `CollectionStatus`, `CollectionInfo`, `SearchResult`, `PhasedProgressCallback`)
- `core.v2.errors.CoreV2Error` hierarchy — all inherit from `IndexedError`

**v2 storage format is NOT backward compatible with v1.** v1 collections must be re-indexed to work with v2.

## Scope: `apps/indexed/` only

**Note:** The app package was recently renamed from `indexed` to `indexed-sh`. Check `apps/indexed/pyproject.toml` to confirm current naming.

### Required changes

**1. Engine selection mechanism**

Add an `engine` setting with two sources:

- `[general] engine = "v1" | "v2"` in `config.toml` (default: `"v1"`)
- `--engine v1|v2` CLI flag (overrides config)

Register via `indexed_config.ConfigService`. Default to v1 for backward compatibility. Document that v2 requires re-indexing.

**2. App startup: explicit v2 config registration**

In `apps/indexed/src/indexed/app.py` (or wherever the Typer root callback initializes services), call:

```python
from core.v2.config import register_config as register_v2_config
register_v2_config(ConfigService.instance())
```

This MUST NOT happen at module import time — only in the app callback. v1 registers differently; don't copy v1's pattern.

**3. Service dispatch layer**

Create `apps/indexed/src/indexed/services/engine_router.py` — a thin router that imports the correct service module based on the active engine:

```python
def get_collection_service(engine: str):
    if engine == "v2":
        from core.v2.services import collection_service
        return collection_service
    from core.v1.engine.services import collection_service  # or equivalent v1 path
    return collection_service
```

Do the same for `search_service` and `inspect_service`. Commands call the router, not the services directly. Keep it <100 lines.

**4. Wire CLI commands**

Update each command in `apps/indexed/src/indexed/knowledge/commands/`:

- `create.py` — use router to pick create service
- `search.py` — use router to pick search service
- `update.py` — use router
- `inspect.py` — use router
- `remove.py` — use router

Commands stay thin: parse args → call service via router → format output. Max 150 lines per command file. **Do NOT rewrite v1 command logic** — just add the branching.

**5. Wire MCP server**

Update `apps/indexed/src/indexed/mcp/server.py` (and `tools.py`/`resources.py` if decomposed) to use the router for `search`, `list_collections`, and `collection_status` tools. Pass engine selection via lifespan state, not globals.

**6. Tests**

- Unit tests for `engine_router.py` — verify correct service is returned for each engine
- Update existing CLI command tests to cover both v1 and v2 code paths (parametrize the engine)
- MCP tool tests: same approach — parametrize the engine
- **Coverage target: >85% for all new/modified files**

## Architectural rules (HARD REQUIREMENTS)

From `.spec/cleanup.md` and `CLAUDE.md`:

1. **Thin commands**: parse args + format output only. Business logic lives in services. Max 150 lines per command file.
2. **No import-time side effects**: no `ConfigService.instance()` at module level, no `register_config` at import, no singletons in module scope.
3. **Lazy imports**: heavy dependencies (LlamaIndex, sentence-transformers) imported inside function bodies. CLI startup must stay <1s.
4. **Dependencies flow downward**: CLI/MCP → services → core engine. Never upward.
5. **All exceptions inherit from IndexedError**: catch `IndexedError` subtypes at the CLI/MCP boundary, format for user, exit with code.
6. **No dual code paths**: if something is accessed via DI (lifespan state), do not also fall back to globals.

## What you MUST NOT do

- Do NOT modify anything under `packages/indexed-core/src/core/v2/` — the core is frozen for this phase
- Do NOT change v1 behavior — default must remain v1
- Do NOT delete v1 code — coexistence is the point
- Do NOT add new dependencies without justification — LlamaIndex packages are already in `indexed-core`
- Do NOT create files unless necessary — prefer editing

## Files to read FIRST (in order)

1. `.spec/cleanup.md` — thin-command pattern, architectural rules, error hierarchy
2. `packages/indexed-core/src/core/v2/__init__.py`, `index.py`, `config.py` — v2 public API
3. `packages/indexed-core/src/core/v2/services/__init__.py` — v2 service exports
4. `apps/indexed/src/indexed/app.py` — current app initialization
5. `apps/indexed/src/indexed/knowledge/commands/create.py` — current thin-command pattern example
6. `apps/indexed/src/indexed/mcp/server.py` — current MCP server structure
7. `packages/indexed-config/src/indexed_config/service.py` — how ConfigService works

## Workflow

Follow **ASK → PLAN → CONFIRM → EXECUTE**:

1. **ASK**: Read the files above. Ask clarifying questions only if genuinely blocked (e.g., unclear where engine flag should live in config schema).
2. **PLAN**: Present an incremental implementation plan — break it into commit-sized checkpoints (router → config + startup → CLI commands → MCP → tests). Each increment must leave the tree green.
3. **CONFIRM**: Get explicit user approval before writing code.
4. **EXECUTE**: Implement incrementally, committing after each checkpoint. Run `uv run pytest -q`, `uv run ruff check . --fix`, `uv run ruff format`, `uv run mypy src/` after each commit.

## Done criteria

- `uv run indexed --engine v2 index create docs --source files --source-path ./docs` creates a v2 collection
- `uv run indexed --engine v2 index search "query"` searches v2 collections
- `uv run indexed index create ...` (no flag) still uses v1 — no regression
- MCP server with `[general] engine = "v2"` in config serves v2 collections to Claude Desktop
- Full test suite passes: `uv run pytest -q`
- v2 coverage >85% on modified files
- Lint + mypy clean

**Branch:** create a new feature branch off `claude/indexed-v2-core-sAbB6` (which has v2 core + latest merges). Do NOT commit directly to it.
