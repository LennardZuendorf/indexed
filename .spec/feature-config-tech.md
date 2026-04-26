---
type: spec
scope: indexed-config
parent: tech.md
updated: 2026-02-19
status: implemented
---

# Tech Spec: Config & .env Loading Fix

Fixes config resolution and .env loading in the `indexed-config` module. Resolves inconsistencies discovered during real usage.

**For product context (what/why), see [feature-config-product.md](feature-config-product.md).**

---

## Problems Fixed

1. **Config merging bug** — `TomlStore.read()` default branch merged both global + local config.toml. Should resolve to ONE source, never merge.
2. **Missing CWD/.env** — `CWD/.env` was never loaded, only `.indexed/.env` files.
3. **No .gitignore** — Local `.indexed/` directories had no `.gitignore`, risking accidental `.env` commits.
4. **EnvFileWriter path mismatch** — `EnvFileWriter` didn't align with the resolved storage mode, so secrets saved during CLI workflows could go to the wrong `.env`.

---

## Architecture

### Config Resolution (no merging)

The system picks ONE config.toml based on the resolved storage mode. It never merges global + local.

```
                    ┌─────────────────────────┐
                    │  ConfigService.load_raw()│
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  Has mode_override?      │
                    │  (--local / --global)    │
                    └──┬─────────────────┬────┘
                   Yes │                 │ No
                       ▼                 ▼
              ┌────────────┐   ┌──────────────────┐
              │ store.read()│   │ WorkspaceManager  │
              │ (single     │   │ .resolve_storage  │
              │  mode read) │   │  _mode()          │
              └────────────┘   └────────┬─────────┘
                                        │
                               ┌────────▼─────────┐
                               │ store.read_for    │
                               │ _mode(resolved)   │
                               │ (single source)   │
                               └──────────────────┘
```

**Mode resolution order** (in `WorkspaceManager.resolve_storage_mode()`):

| Priority | Source | Example |
|----------|--------|---------|
| 1 (highest) | CLI `mode_override` | `--local` / `--global` flag |
| 2 | Workspace preference | Stored in global config `[workspace].mode` |
| 3 | Auto-detect | Local `.indexed/config.toml` exists → local |
| 4 (lowest) | Default | `"global"` |

### .env Loading Hierarchy

All `.env` files use `load_dotenv(override=False)` — first loaded wins. Real env vars (already in `os.environ`) are never overridden.

```
Priority (highest to lowest):

1. Real os.environ          ← already set before process starts, never touched
2. .indexed/.env            ← from resolved root (local or global), loaded first
3. CWD/.env                 ← workspace root, loaded second, fills gaps only
4. INDEXED__* env mapping   ← applied on top of TOML data (not .env)
```

**Implementation:** `read_for_mode()` calls:
1. `_load_dotenv(resolved_root/.env)` — sets vars not already in real env
2. `_load_cwd_dotenv()` — only fills gaps not covered by step 1 or real env
3. `_env_to_mapping()` — maps `INDEXED__*` env vars into the config dict

### .gitignore Auto-creation

When `ensure_storage_dirs()` creates a local `.indexed/` directory, it also creates `.gitignore` with a `.env` entry. Not applied to `~/.indexed/` (outside git repos).

```python
ensure_storage_dirs(root, is_local=True)
  → _ensure_gitignore(root)
      → creates .gitignore with ".env" if missing
      → appends ".env" if .gitignore exists but lacks it
```

### EnvFileWriter Path Resolution

`EnvFileWriter` receives a callable (`_resolved_env_path`) that resolves the correct `.env` path at write-time based on the effective storage mode. This ensures secrets saved during CLI prompts (e.g., `indexed index create`) go to the right location.

```python
# service.py
self._env_writer = EnvFileWriter(self._resolved_env_path)

def _resolved_env_path(self) -> str:
    mode = self._workspace.resolve_storage_mode()
    return self._store.get_resolved_env_path(mode)
```

---

## Files Changed

| File | What changed |
|------|-------------|
| `indexed_config/storage.py` | `_ensure_gitignore()`, `ensure_storage_dirs(*, is_local)`, `StorageResolver.ensure_dirs()` |
| `indexed_config/store.py` | `read_for_mode()`, `_load_cwd_dotenv()`, `get_resolved_env_path()` |
| `indexed_config/service.py` | `load_raw()` mode resolution, `_resolved_env_path()`, `EnvFileWriter` init |

### Test files

| File | Tests added |
|------|------------|
| `test_toml_store.py` | `TestReadForMode` (7 tests), `TestGetResolvedEnvPath` (2 tests) |
| `test_storage.py` | `TestEnsureGitignore` (5 tests), `ensure_dirs` local/global (2 tests) |
| `test_service.py` | `TestLoadRawModeResolution` (3 tests), `TestResolvedEnvPath` (2 tests) |

---

## Key Design Decisions

### No circular dependencies

`WorkspaceManager.resolve_storage_mode()` creates its own `TomlStore(mode_override="global")` internally to read the workspace preference from global config. `ConfigService.load_raw()` calls `resolve_storage_mode()` and passes the result to `TomlStore.read_for_mode()`. No circular dependency between `TomlStore` and `WorkspaceManager`.

### `read()` preserved for backward compatibility

The existing `TomlStore.read()` (with its merge behavior) is kept unchanged — it's still used by `WorkspaceManager` internally where `mode_override` is always set. The new `read_for_mode()` is the correct path for the main `ConfigService.load_raw()` flow.

### Callable for EnvFileWriter, not a static path

`EnvFileWriter` takes a `Callable[[], str]` rather than a resolved path because the storage mode can depend on runtime state (workspace preference loaded from global config). The callable defers resolution to write-time.

---

## Verification

```bash
uv run ruff check . --fix && uv run ruff format   # All checks passed
uv run pytest tests/unit/indexed_config/ -q -v     # 138 passed
uv run pytest -q                                   # 713 passed
```
