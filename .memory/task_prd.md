# Task PRD: Config Formatting Service (Unified Human Output for Config CLI)

## Goal
Provide a single, reusable formatting service that returns pre-formatted, emoji- and ANSI-styled strings for configuration-related CLI commands. This ensures unified look-and-feel and eliminates duplicated formatting logic across `config get`, `config list` (and a future `config show`).

## Motivation / Value
- Consistent output across commands; one source of truth for emojis, colors, badges, and section ordering.
- Cleaner CLI command code (commands simply call a formatter and print the returned string).
- Easier to extend (add a new section or badge once in the formatter; all commands benefit).
- Testable: formatting can be unit-tested as pure string-returning functions.

## In Scope
- A new service that:
  - Computes origin badges (env/toml/default) for values using the same precedence rules as today.
  - Renders:
    1) a specific key’s value (for `config get`),
    2) a full multi-section view (for `config list` without prefix),
    3) a single top-level section like `flags` (for `config list flags`).
  - Returns a single string for each render call (commands just `echo` it).
  - Allows selecting “all sections” vs. a specific section via an enum.
- Keep JSON output paths unchanged (JSON stays raw, not styled).

## Out of Scope
- Changing configuration schema or precedence.
- Storing secrets. (Formatter only displays origin; values are already scrubbed by schema/policy.)
- Non-config commands.

## Users / Use Cases
- CLI users invoking `indexed config get ...`, `indexed config list`, or `indexed config list flags`.
- Developers adding new sections; they extend the enum and a single renderer.

## Functional Requirements
- Provide an enum to control scope:
  - `ConfigSection`: `ALL`, `PATHS`, `SEARCH`, `INDEX`, `SOURCES`, `MCP`, `PERFORMANCE`, `FLAGS`.
- Provide functions that accept an `IndexedSettings` instance (or dict), optional `profile`, and produce formatted strings:
  - `format_full(settings, profile) -> str` (summary + sections)
  - `format_section(section: ConfigSection, settings, profile) -> str`
  - `format_value(key_path: str, settings, profile) -> str`
- Provide consistent styling helpers (bold/color) and emojis, centralized in this service.
- Compute and attach origin badges `[env]`, `[toml]`, `[default]` at leaf values.
- For `SOURCES`, render nested subsections for `files`, `jira_cloud`, and `confluence_cloud` with their own badges.

## Non-Functional Requirements
- Pure string outputs; no direct printing from the service.
- Minimal coupling: depends only on types (`IndexedSettings`) and `os.environ`/.env for origin detection.
- Deterministic ordering of keys within sections (sorted) for stable tests.
- Toggleable ANSI coloring (default on); future-proof a `disable_color` flag if needed.

## Acceptance Criteria
- `config get` uses `format_value` output verbatim for human mode and shows correct origin badge.
- `config list` with no prefix uses `format_full` and matches the unified style (same emojis/ordering as the service defines).
- `config list flags` uses `format_section(ConfigSection.FLAGS, ...)` and shows badges per key.
- JSON outputs remain unchanged from current behavior.
- Unit tests cover: full render, section render, and value render (including origin badges and key ordering).

## Risks / Mitigations
- Risk: Divergence between service and CLI behavior. Mitigation: make CLI delegate all human-mode formatting to the service.
- Risk: Origin computation drift. Mitigation: centralize origin map computation within the service; write tests for env/toml/default cases.

## Open Questions
- Do we want a public `format_prefix(prefix: str, ...)` for arbitrary dot-path rendering beyond top-level sections? (Initial version covers value rendering via `format_value` and section rendering via enum.)  

---

# Task PRD: KISS Loguru Integration (Structured, Simple, Level-Controlled)

## Goal
Adopt Loguru for unified logging with minimal surface area. Keep it simple: one initializer, capture existing `logging.*` calls, and allow controlling the log level via CLI flag, env var, or config. Default to human-readable console logs; optional JSON serialization is a single boolean toggle.

## Motivation / Value
- Consistent logging across CLI, services, and MCP with near-zero code churn.
- Preserve existing `logging.*` calls via interception to avoid mass refactors.
- Easy level control: `--verbose` or `--log-level` CLI, `.env`/env var, and config default.

## Non-Goals
- No complex correlation IDs or extensive context binding in v1.
- No multi-sink routing or remote transports.

