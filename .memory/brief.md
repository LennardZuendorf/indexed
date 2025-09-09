# Project Brief

## What it does
Local, privacy-first document indexing and vector search for:
- Jira (Server/Data Center and Cloud)
- Confluence (Server/Data Center and Cloud)
- Local files (PDF, PPTX, DOCX, etc. via Unstructured)

## Key capabilities
- Create, update, and search collections stored locally
- MCP stdio integration to expose search as a tool
- Update is incremental based on lastModified time

## CLI (Typer) quick reference
- `indexed init` → Guided setup; create `config.yaml` (and optionally `.env`)
- `indexed source add jira|confluence|folder` → Add source to config
- `indexed source list` / `indexed source show <name>` → Inspect configured sources
- `indexed source update [<name>]` → Update all or one source (create if missing)
- `indexed source remove <name> [--purge-data]` → Remove source; optionally delete data
- `indexed status [--sources <list>]` → Collection stats (docs, chunks, last update, indexers)
- `indexed manifest <name>` → Print manifest.json
- `indexed search "<query>" [--sources <list>] [--max-chunks N] [--max-docs N] [--include-full-text]` → Local search
- `indexed indexers list` → Show available indexers
- `indexed cache clear [<name>]` → Clear read cache
- `indexed doctor` → Validate env vars, endpoints, FS permissions
- `indexed mcp [--sources <list>] [--index <name>] [--max-chunks N] [--max-docs N] [--include-full-text] [--config <path>]` → Start MCP server

## Configuration plan
- Central TOML config (`./config.toml`, git-ignored); optional user-level `~/.config/indexed/config.toml`
- Load with pydantic-settings (TomlConfigSettingsSource) + `.env` for secrets
- Precedence: CLI flags > env/.env > user TOML > project TOML > defaults
- Atomic saves for persistence; secrets stay in env

## Requirements for this iteration
- Implement the `indexed` Typer CLI and services (config, source, status, search, mcp, cache, doctor)
- Use TOML + pydantic-settings for config loading; implement atomic save
- Map CLI commands to existing factories and root scripts; avoid changes in `main/`
- Provide aggregated multi-source search and a unified MCP server

## Non-goals
- Changing on-disk collection layout or `main/` module behaviors
- Replacing FAISS or embedding models

## Milestones and To-Dos
- CLI & Config: Typer `indexed` entrypoint; pydantic-settings TOML loader; atomic save; add/list/show/remove sources
- Update & Status: create-on-missing/update orchestration; status/manifest; optional index size
- Search: single and aggregated multi-source search; indexers list
- MCP: unified stdio server with per-source tools and optional search_all
- Utilities: cache clear; doctor checks (env, endpoints, FS)
- Docs: README CLI section, config.toml example, MCP usage; keep legacy scripts documented

## FastAPI MCP extension (optional)
- Offer HTTP-hosted MCP using FastAPI + FastMCP:
  - Generate MCP from FastAPI (`FastMCP.from_fastapi(app)`) or mount MCP into FastAPI at `/mcp`
  - New CLI (planned): `indexed serve-http` and `indexed mcp-from-fastapi`
- Notes: Prefer curated tools; set lifespan correctly; consider new OpenAPI parser env flag
- Ref: [FastAPI 🤝 FastMCP](https://gofastmcp.com/integrations/fastapi)

## Focus
- Primary entry points: Typer CLI (`indexed`) and MCP stdio server (`indexed mcp`)
- No HTTP server in scope for this iteration

## PRD (Product Requirements)
- **Goal**: Provide a local, privacy-first vector search tool with a single CLI (`indexed`) and a unified MCP stdio server.
- **Users**: Developers, data/knowledge managers, AI agent builders who need to index and query Jira, Confluence, and local files.
- **Primary Use Cases**:
  1. Quickly add data sources (Jira, Confluence, folders) via interactive CLI or one-shot flags.
  2. Incrementally update or recreate collections without manual script juggling.
  3. Monitor status (docs, chunks, last update, index size) via a single command.
  4. Run semantic search locally or expose it to LLM agents via MCP stdio.
  5. Maintain configuration in a simple, user-editable TOML file with env-based secrets.
- **Non-Goals**: HTTP API/UI (future), changing existing core indexing logic, remote data storage.

## Jobs to be Done / Features
1. **Setup & Config** – `indexed init`, `source add/list/show/remove` manage TOML config; secrets stay in .env.
2. **Data Ingestion** – `source update` creates or updates collections via existing factories.
3. **Status & Monitoring** – `status`, `manifest`, optional index size.
4. **Search** – `search` (single or multi-source) and `indexers list`.
5. **MCP Exposure** – `indexed mcp` launches a multi-source FastMCP stdio server for agent integration.
6. **Maintenance Utilities** – `cache clear`, `doctor` for diagnostics.
7. **Documentation & Examples** – README section, example config.toml.

## Task Clusters (high-level)
- **CLI & Config Layer** – Typer entrypoint, settings loader, config store, ConfigService.
- **Collection Orchestration** – SourceService for create/update; relies on main.factories.
- **Status & Monitoring** – StatusService.
- **Search & Indexers** – SearchService, aggregated results.
- **MCP Service** – unified stdio server.
- **Utilities** – CacheService, DoctorService.
- **Docs & Packaging** – README, example config, pyproject updates, entrypoint script.

## Backlog
- CLI output/UX polish: Prettify and standardize output across commands (especially `create files`).
  - Consistent success/error messaging and symbols
  - Use richer formatting (colors, tables, progress bars) where helpful
  - Compact default output with optional `--verbose` and `--quiet` modes
  - JSON output remains stable and pretty-print behind `--json`
  - Clear, structured error details with actionable hints and proper exit codes
  - Consider adopting `rich` for formatting and progress rendering
  - Specifically, prettify `update` command and controller outputs (aligned columns, clearer headers, symbols, progress)
