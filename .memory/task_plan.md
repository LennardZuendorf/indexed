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

# Implementation Plan: Pretty CLI Output (Typer + Rich)

## Objective
Implement minimal, consistent human-mode output across CLI commands using Rich, keep JSON output unchanged, and centralize JSON default behavior (CLI default human; MCP default JSON). Reduce standard CLI prints; route details to logs controlled by global verbosity.

## Components
1) Dependencies
   - Add `rich>=13.0.0` to `pyproject.toml` dependencies.

2) Utilities
   - `src/cli/utils/rich_console.py`
     - Provide a singleton `Console()` instance for stdout and `err_console` for stderr.
     - Helpers: `human_size(int|None)->str`, `success_panel(title, body)`, `error_panel(title, body)`, `make_table(columns: list[str], **opts) -> Table`.
     - Progress helpers: `spinner(description)` context manager using `Progress(SpinnerColumn(), TextColumn(...), transient=True)`.

3) Formatters
   - `src/cli/formatters/search_formatter.py`
     - `render_search_result(result: dict, *, include_matched_chunks: bool) -> RenderableType` producing compact output per collection and document as specified.
   - `src/cli/formatters/inspect_formatter.py`
     - `render_inspect_table(statuses: list[CollectionStatus], *, include_size: bool) -> Table` with minimal columns and optional size.

4) JSON Mode Decision
   - `src/cli/utils/output_mode.py`
     - `should_output_json(for_context: Literal['cli','mcp'], flag_value: bool|None) -> bool` implementing precedence:
       - CLI: `--json-output` flag (True) > config `flags.cli_json_output` (bool) > default False.
       - MCP: future flag > config `mcp.mcp_json_output` (bool) > default True.
     - Read config via `ConfigService.get()`; avoid circular imports by keeping it simple.

5) Logging defaults
   - Set default log level to WARNING globally (both CLI and MCP). Keep ability to set `--verbose` (DEBUG) or `--log-level`.

## Integration by Command
1) Inspect (`cli/app.py:inspect_cmd`)
   - Use `should_output_json('cli', json_output)` to decide. If human, use `render_inspect_table` and print via Console. Remove manual string tables.
   - Rename option to `--index-size` (keep semantics). Wire through to `InspectService`.
2) Search (`cli/commands/search.py`)
   - Decide JSON with `should_output_json('cli', json_out)`. If human, render header (what) and `render_search_result` for result (result). No progress spinner (fast path). Keep JSON path identical.

3) Create / Update (`cli/commands/create.py`, `cli/commands/update.py`)
   - Reduce pre-action prints to a single concise “Creating …/Updating …”.
   - Wrap service calls in a single transient spinner `with spinner('Preparing…'):` and update the action description as phases change (Preparing → Reading → Indexing) based on available checkpoints.
   - On success, show a concise success line, optionally with a success panel if we can read manifest quickly for docs/chunks/updated.
   - Errors render as `error_panel` with message; details to logs.

4) Delete (`cli/commands/delete.py`)
   - Minimal candidates table using Rich (Name, Docs, Chunks, Updated). Keep confirmation logic. Final concise summary line.

## Config Additions
- `flags.cli_json_output: bool = false` (optional; default False)
- `mcp.mcp_json_output: bool = true` (optional; default True)
Placement aligns with existing `flags` and `mcp` sections in `IndexedSettings`.

## Precedence Rules
- JSON output decision:
  - CLI: flag `--json-output` > `flags.cli_json_output` > False.
  - MCP: flag (future) > `mcp.mcp_json_output` > True.
- Logging level decision remains: CLI flags/env/config > default (CLI: WARNING, MCP: INFO).

## Testing
- Unit tests for `should_output_json` precedence.
- Update CLI tests to validate human-mode rendering entry points (basic substrings) and ensure JSON path unchanged.
- Verify default logging level change doesn’t break existing tests (adjust expectations if needed).

## Rollout Steps
1) Add dependency `rich` and `uv sync`.
2) Implement utilities and formatters.
3) Wire Inspect and Search first (low risk).
4) Wire Create/Update/Delete with spinner and concise messages.
5) Implement JSON decision helper and use across commands; adjust MCP server to default JSON.
6) Adjust CLI default logging level to WARNING.
7) Update/extend tests and docs.

## Risks & Mitigations
- Rich dependency footprint: lightweight; vendor only where needed.
- Overwriting user expectations for logs: maintain verbose flag and document new defaults.
- Spinner phases fidelity: keep generic spinner to avoid coupling to service internals.

# Task Plan: KISS Loguru Central Logging (Architect Mode)