## Minimal Design
- Single module: `main/utils/logger.py` provides `setup_root_logger(level: str | int = "INFO", json_mode: bool = False) -> None` implemented with Loguru.
  - Add a single sink to `sys.stderr` with simple format: "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}".
  - Support `json_mode` by using `serialize=True` when enabled.
  - Install an InterceptHandler so stdlib `logging` records flow into Loguru (captures existing calls).
  - Set noisy third-party loggers to `WARNING`.
- Central initialization points only:
  - CLI (`cli/app.py`): initialize early based on CLI flags/env/config.
  - MCP server (`server/mcp.py`): initialize from its `--log-level` argument or env/config.
  - Remove per-module initializers if present (or keep as no-op when already configured).

## Level Control (three ways)
- CLI: add `--verbose` (bool → DEBUG) and `--log-level {CRITICAL,ERROR,WARNING,INFO,DEBUG}` on the root Typer app.
- Env: `INDEXED_LOG_LEVEL` (e.g., `DEBUG`) and `INDEXED_LOG_JSON` (`true|false`).
- Config (IndexedSettings): add optional `logging` section:
  - `logging.level: str = "INFO"`
  - `logging.json: bool = false`
  - These map to env keys `INDEXED__logging__level` and `INDEXED__logging__json`.

Precedence: CLI flag > env > config > default.

## Structured Fields (v1)
- Keep message-focused logs; let Loguru add standard fields (time, level, message).
- If `json` enabled, emit JSON with default Loguru structure (time, level, message, module, line, etc.).

## Key Logging Hotspots (must-have)
- Configuration lifecycle
  - `main/services/config_service.py`: `get()` – profile used, overrides presence, unknown key warnings; `atomic_write_toml()` save success/failure.
  - `main/config/store.py`: validation errors in `validate_no_secrets()`, lock/backup write failures.
- CLI entrypoints
  - `cli/app.py`: selected log level/source (CLI/env/config), command invocation name.
  - `cli/commands/search.py`: query start with options (collection, limits); summarize results count; error output path already handled.
- Search and Inspect
  - `main/services/search_service.py`: per-collection search start/finish and caught exceptions (already logs errors; keep via interception). Optionally one INFO summary with docs/chunks counts.
  - `main/services/inspect_service.py`: index-size computation failures, per-collection status errors (already present; keep).
- Create/Update orchestration
  - `main/services/collection_service.py`: create/update start/finish per collection; surface ValueErrors for missing envs; optionally brief success messages.
- Utilities
  - `main/utils/performance.py`, `batch.py`, `retry.py`, `sources/*` readers: retain existing logs; interception will route to Loguru.

## Changes Required
1) Replace implementation of `main/utils/logger.py` to use Loguru with an InterceptHandler and one stderr sink.
2) Initialize logging once at process start:
   - `cli/app.py`: parse `--verbose`/`--log-level` and env/config, call `setup_root_logger()`.
   - `server/mcp.py`: call `setup_root_logger()` based on `--log-level` or env/config.
3) Settings: add optional `logging` section to `IndexedSettings` and scaffold it in `ensure_indexed_toml_exists()`.
4) Keep existing `logging.*` calls; do not refactor call sites.

## Acceptance Criteria
- Running any CLI command shows Loguru-formatted output at the correct level; `--verbose` switches to DEBUG.
- Env `INDEXED_LOG_LEVEL=DEBUG` and config `logging.level = "DEBUG"` both work when CLI flag is absent.
- MCP honors `--log-level` and env/config when unspecified.
- Existing unit tests continue to pass; no behavior changes to return values.

## Risks / Mitigations
- Double-initialization: guard to avoid adding multiple sinks.
- Test expectations around logging: interception ensures stability; caplog remains workable by configuring stdlib logging if needed.

## Open Questions
- Do we want a single `--json-logs` flag for JSON mode now or defer? Proposed: include flag but default off.

# Task PRD: Config Injection Runtime (Gateway for CLI and MCP)

## Goal
Centralize configuration resolution, validation, and runtime parameter derivation for all entry points (CLI commands and MCP server). Provide a thin, reusable gateway that merges CLI/env overrides with `ConfigService` output and injects derived parameters into core services.

## Motivation / Value
- Single source of truth for loading and validating settings (profile-aware; env/TOML precedence).
- Remove duplicated config handling in CLI and MCP; reduce drift and bugs.
- Enable consistent defaults (e.g., indexer, limits, flags) with clear override rules.
- Make future features (flags, profiles, env) available across all entry points without per-command rewrites.

