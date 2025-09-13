# Task Subtasks: Central Configuration Service & Config CLI

1. ✅ **COMPLETED**: Create package skeleton `src/config` with `__init__.py`, `settings.py`, `store.py`.
2. ✅ **COMPLETED**: Implement `IndexedSettings` schema in `settings.py` with pydantic-settings and TOML source helper targeting `indexed.toml`; enable `.env` loading for secrets. **FIXED**: TOML loading issue resolved.
3. ✅ **COMPLETED**: Implement `store.py` atomic read/write to `indexed.toml`, with lock + backup; never persist secrets.
4. ✅ **COMPLETED**: Add `main/services/config_service.py` with singleton, caching, profile merge, and CRUD (`get`, `set`, `update`, `delete`, `list_profiles`).
5. ✅ **COMPLETED**: Implement CLI `config` group (initial scope): `show`, `list`, `add`, `delete|unset`, `validate` (no `update`, `set`, or `edit`). Includes styled output, unknown-key warnings, and readiness breakdown.
6. (Deferred) Implement `indexed init` onboarding wizard (interactive + `--file` import) that writes only non-secret settings to `indexed.toml`; instructs user to export secrets to `.env`/env.
7. ✅ **COMPLETED**: Wire `config` group into `cli/app.py` registration.
8. ⏳ PARTIAL: Refactor `server/mcp.py` and CLI commands to consume `ConfigService.get()`; pass CLI flags as overrides; validate merged config with pydantic before service calls. (Base wiring exists; further integration pending.)
9. ✅ **COMPLETED**: Profiles support in service API; `--profile` supported across `config` commands.
10. ⏳ PARTIAL: Testing — settings/store/autocreate/config_service complete; CLI config commands covered; remaining: MCP integration behavior and precedence edge-cases.
11. ⏳ Docs: README sections for `indexed.toml` layout, `.env` usage, examples per source, profiles, security policy; note `indexed.toml` auto-creation on first use.

12. ✅ **COMPLETED**: Move configuration package to `main/config` and update all imports; remove old `src/config`.
13. ✅ **COMPLETED**: Ensure `.env.example` creation does not duplicate keys and contains guidance.
14. ✅ **COMPLETED**: Default `JIRA_API_TOKEN`/`CONFLUENCE_API_TOKEN` fallbacks honored if `*_env` not set in TOML.
15. ✅ **COMPLETED**: Unknown keys in `indexed.toml` are ignored (not fatal) and surfaced as warnings in `config validate` with full dot-paths.
16. ✅ **COMPLETED**: Prettified CLI outputs for `config validate`, `create`, `search`, `update`, `delete`.

— Newly identified pending fixes —
17. 🔧 Adjust `server/mcp.py` tests expectation: call `main.services.search_service.search` with only `query` and `configs` when possible (or update tests). Current implementation passes extra kwargs; align call signature to tests.
18. 🔧 `SearchService._discover_collections`: adapt to inputs where the persister returns folder names (e.g., `"collection1"`) and rely on `is_path_exists(f"{name}/manifest.json")` rather than scanning for files named `manifest.json`.
19. 🔧 CLI `search` printing: already adapted to new result shape; ensure exit behavior doesn’t treat Typer `Exit(0)` as error (done), verify with tests.
20. 🔧 Add/expand tests for unknown-key warnings and styled outputs (non-blocking for functionality).

—— New Subtasks: Config Formatting Service ——
21. ✳️ Create `src/main/services/config_format_service.py` with:
    - Enum `ConfigSection` and API functions `format_full`, `format_section`, `format_value`.
    - Central styling helpers and origin badge computation.
22. ✳️ Refactor `src/cli/commands/config.py` to use the new service for human-mode outputs in `get` and `list`.
23. ✳️ Add tests: `tests/services/test_config_format_service.py` and extend CLI tests for `get`/`list` unified style.
24. ✳️ Run `uv run pytest -q` and fix any regressions; ensure JSON paths are unchanged.
25. ✳️ Optional: expose a `disable_color` toggle in the formatter; keep default enabled.

—— New Subtasks: Config Injection Gateway ——
26. ✳️ Create `src/main/services/inject_config.py` with `ConfigSlice` enum and `resolve_and_extract`.
27. ✳️ Add DTOs in services: SearchArgs, CreateArgs/UpdateArgs, InspectArgs, MCPDefaults.
28. ✳️ Wire `src/cli/commands/search.py` via `resolve_and_extract(ConfigSlice.SEARCH, ...)`.
29. ✳️ Wire `src/server/mcp.py` via `resolve_and_extract(ConfigSlice.MCP_DEFAULTS, ...)`.
30. ✳️ Add tests for gateway and updated CLI/MCP behavior; run full suite.
31. ✳️ Document override precedence and `--profile` usage in README.