## Objective
Implement a single, centrally controlled logging setup using Loguru. Control verbosity (and optional JSON) once at process start; keep all existing `logging.*` calls via interception. No per-service level logic.

## Validation against Loguru docs
- Central level filtering at sink: `logger.add(sys.stderr, level="INFO")` ignores lower levels; change by remove/re-add. (Docs: add handler with level; troubleshooting example shows `level="WARNING"` only emits >= WARNING.)
- Remove default and add custom: `logger.remove(); logger.add(sys.stderr, level="...")`. (Docs: recipes remove default handler.)
- Intercept stdlib: configure `logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)` and forward records to Loguru; Loguru then applies sink level. (Docs: README interception pattern.)
- Optional JSON: `logger.add(..., serialize=True)`. (Docs: README serialization.)

## Design Decisions
1) Single initializer `setup_root_logger(level_str: str = "INFO", json_mode: bool = False) -> None` in `main/utils/logger.py`:
   - If already configured, no-op (module-level guard `_LOGGING_CONFIGURED`).
   - `logger.remove()` then `logger.add(sys.stderr, level=level_str, serialize=json_mode, format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}")`.
   - Install stdlib interception handler so existing `logging.*` calls are routed to Loguru.
   - Quiet noisy third-party loggers to WARNING (e.g., `faiss`, `sentence_transformers`).
2) Central control points only:
   - CLI root (`cli/app.py`): global options `--verbose/--log-level/--json-logs`; initialize once via `@app.callback()`.
   - MCP entry (`server/mcp.py`): initialize from args/env before starting server.
3) Precedence for level/json: CLI flags > env (`INDEXED_LOG_LEVEL`, `INDEXED_LOG_JSON`) > config (`settings.logging.level/json`) > defaults.
4) Keep existing service/module `logging.*` calls; do not refactor call sites. Existing `setup_root_logger()` calls inside services remain safe because initializer is idempotent.

## Changes Required
1) `pyproject.toml`
   - Add dependency: `loguru`.

2) `src/main/utils/logger.py`
   - Replace current stdlib logger setup with Loguru-based initializer + stdlib interception handler.
   - Expose `setup_root_logger(level_str: str | int | None = None, json_mode: bool | None = None) -> None`.

3) `src/cli/app.py`
   - Add global options via `@app.callback()`:
     - `--verbose` (bool → DEBUG), `--log-level` (choice), `--json-logs` (bool).
   - Resolve effective level/json using precedence (consume env/config if flags absent).
   - Call `setup_root_logger()` once before any command runs.

4) `src/server/mcp.py`
   - Before `mcp.run(...)`, resolve level/json from args/env/config and call `setup_root_logger()`.
   - Optionally align `--log-level` arg with CLI choices.

5) `src/main/config/settings.py`
   - Add optional `LoggingSettings` section to `IndexedSettings`:
     - `level: str = "INFO"`, `json: bool = False` (env keys `INDEXED__logging__level`, `INDEXED__logging__json`).

6) `src/main/config/store.py`
   - Update `ensure_indexed_toml_exists()` scaffold to include:
     - `[logging]\n# level = "INFO"\n# json = false`.

7) Services imports
   - Leave existing `setup_root_logger()` imports/calls; make initializer no-op when already configured.

8) Tests
   - Add minimal tests validating initializer idempotency and level control via env/flag precedence.
   - Ensure existing tests remain green (logs routed but behavior unchanged).

## Rollout Steps
1) Add `loguru` to dependencies and `uv sync`.
2) Implement `logger.py` initializer + interception.
3) Wire CLI callback and MCP init; resolve level/json with precedence.
4) Extend settings schema and TOML scaffold.
5) Run tests and lint; adjust noisy logger levels if needed.

## Risks & Mitigations
- Double initialization: guard in `setup_root_logger` avoids duplicate sinks.
- Test capture of logs: stdlib interception keeps compatibility; if caplog relies on stdlib, basicConfig with InterceptHandler preserves capture.

# Task Plan: Config Injection Gateway (inject_config)

## Objective
Implement a central runtime adapter that resolves and validates `IndexedSettings` via `ConfigService`, merges CLI/env overrides, and derives operation parameters passed to `services` (`search`, `update`, `inspect`). Adopt it in CLI commands and MCP.

## Design Decisions
1. Module location: `src/main/services/inject_config.py`.
2. Public API:
   - Enum `ConfigSlice` = { SEARCH, CREATE, UPDATE, INSPECT }
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
3. MCP (`src/server/mcp.py`): call `resolve_and_extract(ConfigSlice.SEARCH, ...)` for search; use `resolve_and_extract(ConfigSlice.INSPECT, ...)` for status resources; build `SourceConfig` as needed for `search_collection`.
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
