---
type: feature-tech
feature: workspace-profile
sibling: product.md
parent: ../../tech.md
updated: 2026-06-22
---

# Feature: Workspace Profile — Architecture

Collapses the local/global storage axis to a single global root and introduces a
`WorkspaceProfile` over `./.indexed/config.toml`. Config resolution changes from
"single source, no merge" to a **global base + workspace overlay**. A
**collection-id allowlist** threads from the profile through the read paths
(`SearchService`, `InspectService`, and MCP) so search/inspect/MCP see only the
workspace's collections.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

---

## Files

```
packages/indexed-config/src/indexed_config/
  storage.py            # DELETE StorageMode, StorageResolver, get_local_root,
                        #   has_local/global_storage, _ensure_gitignore, is_local;
                        #   keep plain global-only path helpers
  workspace.py          # REPLACE WorkspaceManager(mode/preference) → WorkspaceProfile
                        #   (read/write [workspace]: collection filter + overrides)
  store.py              # read() = global + workspace overlay merge; drop read_for_mode,
                        #   mode_override; write() → global only; schema_version → "2"
  service.py            # drop mode_override, resolver prop, resolve_storage_mode;
                        #   add get_workspace_profile() / collection-filter accessor
  __init__.py           # shrink public exports (remove storage-mode symbols)
  errors.py             # drop/repurpose StorageConflictError

packages/indexed-core/src/core/v1/
  config_models.py      # get_default_collections_path/caches_path → always global
  engine/services/search_service.py   # add allowed_collection_ids filter
  engine/services/inspect_service.py  # add allowed_collection_ids filter

apps/indexed/src/indexed/
  app.py                # DELETE --local flag + ctx.obj["mode_override"]
  knowledge/commands/create.py, _create_helpers.py  # drop --local/mode/explicit paths
  knowledge/commands/search.py, inspect.py          # apply workspace filter
  knowledge/commands/update.py, remove.py           # warn if name out of profile
  config/cli.py         # repurpose `config init` → profile scaffold; inspect shows profile
  utils/storage_info.py # DELETE (mode display) — replace with a thin scope note
  utils/conflict_prompt.py # DELETE (storage-conflict prompt no longer reachable)
  mcp/server.py         # load collection filter into lifespan context
  mcp/tools.py          # pass allowlist to svc_search; validate named access
  mcp/resources.py      # pass allowlist to svc_status; validate named access
```

---

## Contract / API

```python
# packages/indexed-config/src/indexed_config/workspace.py
class WorkspaceProfile:
    """Reader/writer for ./.indexed/config.toml [workspace] section."""
    def __init__(self, workspace: Path | None = None) -> None: ...
    def exists(self) -> bool: ...
    def collection_ids(self) -> list[str] | None:        # None = no filter
        ...
    def collection_name(self, cid: str) -> str | None: ...
    def overrides(self) -> dict[str, Any]:               # [workspace.overrides]
        ...
    def collection_overrides(self, cid: str) -> dict[str, Any]: ...
    def scaffold(self, *, force: bool = False) -> Path:  # write skeleton
        ...

# packages/indexed-config/src/indexed_config/service.py
class ConfigService:
    @classmethod
    def instance(cls, workspace: Path | None = None) -> "ConfigService": ...  # no mode_override
    def get_workspace_profile(self) -> WorkspaceProfile: ...
    def collection_filter(self) -> list[str] | None: ...  # convenience → profile.collection_ids()

# packages/indexed-core/.../search_service.py  (and functional wrapper)
def search(query, *, configs=None,
           allowed_collection_ids: list[str] | None = None,  # NEW
           max_docs=None, max_chunks=None, ...,
           collections_path: str | None = None) -> dict: ...

# packages/indexed-core/.../inspect_service.py  (status + inspect, and wrappers)
def status(collection_names=None, *,
           allowed_collection_ids: list[str] | None = None,  # NEW
           include_index_size=False, ...) -> list[CollectionStatus]: ...
```

`allowed_collection_ids=None` means **no filtering** (preserves behaviour when no
profile is present). An empty list means **nothing visible**.

---

## Implementation Detail

<!-- merge -->
## Storage model: one global root + workspace overlay

There is exactly one storage root: `~/.indexed/`. Collections and caches always
live under `~/.indexed/data/`. The former local root (`./.indexed/data/`),
`StorageResolver` mode resolution, `--local`/`--global` flags, the `[workspace].mode`
preference, and the `.gitignore` guard are removed.

`./.indexed/config.toml` is repurposed as a **workspace profile** with a single
`[workspace]` section:

- `[workspace.collections.<id>]` — the collection **filter**; each entry carries a
  display `name` and optional `[...overrides]`.
- `[workspace.overrides.<section>]` — workspace-wide **setting overrides**.

Config resolution is now **global base + workspace overlay** (replacing the old
"single source, no merge"):

```
Pydantic defaults
  → ~/.indexed/config.toml            (global base)
  → ./.indexed/config.toml [workspace.overrides]   (workspace overlay, if present)
  → INDEXED__* env vars
  → CLI args
```

Writes always target the global config; the profile is hand-edited or scaffolded,
never written to by `config set`.
<!-- /merge -->

<!-- merge -->
## Collection filter as an allowlist

Read paths take an optional `allowed_collection_ids`. `SearchService` and
`InspectService` resolve their candidate set (explicit names or auto-discovery),
then intersect with the allowlist when it is non-None. The CLI passes
`ConfigService.instance().collection_filter()`; the MCP server loads the same list
into its lifespan context and tools/resources read it from there. Named MCP access
to a collection outside the allowlist returns an access error rather than silently
widening scope.
<!-- /merge -->

**Merge semantics.** The overlay is a deep dict merge: workspace tables override
matching global keys; sibling keys are preserved. Per-collection overrides
(`[workspace.collections.<id>.overrides]`) are applied only when operating on that
collection (e.g. search config for that collection's searcher).

**Schema version.** Global and profile files carry `[_meta] schema_version = "2"`.
The bump marks the dropped `[workspace].mode`/`local_path`/`global_path` keys and
the new `[workspace.collections|overrides]` shape. Clean break — no migration of
old local stores (alpha).

**`.env`.** With the local root gone, secret resolution is `os.environ` →
`~/.indexed/.env` → `CWD/.env` (the old `./.indexed/.env` root is dropped; project
secrets use `CWD/.env`).

---

## Open Questions

1. **Per-collection override application point.** — Cleanest is to apply
   `collection_overrides(cid)` when building that collection's search config in the
   CLI/MCP layer (services stay override-agnostic, just filtering by id). Confirm
   during search/2 rather than threading overrides into the engine.