## In Scope
- A small runtime/gateway that:
  - Loads `IndexedSettings` via `ConfigService.get(profile, overrides)` (validation included).
  - Builds operation-specific parameters from settings with CLI overrides applied (e.g., search limits, include flags, default indexer).
  - Exposes helpers to construct `SourceConfig` lists from configured sources when needed.
- Adoption in:
  - CLI commands in `src/cli/commands/` (at least `search`, `update`, and any command using default indexer).
  - MCP server in `src/server/mcp.py` (read mcp/search defaults from settings with env fallback).

## Out of Scope
- Changing core services APIs (`search_service`, `inspect_service`, `collection_service`).
- Persisting overrides. Runtime overrides remain ephemeral.
- Redesigning the configuration schema.

## Users / Use Cases
- CLI users leveraging profiles and defaults without specifying every flag.
- MCP deployments that want consistent behavior via config (e.g., default indexer/limits, include flags).

## Functional Requirements
- Provide a function/class to resolve settings with precedence: CLI overrides > env/.env > TOML > defaults.
- Provide helpers to derive per-operation args:
  - Search: `configs` (optional), `max_docs`, `max_chunks`, `include_*` flags, default indexer fallback.
  - Update: list of collections to update (from configured sources or discovered), default indexer when needed.
- Work without mandatory settings for disk-only flows (e.g., searching existing collections) while still validating the overall config object.
- Allow per-command `--profile` to select the profile; env var fallback allowed (e.g., `INDEXED_PROFILE`).

## Non-Functional Requirements
- KISS: minimal surface; avoid decorators unless needed by ergonomics.
- No circular imports; place runtime under `main/services/` to be shared by CLI and MCP.
- Deterministic behavior with clear override order.

## Acceptance Criteria
- CLI `search` loads and validates settings once, applies CLI overrides, and calls `SearchService` with derived params. Defaults align with settings when flags are omitted.
- MCP reads settings (with env fallback) and applies configured defaults for search and inspect where applicable.
- No regression in existing tests; add unit tests asserting runtime is invoked and behavior for overrides.
- Code has no linter errors and follows existing style.

## Risks / Mitigations
- Risk: Tight coupling to current settings schema. Mitigation: limit the runtime to a small adapter that reads only necessary fields with safe defaults.
- Risk: Global option propagation across CLI subcommands. Mitigation: start with per-command `--profile`; consider global option later if needed.

## Open Questions
- Should we add a global `--profile` option at the root Typer app? Initial version will add `--profile` only to affected commands to keep changes small.

u---

# Task PRD: Pretty CLI Output (Typer + Rich, Minimal Human Output)

## Goal
Minimize human-facing CLI output to essentials (what, progress, result), keep JSON schemas unchanged, and control verbosity via logging flags.

## JSON Output Defaults
- CLI: default human output; return JSON only when explicitly requested via `--json-output` or an opt-in config value `flags.cli_json_output` (bool).
- MCP: default JSON output true for requests; allow override via config `mcp.mcp_json_output` (bool) and future flags.

## Principles
- Human mode shows only what/progress/result.
- JSON mode returns machine-readable results with the existing schema.
- Verbose details go to logs (respecting `--verbose` / `--log-level`).

## In Scope (commands)
- create (jira|confluence|files), update, delete, inspect, search.

## UX per command (human mode)
- Create/Update: transient spinners for phases; concise success summary; errors concise.
- Delete: minimal candidates list; confirmations; concise result.
- Inspect: single compact table (Name, Docs, Chunks, Updated). Optional Size behind flag.
- Search: header; compact results per collection with minimal per-doc line and optional chunk previews when requested.

## Configuration
- Add config toggles to control JSON output defaults:
  - `flags.cli_json_output: bool = false` (CLI default human unless true or flag present)
  - `mcp.mcp_json_output: bool = true` (MCP default JSON; can be set false if desired)
- CLI precedence: flag `--json-output` > `flags.cli_json_output` > default human.

## Acceptance Criteria
- CLI returns human by default and JSON only when requested (`--json-output` or `flags.cli_json_output`).
- MCP returns JSON by default (`mcp.mcp_json_output` true).
- JSON schemas/content unchanged.
- Spinners are transient; logs contain details under verbose.
