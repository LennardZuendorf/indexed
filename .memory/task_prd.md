# Task PRD: Central Configuration Service & Config CLI

## Goal
Establish a **single, authoritative configuration system** for the Indexed project that:
1. Loads settings from `config.toml`, environment variables, and sensible defaults.
2. Exposes a programmatic `ConfigService` that other services/commands fetch configuration from and merge with runtime overrides (e.g. CLI flags).
3. Provides a new `indexed config` CLI group to view and modify the persisted configuration.

## Motivation / Value
- Removes duplicated option handling scattered across CLI commands and MCP server.
- Enables non-interactive use through environment variables (ideal for CI/remote agents).
- Gives users a canonical `config.toml` they can commit/share for reproducible setups.
- Simplifies future feature flags and advanced options (e.g. embedding model switch).

## Functional Scope
### 1. Configuration Schema
- Implemented via **pydantic-settings** `BaseSettings` subclass (`IndexedSettings`).
- **Top-level sections** (initial set):
  - `search.max_docs: int = 10`
  - `search.max_chunks: int = 30 | null`
  - `search.include_full_text: bool = false`
  - `paths.collections_dir: str = "./data/collections"`
  - `index.default_indexer: str = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"`
- Environment variable mapping follows `INDEXED__SEARCH__MAX_DOCS` (double underscore → nested field).

### 2. Config Store
- Persisted at **project-local** `./config.toml` (git-ignored).
- Optional **user-level** `~/.config/indexed/config.toml` (lower precedence).
- Atomic write (`tempfile` + `os.replace`) with backup `config.toml.bak`.

### 3. Precedence Rules (Highest → Lowest)
1. **Runtime overrides** (explicit kwargs / CLI flags).
2. **Environment variables**.
3. **Project `config.toml`**.
4. **User `config.toml`**.
5. **Internal defaults** (defined in schema).

### 4. ConfigService API (sync)
```python
class ConfigService:
    def load(self, *, overrides: dict | None = None) -> IndexedSettings: ...
    def save(self, settings: IndexedSettings) -> None:  # writes project toml
    def merge(self, overrides: dict | None = None) -> IndexedSettings: ...  # convenience
```
- Singleton instance accessible via `main.services.config_service.get()` to avoid repeated disk I/O.

### 5. Injection Pattern
- **CLI commands** (`create`, `search`, `update`, `mcp`, etc.) obtain a settings object at the beginning and merge CLI options with `ConfigService.merge()`.
- **MCP server** imports `ConfigService` and passes merged settings into service calls (e.g. `max_docs`).

### 6. New CLI Group `indexed config`
| Sub-command | Args | Behaviour |
| ----------- | ---- | --------- |
| `show` | `--json` | Print resolved config (json or table). |
| `set` | `key value` | Persist new value to project `config.toml`. |
| `unset` | `key` | Remove key from project file (fall back to lower precedence). |
| `edit` | *(no args)* | Open `config.toml` in `$EDITOR` (optional). |
| `validate` | | Performs full schema validation and prints result. |

### 7. Validation & Error Handling
- All writes validated by the Pydantic schema. Invalid types raise a clear message.
- On `save` we keep previous file as `.bak` in case of corruption.

## Non-Functional Requirements
- **Thread-safe**: concurrent reads allowed; writes acquire file lock (portalocker).
- **Performance**: Config cached in memory; reload only when `save` is called.
- **Security**: Sensitive credentials NOT stored in TOML—env vars only.
- **Testing**: Provide pytest fixtures with temporary config file override.

## Out of Scope
- Remote configuration sync or cloud storage.
- Secrets management tool (future work).
- GUI editor.

## Acceptance Criteria
- Running `indexed config show --json` outputs full resolved config in JSON.
- Setting a value via `indexed config set search.max_docs 20` updates `config.toml` and subsequent `indexed search` picks up the new default without flags.
- Environment variable `INDEXED__SEARCH__MAX_DOCS=5` overrides TOML at runtime but does **not** persist.
- MCP server search tool respects settings from `config.toml` when CLI flags are absent.

## Risks / Mitigations
| Risk | Mitigation |
| ---- | ---------- |
| File corruption on write | Atomic write + backup file. |
| Confusing precedence | Clear docs + `config show --source` flag (future). |
| Breaking existing scripts depending on defaults | Keep prior hard-coded defaults in schema. |

## Open Questions
1. Should we support profiles (e.g. `dev`, `ci`) inside a single TOML?  
2. How to safely edit nested keys via CLI (`--yaml` style path vs dot notation)?  
3. Add watch-for-changes & auto-reload for long-running MCP server?  
