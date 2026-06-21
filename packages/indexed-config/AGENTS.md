# indexed-config — Configuration

> Scope: this package. Workflow, rules, and verify gate live in the root
> [`AGENTS.md`](../../AGENTS.md). Canonical design: [`.spec/tech-config.md`](../../.spec/tech-config.md).

## What this is

Unified configuration: explicit spec registration, Pydantic validation, automatic
secret routing, and ownership of the on-disk storage layout. `ConfigService` is a
**singleton** (`ConfigService.instance()`).

## Layer & dependencies

Lowest layer. Imports nothing above it — not `core`, connectors, CLI, or MCP.

## Where to find what

```
src/indexed_config/
  service.py       ConfigService — slim singleton orchestrator
  store.py         TomlStore.read_for_mode() · schema versioning
  workspace.py     WorkspaceManager.resolve_storage_mode()
  registry.py      ConfigRegistry — typed spec registration
  provider.py      config value provider / access
  env_writer.py    EnvFileWriter — secrets → resolved .env
  storage.py       owns storage dirs; ensure_storage_dirs(), .gitignore guard
  path_utils.py    path resolution helpers
  errors.py        IndexedError hierarchy (ConfigurationError, StorageError, …)
```

## Architecture notes

- **Single source, no merging.** Resolves to exactly one `config.toml` (local OR
  global). Mode order: CLI override → workspace pref → auto-detect (`./.indexed/`)
  → default `global`. Then `INDEXED__*` env vars and CLI args apply on top.
- **`.env` hierarchy** (`load_dotenv(override=False)`, first wins): real
  `os.environ` → `.indexed/.env` → `CWD/.env`. Secrets live in `.env`, never TOML.
- **Storage layout** (`storage.py`): `data/collections/<name>/` with
  `manifest.json`, `documents.json`, `chunks.json`, `index/`. Local mode
  auto-creates a `.gitignore` containing `.env`.
- **Schema versioning:** `[_meta] schema_version` (`CURRENT_SCHEMA_VERSION="1"`)
  gives a migration path when namespaces change (`core.v1.*` → `core.v2.*`).
- **Explicit registration only** — register specs in a `register_*()` function,
  never as an import-time side effect.
