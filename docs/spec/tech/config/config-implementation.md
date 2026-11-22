---
type: tech
updated: 2026-11-22
applies: "src/indexed/config/**"
---

# Implementation

**Key files** (`src/indexed/config/`):
- `service.py` — `ConfigService` slim orchestrator (singleton)
- `store.py` — `TomlStore` with `read_for_mode()`, schema versioning
- `workspace.py` — `WorkspaceManager.resolve_storage_mode()`
- `env_writer.py` — `EnvFileWriter` (secrets → resolved `.env`)
- `registry.py` — `ConfigRegistry` (typed spec registration)
- `provider.py` — `Provider`, the immutable typed view over merged config
- `path_utils.py` — dot-path helpers (`get_by_path`) over nested config dicts
- `storage.py` — `StorageResolver` + storage-dir layout (see [Storage Directory Structure](config-storage-directory-structure.md))
- `collections_registry.py` — global collection registry (stable ids) + per-workspace pointer file (#346)
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
