---
type: branch
scope: config
parent: tech.md
covers: single-source config resolution, .env loading hierarchy, storage directory layout, .gitignore guard, schema versioning, config schema
updated: 2026-07-10
---

# Tech Branch: Config (`src/indexed/config/`)

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

## Read-Mostly Config & Write Safety

`config.toml` is **user-owned**: `create` / `update` / `search` never write it.
CLI-arg overrides, date-stamped incremental queries, and cutoffs live in an
**in-memory overlay** (`ConfigService.set_overlay`); `INDEXED__*` env values are
applied on top but **never** baked back into TOML. Only `indexed config set`
persists, and it writes **atomically** — serialize → validate → tmp → `fsync` →
`os.replace` — rejecting unserializable input (e.g. `null`) **before** the target
file is touched, so a bad value can never truncate `config.toml`.

**Secrets** (`_is_sensitive_key`) route to the resolved `.env`, never TOML; they
are **quoted** so a value containing ` #` or `${...}` survives a dotenv reload
intact, and are **masked** on `config inspect` / `set` output.

---

## Storage Directory Structure

Storage dirs owned by `src/indexed/config/` (`storage.py`). Persistence semantics:
[tech-core.md](tech-core.md) § Persistence Strategy.

```text
~/.indexed/                    # Global mode (default)
├── config.toml
├── .env                       # credentials (not in git)
└── data/collections/{name}/
    ├── manifest.json
    ├── documents.json
    ├── chunks.json
    └── index/
        ├── index_info.json
        ├── index_document_mapping.json
        └── indexer_FAISS_*/indexer   # binary FAISS index

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

**Key files** (`src/indexed/config/`):
- `service.py` — `ConfigService` slim orchestrator (singleton)
- `store.py` — `TomlStore` with `read_for_mode()`, schema versioning
- `workspace.py` — `WorkspaceManager.resolve_storage_mode()`
- `env_writer.py` — `EnvFileWriter` (secrets → resolved `.env`)
- `registry.py` — `ConfigRegistry` (typed spec registration)
- `provider.py` — `Provider`, the immutable typed view over merged config
- `path_utils.py` — dot-path helpers (`get_by_path`) over nested config dicts
- `storage.py` — `StorageResolver` + storage-dir layout (see § Storage Directory Structure)
- `errors.py` — `IndexedError` hierarchy

Pydantic validation models are not centralized in a `config/models.py` — each
caller registers its own `BaseModel` spec with `ConfigService.register()` (e.g.
`mcp/config.py`, core/CLI specs); `registry.py`/`service.py`/`provider.py` are
generic over any registered model type.

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

```toml
[_meta]
schema_version = "1"

[general]
log_level = "INFO"
storage_mode = "global"  # or "local"

[core.v1.indexing]
chunk_size = 512
chunk_overlap = 50
batch_size = 32

[core.v1.embedding]
model_name = "all-MiniLM-L6-v2"

[core.v1.vector_store]
index_type = "IndexFlatL2"

[core.v1.search]
max_docs = 10
max_chunks = 30
include_matched_chunks = true
min_score = 0.0

[mcp]
log_level = "INFO"
json_logs = false
transport = "stdio"
host = "127.0.0.1"
port = 8000
```

> **Note:** `[core.v1.indexing]` (`chunk_size`/`chunk_overlap`) and most of
> `[core.v1.embedding]` are currently **registered but unread** — effective
> chunking uses the embedder's token window ([tech-core.md](tech-core.md)
> § Chunk-size invariant), not `chunk_size`. Only `embedding.batch_size` and
> `[core.v1.search]` are wired today. Tracked for wiring/removal in a later
> config pass.

---

## Schema Versioning

`config.toml` carries `[_meta] schema_version`. `TomlStore.read()` extracts it
(`CURRENT_SCHEMA_VERSION = "1"`); writes ensure `_meta` is present. Provides a
migration path when config namespaces change (e.g. `core.v1.*` → `core.v2.*`).
