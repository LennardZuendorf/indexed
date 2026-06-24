---
type: branch
scope: config
parent: tech.md
covers: single-source config resolution, .env loading hierarchy, storage directory layout, .gitignore guard, schema versioning, config schema
updated: 2026-06-15
---

# Tech Branch: Config (`indexed-config`)

Unified config: explicit registration, Pydantic validation, automatic secret routing.
Lowest layer — imports nothing above it (see [tech.md](tech.md) § Architectural Rules).

**Parent: [tech.md](tech.md).**

---

## Single-Source Config Resolution

Resolves to **one** `config.toml` — local OR global, never both. No merging.

**Mode resolution order** (`WorkspaceManager.resolve_storage_mode()`):

| Priority | Source | Example |
|----------|--------|---------|
| 1 (highest) | CLI `mode_override` | `--local` / `--global` |
| 2 | Workspace preference | global config `[workspace].mode` |
| 3 | Auto-detect | local `.indexed/config.toml` exists → local |
| 4 (lowest) | Default | `"global"` |

Once resolved, `TomlStore.read_for_mode(mode)` reads the single source. Then
`INDEXED__*` env vars and CLI arguments apply on top.

---

## .env Loading Hierarchy

All `.env` files use `load_dotenv(override=False)` — first loaded wins; real env
vars never overridden.

| Priority | Source | Description |
|----------|--------|-------------|
| 1 (highest) | real `os.environ` | set before process starts, never touched |
| 2 | `.indexed/.env` | from resolved root (local or global), loaded first |
| 3 (lowest) | `CWD/.env` | standard project .env, fills gaps only |

`INDEXED__*` env variables are mapped into the TOML config dict separately (not via `.env`).

---

## Storage Directory Structure

Storage dirs owned by `indexed-config` (`storage.py`). Persistence semantics:
[tech-core.md](tech-core.md) § Persistence Strategy.

```text
~/.indexed/                    # Global mode (default)
├── config.toml
├── .env                       # credentials (not in git)
└── data/
    ├── collections/{name}/
    │   ├── manifest.json
    │   ├── documents.json
    │   ├── chunks.json
    │   └── index/
    │       ├── index_info.json
    │       ├── index_document_mapping.json
    │       └── indexer_FAISS_*/indexer   # binary FAISS index
    └── caches/                # document caches

./.indexed/                    # Local mode (per-project)
├── config.toml
├── .env
├── .gitignore                 # auto-created with ".env" entry
└── data/collections/...
```

**`.gitignore` auto-creation:** `ensure_storage_dirs(is_local=True)` creates a
`.gitignore` containing `.env` (appends `.env` if the file exists but lacks it).
Not applied to `~/.indexed/` (outside git repos).

---

## Implementation

**Key files:**
- `service.py` — `ConfigService` slim orchestrator (singleton)
- `store.py` — `TomlStore` with `read_for_mode()`, schema versioning
- `workspace.py` — `WorkspaceManager.resolve_storage_mode()`
- `env_writer.py` — `EnvFileWriter` (secrets → resolved `.env`)
- `registry.py` — `ConfigRegistry` (typed spec registration)
- `provider.py` — `Provider` (public bound-config type returned by `bind()`)
- `storage.py` / `path_utils.py` — storage dirs + path helpers
- `errors.py` — `IndexedError` hierarchy

```python
class ConfigService:
    """Singleton config service. Orchestrates registry, store, and workspace."""
    _instance = None

    @classmethod
    def instance(cls) -> "ConfigService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
```

---

## Config Schema

`indexed-config` owns config **resolution and storage**, not the domain schemas.
Each section's Pydantic model lives in the package that owns it — keeping this doc
free of cross-package duplication that silently drifts. Config-owned keys:

```toml
[_meta]
schema_version = "1"   # = CURRENT_SCHEMA_VERSION

[workspace]
mode = "global"        # or "local" — storage-mode preference
```

Sections validated elsewhere (model → owner doc):

| Section | Owner | Selected fields / defaults |
|---------|-------|----------------------------|
| `[core.v1.indexing]` | [tech-core.md](tech-core.md) | `chunk_size`, `chunk_overlap` |
| `[core.v1.embedding]` | [tech-core.md](tech-core.md) | `model_name`, `dimension`, `device`, `batch_size` (128) |
| `[core.v1.storage]` | [tech-core.md](tech-core.md) | `type`, `index_type` (FAISS index, default `IndexFlatL2`), `persistence_enabled`, `persistence_path` |
| `[core.v1.search]` | [tech-core.md](tech-core.md) | `max_docs`, `max_chunks`, `score_threshold` (default `None`) |
| `[mcp]` | [tech-app.md](tech-app.md) | `host` (`localhost`), `port` (8000), `log_level` (`WARNING`), `enable_async_pool`, `include_index_size` |

There is **no** `[general]` section, and `transport` / `json_logs` are MCP CLI
flags, not `[mcp]` config fields.

---

## Schema Versioning

`config.toml` carries `[_meta] schema_version`. `TomlStore.read()` extracts it
(`CURRENT_SCHEMA_VERSION = "1"`); writes ensure `_meta` is present. Provides a
migration path when config namespaces change (e.g. `core.v1.*` → `core.v2.*`).
