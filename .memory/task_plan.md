# Task Plan: Config Formatting Service (Unified Output for Config CLI)

## Objective
Create a reusable formatting service that returns pre-formatted strings for config-related commands, unifying emojis, colors, section ordering, and origin badges. Integrate it into `config get` and `config list`, and prepare for `config show` if added later.

## Design Decisions
1. Module location: `src/main/services/config_format_service.py`.
2. Public API:
   - `class ConfigSection(Enum)`: `ALL`, `PATHS`, `SEARCH`, `INDEX`, `SOURCES`, `MCP`, `PERFORMANCE`, `FLAGS`.
   - `format_full(settings: IndexedSettings, profile: str | None = None) -> str`
   - `format_section(section: ConfigSection, settings: IndexedSettings, profile: str | None = None) -> str`
   - `format_value(key_path: str, settings: IndexedSettings, profile: str | None = None) -> str`
   - Optional: `disable_color: bool = False` parameter added later (keep internal feature flag for easy extension).
3. Responsibility separation:
   - Reuse origin detection consistent with current logic (env > toml > default) by building an origin map from an effective settings dump plus merged TOML for the given profile. The service will include internal helpers mirroring current behavior in `config.py`.
   - Styling helpers (bold/color, badges) live in the service to avoid duplication across commands.
4. Deterministic ordering: sort keys in all sections.
5. No printing; functions return strings.

## Integration Plan
1. Add new service file with enum and functions, along with helpers ported from `cli/commands/config.py`:
   - `bold`, `color`, `status_style`, `_origin_badge`, `_stringify`, `_render_json`, origin map helpers.
   - IMPORTANT: Do not create circular imports. Only import `IndexedSettings` and `read_toml` and `.env` reader used for origin.
2. Refactor `src/cli/commands/config.py`:
   - For human-mode outputs:
     - `get`: replace inline printing with `format_value(...)` and print the returned string.
     - `list`: replace summary + sections rendering with `format_full(...)` when `prefix is None`; and `format_section(...)` for top-level prefixes that match enum; fall back to JSON/human key-only listing behavior as today for other cases.
   - Keep JSON outputs unmodified.
3. Add minimal unit tests:
   - `tests/services/test_config_format_service.py` with fixtures building small `IndexedSettings` objects and env vars to assert badges `[env]/[toml]/[default]` and key ordering.
   - Extend `tests/cli/test_commands.py` cases for `config get` and `config list` to assert unified style substrings.

## Step-by-step
1. Implement `config_format_service.py` with:
   - Enum and API signatures.
   - Helpers to compute origin map using merged TOML (`read_toml`) and `.env` fallback (non-exporting) consistent with CLI.
   - Renderers for full summary, per-section, and single value.
2. Wire into CLI commands (`get`, `list`). Feature-guard changes to minimize diff wherever possible.
3. Add tests and run: `uv run pytest -q`.
4. Lint/format: `uv run ruff check .` and `uv run ruff format`.

## Risks & Mitigations
- Potential duplication of helpers between CLI and service: fully move helpers into the service and import them from the CLI to avoid drift.
- Slight changes in output compared to current implementation: lock in expected strings via tests and keep emojis/phrases as in the service.

## Deliverables
- New `src/main/services/config_format_service.py`.
- Refactor of `src/cli/commands/config.py` to use the service for human-mode formatting in `get` and `list`.
- Tests verifying new service and updated CLI behavior.

---

# Task Plan: Config Injection Gateway (inject_config)

## Objective
Implement a central runtime adapter that resolves and validates `IndexedSettings` via `ConfigService`, merges CLI/env overrides, and derives operation parameters passed to `services` (`search`, `update`, `inspect`). Adopt it in CLI commands and MCP.

## Design Decisions
1. Module location: `src/main/services/inject_config.py`.
2. Public API:
   - Enum `ConfigSlice` = { SEARCH, CREATE, UPDATE, INSPECT, MCP_DEFAULTS }
   - `resolve_and_extract(kind: ConfigSlice, *, profile: str | None, overrides: dict | None, target: str | None = None) -> tuple[IndexedSettings, Any]`
   - Services define their DTOs (SearchArgs, CreateArgs, UpdateArgs, InspectArgs). MCPDefaults provided for MCP.
3. Precedence order: CLI overrides > env/.env > TOML > defaults (leverages `ConfigService.get` with overrides).
4. Keep functions pure (no printing); do not import Typer.
5. MCP uses env-provided profile/overrides if set; otherwise defaults from settings.

## Integration Plan
1. Implement `inject_config.py` with functions above and dataclasses.
2. CLI commands:
   - `search`: accept `--profile`; call `resolve_and_extract(ConfigSlice.SEARCH, ...)`; pass returned args to `svc_search`.
   - `update`: call `resolve_and_extract(ConfigSlice.UPDATE, ...)`; pass returned args to `svc_update`.
3. MCP (`src/server/mcp.py`): call `resolve_and_extract(ConfigSlice.MCP_DEFAULTS, ...)` at startup or per-call; use defaults to drive search; build `SourceConfig` as needed.
4. Tests: add unit tests for `config_runtime` functions and adapt CLI/MCP tests to validate invocation and behavior.

## Step-by-step
1. Create `config_runtime.py` with pure helpers.
2. Wire `cli/commands/search.py` to use runtime for defaults/overrides.
3. Wire `server/mcp.py` to use runtime for defaults and indexer lookup; keep current API to `search_service` intact.
4. Add tests, run `uv run pytest -q`.
5. Lint/format.

## Risks & Mitigations
- Coupling to settings layout: access fields defensively and keep safe fallbacks.
- Performance: if called per-invocation, acceptable; for MCP long-running, cache settings in module-level var or rely on service caching.

## Deliverables
- New `src/main/services/config_runtime.py`.
- CLI `search` and MCP server updated to use runtime.
- Tests covering runtime behavior.
