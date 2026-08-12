---
type: feature-tech
feature: workspace-profile
sibling: product.md
parent: ../../tech.md
updated: 2026-08-12
---

# Feature: Workspace Profile — Architecture

Collapses the local/global storage axis to a single global root and introduces a
`WorkspaceProfile` over `./indexed.config.toml`. Config resolution changes from "single
source, no merge" to a **global base + workspace overlay**. A **collection-id allowlist**
threads from the profile through the read paths — applied at the version-dispatching facade
`core/engine.py` so it covers every engine — and CLI/MCP see only the workspace's
collections. The MCP server resolves the workspace **per request** through a documented
chain and reports what it resolved. The profile also contributes one link to the engine-
selection chain for newly created collections.

> **Layout note.** This spec targets the post-Simplify (Feature 14) single package
> `src/indexed/`. The module-edge gate (`scripts/check_imports.py`, four edges) MUST stay
> green: `config` is a leaf — it never imports up into `core`/`cli`/`mcp`. The allowlist and
> the overlay travel *downward* as plain data, so config keeps its leaf position.

> **Upstream gate — Core v2 (PR #162).** This feature is sequenced **after** #162 and its
> code units build on the post-#162 tree. Two consequences run through this document: the
> collection allowlist is applied at the dispatching facade `core/engine.py`, **not** in
> `core/v1/engine/services/*`; and the MCP unit rebases onto #162's `server.py`, `tools.py`,
> `resources.py` and `formatting.py` rather than today's. Both are correctness requirements,
> not merge conveniences — see § Collection filter as an allowlist.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

---

## Files

```
src/indexed/config/
  storage.py            # DELETE StorageMode, StorageResolver, get_local_root,
                        #   has_local/global_storage, _ensure_gitignore, resolve_storage_mode;
                        #   keep plain global-only path helpers
  discovery.py          # NEW: upward profile search (canonical + legacy, $HOME bound)
  workspace.py          # REPLACE WorkspaceManager(mode/preference) → WorkspaceProfile
                        #   + WorkspaceScope (frozen value object) + mtime-keyed cache
  store.py              # read() = global base; drop read_for_mode/mode_override;
                        #   write() → global only; schema_version "2" enforcement
  service.py            # drop mode_override, resolver prop, resolve_storage_mode
  __init__.py           # shrink public exports (remove storage-mode symbols)
  errors.py             # drop StorageConflictError; add SchemaVersionError,
                        #   WorkspaceResolutionError
  cli.py, commands/     # `config workspace init` scaffold; `config inspect` shows scope

src/indexed/core/
  engine.py                           # PR #162's dispatching facade — allowlist applied HERE,
                                      #   in search/status/inspect, BEFORE the per-engine split
  v1/config_models.py                 # get_default_collections_path/caches_path → always global
  v1/engine/services/inspect_service.py  # relative_path anchored to the workspace, not os.getcwd()

src/indexed/cli/
  app.py                # DELETE --local flag + ctx.obj["mode_override"]
  composition.py        # build one WorkspaceScope per invocation; drop mode_override
  init.py               # drop the storage-mode banner
  knowledge/commands/create.py, _create_helpers.py, _create_options.py  # drop --local; add --no-profile
  knowledge/commands/search.py, inspect.py          # apply scope filter + scope note
  knowledge/commands/update.py, remove.py           # warn if out of scope; remove drops entry
  utils/storage_info.py    # DELETE (mode display) — replace with a thin scope note
  utils/conflict_prompt.py # DELETE (storage-conflict prompt no longer reachable)

src/indexed/mcp/
  workspace.py          # NEW: the resolution chain + roots probe + per-request scope cache
  server.py             # lifespan holds env/cwd defaults only — no pinned workspace
  tools.py              # `workspace` argument; pass allowlist; emit `scope` block
  resources.py          # resolve via chain steps 2–5; emit `scope` block
  config.py             # DELETE default_global_context() swallow-all fallback
```

---

## Contract / API

> **Drift corrected.** The previous revision of this spec named `ConfigService.instance()`.
> That method does not exist — the real accessor has been `get_config()` / `reload()` since
> foundation/9 (`config/service.py:367-391`).

```python
# src/indexed/config/discovery.py
CANONICAL_NAME = "indexed.config.toml"
LEGACY_RELPATH = Path(".indexed") / "config.toml"

def find_profile(start: Path) -> tuple[Path, bool] | None:
    """Walk up from `start` to $HOME (inclusive) or the filesystem root.

    Returns (path, is_legacy) for the first hit, or None. The legacy form is
    never matched at $HOME — ~/.indexed/config.toml is the global config.
    """

# src/indexed/config/workspace.py
class WorkspaceProfile:
    """Reader/writer for a workspace profile file."""
    def __init__(self, path: Path, *, is_legacy: bool = False) -> None: ...
    def collection_ids(self) -> list[str]: ...
    def collection_name(self, cid: str) -> str | None: ...
    def overrides(self) -> dict[str, Any]: ...
    def collection_overrides(self, cid: str) -> dict[str, Any]: ...
    def add_collection(self, cid: str, name: str | None = None) -> None: ...   # atomic
    def drop_collection(self, cid: str) -> bool: ...                            # atomic
    @staticmethod
    def scaffold(workspace: Path, *, force: bool = False) -> Path: ...

@dataclass(frozen=True)
class WorkspaceScope:
    """Immutable per-invocation / per-request resolution result."""
    workspace: Path | None
    profile_path: Path | None
    source: Literal["argument", "header", "roots", "env", "cwd", "none"]
    collection_ids: list[str] | None          # None = unfiltered
    overrides: dict[str, Any]
    warnings: list[str]

    def apply(self, config: dict[str, Any]) -> dict[str, Any]:
        """Deep-merge `overrides` onto a config dict. Pure — no shared state."""

def resolve_scope(workspace: Path | None) -> WorkspaceScope: ...   # mtime-keyed cache

# src/indexed/config/service.py  (unchanged accessor, narrowed signature)
def get_config(*, workspace: Path | None = None) -> ConfigService: ...
def reload() -> None: ...

# src/indexed/core/engine.py — PR #162's dispatching facade. The allowlist is appended
# alongside the existing keyword-only `engine`, and applied BEFORE the per-engine split.
def search(query, configs=None, max_chunks=None, max_docs=None, score_threshold=None,
           include_full_text=False, include_all_chunks=False, include_matched_chunks=False,
           collections_path: str | None = None, *,
           engine: str | None = None,
           allowed_collection_ids: list[str] | None = None) -> dict: ...

def status(collection_names=None, *, include_index_size: bool = False,
           collections_path: str | None = None, engine: str | None = None,
           allowed_collection_ids: list[str] | None = None) -> list: ...

def inspect(collection_names=None, *, include_index_size: bool = False,
            collections_path: str | None = None, engine: str | None = None,
            allowed_collection_ids: list[str] | None = None) -> list: ...
```

`allowed_collection_ids=None` means **no filtering** (preserves behaviour when no profile is
present). An empty list means **nothing visible**.

> **Signature hazard.** The facade's leading parameters are *positional*
> (`core/engine.py:508` `search`, `:562` `status`, `:598` `inspect`), exactly as the v1
> wrappers were. Inserting `allowed_collection_ids` mid-signature would silently rebind
> existing positional callers. It MUST be appended after the existing keyword-only `engine`.

> **Do not filter in the v1/v2 services.** The per-engine implementations stay
> filter-agnostic. Filtering there would have to be duplicated per engine and would regress
> the moment a v3 arrives; filtering at the facade covers every engine by construction. See
> § Collection filter as an allowlist.

---

## Implementation Detail

<!-- merge -->
## Storage model: one global root + workspace overlay

There is exactly one storage root: `~/.indexed/`. Collections and caches always live under
`~/.indexed/data/`. The former local root (`./.indexed/data/`), `StorageResolver` mode
resolution, `--local`/`--global` flags, the `[workspace].mode` preference, and the
`.gitignore` guard are removed.

The workspace profile is a single committable file, resolved by walking upward from the
workspace directory:

1. `<dir>/indexed.config.toml` — canonical
2. `<dir>/.indexed/config.toml` — legacy, accepted with a one-time deprecation notice

The walk stops at the first hit, and is bounded by `$HOME` (inclusive) or the filesystem
root. **The legacy form is never matched at `$HOME`**, since `~/.indexed/config.toml` is the
global config. Both forms in one directory → canonical wins, warn once.

The file carries one `[workspace]` section:

- `[workspace.collections.<id>]` — the collection **filter**. `<id>` MUST equal the
  collection's directory name under `~/.indexed/data/collections/`; `name` is a display
  label only.
- `[workspace.overrides.<section>]` — workspace-wide **setting overrides**.

Config resolution is now **global base + workspace overlay** (replacing the old
"single source, no merge"):

```
Pydantic defaults
  → ~/.indexed/config.toml                    (global base)
  → <profile> [workspace.overrides]           (workspace overlay, if present)
  → INDEXED__* env vars
  → CLI args / MCP per-call arguments
```

`config set` writes the global file only. The profile is written by exactly three commands —
`config workspace init`, `index create` (append), and `index remove` (drop) — each through
the same atomic serialize → validate → tmp → `fsync` → `os.replace` path used for
`config.toml`.
<!-- /merge -->

<!-- merge -->
## Collection filter as an allowlist

Read paths take an optional `allowed_collection_ids`. The filter is applied at the
**version-dispatching facade** `core/engine.py` (introduced by Core v2, PR #162), which
resolves the candidate set — explicit names or on-disk enumeration — and groups it per
engine before fanning out. Intersecting with the allowlist there, *before* the per-engine
split, is what makes the filter engine-agnostic.

Applying it inside `core/v1/engine/services/*` instead would be a **silent correctness
hole**: the CLI and MCP call the facade, which routes each collection to v1 or v2 from its
own manifest, so a v1-only filter would leave every v2 collection unfiltered. A workspace
declaring `docs` would still return hits from unrelated v2 collections. The facade is the
only chokepoint both engines pass through.

`engine.search()` and `engine.status()`/`inspect()` already end in `*, engine: str | None =
None`; `allowed_collection_ids` is appended alongside it, keyword-only. The CLI passes the
scope resolved for the invocation; MCP passes the scope resolved for the request. A declared
id with no collection on disk warns and is skipped.

The allowlist filters **discovery**, not authority: naming a collection outside it warns and
proceeds, on CLI and MCP alike. This mirrors MCP's own framing of roots as *"informational
guidance rather than an access-control mechanism"* — the profile is a default-scope filter,
not a boundary.
<!-- /merge -->

<!-- merge -->
## MCP workspace resolution

MCP is stateless as of protocol revision `2026-07-28` (sessions and `Mcp-Session-Id` were
removed, SEP-2567), and one server process may serve several workspaces. The workspace is
therefore resolved **per request**, never pinned at lifespan. First hit wins:

| # | Source | Notes |
|---|---|---|
| 1 | `workspace` tool argument | The spec's own migration target for roots. Tools only — resources take no arguments. |
| 2 | `Indexed-Workspace` HTTP header | http transport only. `get_http_headers()` returns `{}` under stdio and lowercases keys — look up `indexed-workspace`. |
| 3 | Client roots (`ctx.list_roots()`) | Guarded + cached; see below. |
| 4 | `INDEXED_WORKSPACE`, then `CLAUDE_PROJECT_DIR` | Process-wide default. |
| 5 | Process cwd | **stdio only** — for an http daemon, cwd is a silently wrong answer. |

**Why not `INDEXED__workspace`.** `INDEXED__*` names are mapped into the nested config dict,
so `INDEXED__workspace` would set a scalar `workspace` key colliding with the `[workspace]`
table and raise from `_env_to_mapping` (`config/store.py:511`). The env var is deliberately
single-underscore and outside that namespace.

**Roots.** Deprecated as of `2026-07-28` (SEP-2577, earliest removal 2027-07-28), so it is a
best-effort probe rather than the primary path — but it is the only source that reflects a
workspace changing mid-session, and Claude Code implements it well (launch dir plus every
`--add-dir`). It sits behind one function so the eventual MRTR swap is a single edit:

- Guard with `ctx.session.check_client_capability(...)` and `try/except` —
  `Context.list_roots()` does **not** check the capability and raises against clients that
  lack roots.
- Cache the result; invalidate on `notifications/roots/list_changed` while the installed SDK
  speaks `2025-11-25`, and fall back to a short TTL once that notification is gone.
- Multi-root policy: exactly one root → use it; several → use the one containing a profile;
  several *with* profiles → raise, naming the candidates and asking for an explicit
  `workspace` argument. Never silently pick.

**Fail closed.** `mcp/config.py::default_global_context()` currently swallows every exception
and hard-codes a global, unfiltered context — with an allowlist that silently *widens* an
agent's scope, so it is deleted. An explicitly supplied workspace that does not resolve, and
a profile that is found but unparseable, both raise. Only "no explicit source, no profile
found" yields an unfiltered view, and the response says so.

**Self-description.** Every tool and resource response carries a `scope` block —
`{workspace, profile_path, source, collections, warnings}` — so an agent can see the scope it
got instead of inferring it. Out-of-scope named access reports its warning here, since an
agent cannot read stderr.

**Version skew.** The installed stack (fastmcp 3.2.4 / mcp 1.25.0) tops out at protocol
`2025-11-25` and has no `InputRequiredResult`, so classic server-initiated `roots/list` is
what ships. Under `2026-07-28` the probe changes shape to an `InputRequiredResult` the client
retries (MRTR, SEP-2322).
<!-- /merge -->

**Engine selection.** Core v2 (PR #162) resolves the engine for a *new* collection as
`--engine` flag › `INDEXED__CORE__ENGINE` env › `[core] engine` config › built-in default
(v1). The workspace profile contributes to the config link of that chain: because
`[workspace.overrides]` deep-merges onto the global base *below* env and CLI args, setting
`[workspace.overrides.core] engine` lands in exactly the right position with no new
precedence rule — flag and env still win, the profile still beats global config. No change
to #162's resolver is required; it reads the merged config it is already given.

Existing collections are unaffected: the facade routes each one from its own manifest
(`core/versioning.py`), never from config. The profile therefore cannot re-engine or
implicitly migrate a collection, and `#162`'s `EngineMismatchError` still fires on a genuine
conflict.

**Merge semantics.** The overlay is a deep dict merge: workspace tables override matching
global keys; sibling keys are preserved. It is applied through the pure
`WorkspaceScope.apply()` helper, **never** by mutating `ConfigService` — `set_overlay()` is
process-global mutable state and would race between concurrent MCP requests for different
workspaces. The CLI applies it once at composition; MCP applies it per request. Per-collection
overrides (`[workspace.collections.<id>.overrides]`) are applied at the CLI/MCP layer when
building that collection's search config; the engine services stay override-agnostic and only
filter by id. (Resolves the previous revision's Open Question 1.)

**Singleton caveat.** `get_config()` rebuilds its singleton only on a changed `mode_override`
(`config/service.py:379-381`); with that parameter gone it would never rebuild on a changed
`workspace`. This is why the profile is *not* carried in the singleton: `ConfigService`
serves the global base, and `WorkspaceScope` — an immutable value resolved per invocation or
request, cached by `(path, mtime)` — carries everything workspace-specific.

**Path handling.** A `workspace` argument is model-generated and prompt-injectable. Resolve
it with `Path.expanduser().resolve()` (following symlinks), require an existing directory,
and reject the request otherwise. Confinement is deliberately *not* claimed as a security
control: the workspace only selects which profile is read, all collection data is global
either way, and the spec is explicit that roots are not access control. Transport-level
controls (stdio, loopback binding, auth tokens) remain the real boundary.

**Schema version.** `CURRENT_SCHEMA_VERSION` moves to `"2"` and — unlike today, where
`_schema_version` is popped and discarded (`store.py:182`, `service.py:144`) — is actually
enforced: `"2"` passes; `"1"`/absent passes when the file carries none of the removed keys
(`[workspace].mode`, `local_path`, `global_path`) and raises `SchemaVersionError` naming them
when it does; anything else raises. Without this the bump would be decoration.

**`.env`.** With the local root gone, secret resolution is `os.environ` → `~/.indexed/.env` →
`<workspace>/.env`. Note the third is the resolved workspace, not literally the process cwd
(`store.py:196`) — the two differ once MCP resolves a workspace per request.

**Module edges.** `WorkspaceProfile`, `WorkspaceScope`, and the overlay merge live in the
`config` module, which stays a leaf: it exposes scope as data, and the CLI/MCP layers pass the
allowlist *down* into the core read services. No new `config → core`/`config → cli` import,
so `scripts/check_imports.py` stays green. The roots probe lives in `mcp/workspace.py` — it
needs the MCP `Context`, which `config` may not import.

---

## Open Questions

None. Both questions carried by the previous revision are resolved above: per-collection
overrides apply at the CLI/MCP layer (§ Merge semantics), and out-of-scope named access warns
and proceeds everywhere (§ Collection filter as an allowlist).

**Documented follow-up (out of scope here).** `2026-07-28` adds `x-mcp-header` (SEP-2243):
annotating the `workspace` parameter would make conforming clients mirror it as
`Mcp-Param-Workspace`, collapsing chain steps 1 and 2 into one spec-sanctioned mechanism. It
also obliges the server to validate header-against-body equality and reject mismatches with
JSON-RPC `-32020`. The installed SDK cannot exercise either half, so this waits for the SDK
upgrade rather than shipping half-implemented.
