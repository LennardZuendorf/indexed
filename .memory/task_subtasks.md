# Task Subtasks: Central Configuration Service & Config CLI

1. Create package skeleton `src/main/config` with `__init__.py`, `settings.py`, `store.py`.
2. Implement `IndexedSettings` schema in `settings.py` with pydantic-settings and TOML source helper targeting `indexed.toml`; enable `.env` loading for secrets.
3. Implement `store.py` atomic read/write to `indexed.toml`, with lock + backup; never persist secrets.
4. Add `main/services/config_service.py` with singleton, caching, profile merge, and CRUD (`get`, `set`, `update`, `delete`, `list_profiles`).
5. Implement CLI `config` group: `show`, `list`, `add`, `set`, `update`, `delete|unset`, `validate`, `edit`.
6. Implement `indexed init` onboarding wizard (interactive + `--file` import) that writes only non-secret settings to `indexed.toml`; instructs user to export secrets to `.env`/env.
7. Wire groups into `cli/app.py` registration (`config`, `init`).
8. Refactor `server/mcp.py` and CLI commands to consume `ConfigService.get()`; pass CLI flags as overrides; validate merged config with pydantic before service calls.
9. Profiles: add `[profiles.<name>]` in `indexed.toml`, add `--profile` support to all config CRUD and consumers.
10. Testing: precedence (CLI/env/indexed.toml/defaults), CRUD correctness, profile overlays, non-persistence of secrets, init wizard, MCP integration.
11. Docs: README sections for `indexed.toml` layout, `.env` usage, examples per source, profiles, and security policy.
