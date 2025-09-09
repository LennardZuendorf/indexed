# Task Plan: FastMCP Integration – Search & Inspect

## Objective
Implement the PRD *Expose Search & Inspect via FastMCP*.  Concretely, extend the existing `src/mcp_server/server.py` so that it offers:

1. **Tools**
   - `search(query: str)` – multi-collection semantic search.
   - `search_collection(collection: str, query: str)` – same but limited to one collection.

2. **Resources**
   - `resource://collections` – list of collection names.
   - `resource://collections/status` – detailed status for all collections.
   - `resource://collections/{name}` – detailed status for a single collection.

All functions delegate to existing service singletons in `main.services.*`.

## Architectural Decisions
1. **Keep Single MCP Instance** – continue using instantiated `mcp` object in `server.py`.
2. **Service Imports** – import `search_service.search` and `inspect_service.status` directly to avoid CLI coupling.
3. **Minimal Args** – Only required positional args per user request; future optional parameters can be added later or read from env.
4. **Sync vs Async** – Service calls are synchronous; we will wrap heavy search in `make_async_background` if FastMCP blocking becomes an issue, but initial version stays sync.
5. **Type Hints** – Provide full type annotations so FastMCP auto-generates schemas.
6. **Return Types** – Accept FastMCP default serialisation (dictionaries/ lists). Convert `CollectionStatus` pydantic models to `dict` via `model.dict()`.
7. **Error Handling** – Catch service exceptions and return structured error dict `{"error": str(e)}`.

## Deliverables
- **Modified** `src/mcp_server/server.py` with:
  ```python
  from main.services.search_service import search as svc_search, SourceConfig
  from main.services.inspect_service import status as svc_status
  ```
  Plus new `@mcp.tool` and `@mcp.resource` decorated functions.
- **Unit tests** under `tests/mcp/` verifying:
  - Tool schemas exist (`client.list_tools`).
  - Calling tools returns expected structure using monkeypatched services.
  - Resources content matches inspect service output.
- **README** snippet update (optional, future).

## Implementation Steps
1. **Refactor server placeholders**
   - Remove or keep demo tools (`say_hello`, etc.) but ensure no naming collisions.
2. **Add Search Tools**
   - `search(query: str) -> dict`
   - `search_collection(collection: str, query: str) -> dict`
   - Inside second tool build `SourceConfig` list with default indexer.
3. **Add Collection Resources**
   - Static list and status variants using `@mcp.resource`.
   - Convert `CollectionStatus` objects to `dict` (`jsonable_encoder` if needed).
4. **Update __all__ or keep none (not required)**
5. **Write Tests** (basic smoke—can be expanded later).

## Estimated Effort
- Code changes: **1h**
- Tests: **1h**

## Validation Strategy (cli/mcp overrides)

All runtime overrides supplied via CLI flags or MCP env must pass through **pydantic validation** before use.

Pattern:
```python
cfg = ConfigService.get()
# build patch with CLI flags (only non-None)
patch = {"search": {"max_docs": cli_max_docs}}  # etc.
validated = cfg.model_copy(update=patch, deep=True)  # pydantic merges & validates
```
Any `ValidationError` will be caught by CLI command decorator / MCP tool wrapper and surfaced to the user as a clear error message. This guarantees type safety after merging external arguments with stored configuration.

## CLI Reverse Flow – User Editing Config

Additions to CLI group `config`:
| Command | Purpose |
|---|---|
| `config list [--profile]` | Show all stored (unmerged) settings for the base or selected profile. |
| `config add <key> <value> [--profile]` | Alias for `update` when key is new. Validates before save. |
| `config delete <key> [--profile]` | Remove key (same as `unset`). |

Onboarding command:
```
indexed init
```
• Interactive prompt wizard (Typer) that walks user through minimal required settings per source (files path, Jira URL + email, etc.).  
• Collects answers, builds a valid `IndexedSettings`, and calls `ConfigService.set()` to persist.  
• Option `--non-interactive --file my-settings.toml` to import prepared config.

## Configuration Files & Secrets Policy (updated)

- Primary settings file: `indexed.toml` at project root (authoritative, VCS-tracked or ignored per team policy).
- Environment variables: loaded from process environment and optional `.env` file in project root.
- Precedence: CLI/MCP overrides → env (.env/process) → `indexed.toml` → defaults.
- Secrets non-persistence policy:
  - Sensitive values (API tokens, passwords) are NEVER written to `indexed.toml` by any CLI command.
  - The config may store only the name of the env var (e.g., `sources.jira_cloud.api_token_env = "JIRA_API_TOKEN"`).
  - CLI flags that pass secret values are treated as runtime overrides only and are not persisted; guidance is shown to export them to `.env` or shell env.
