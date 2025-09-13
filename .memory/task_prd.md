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
