---
type: feature-tech
feature: foundation
sibling: product.md
parent: ../../tech.md
updated: 2026-07-06
---

# Feature: Foundation — Config, CLI & MCP Architecture

Detail file for the **top of the stack**: the `indexed-config` package and the
`apps/indexed` CLI/MCP layer. It makes configuration **read-mostly** (runtime
flows stop writing `config.toml`), consolidates the triplicated path/mode logic
and the two competing singletons into one cached `get_config()`, collapses the
three wiring modules (`bootstrap.py` + `connector_wiring.py` + `runtime.py`)
into a single `composition.py`, and fixes every audited CLI/MCP correctness
defect (dead exit codes, Rich markup crashes, hour-stale MCP cache,
mis-registered config sections). All work lands in the **current 7-package
layout**; the workspace collapse is the `simplify` feature.

**Overview:** [tech.md](tech.md)
**Requirements:** [product.md](product.md)

---

## Files

```
packages/indexed-config/src/indexed_config/
  service.py         ConfigService singleton — replace with cached get_config()/reload()   ~300→~150
  store.py           TomlStore — atomic write; fold path/mode logic here or into storage    ~399
  storage.py         StorageResolver + module fns — the ONE home for path/mode              ~396
  workspace.py       WorkspaceManager — merge into the single resolver                       ~141
  provider.py        Provider / bind() — DELETE (connectors validate own section)            ~79
  registry.py        ConfigRegistry — DELETE (no second consumer)                            ~30
  env_writer.py      EnvFileWriter — quoting + broaden sensitive routing                     ~66
  path_utils.py      get/set/delete_by_path, deep_merge — keep                               ~101
  errors.py          IndexedError hierarchy — keep; drop missing_wiring_error after R2       ~36

apps/indexed/src/indexed/
  app.py             Typer entry — sys.exit(exit_code_for(exc)); no typer.Exit outside runner  ~376
  bootstrap.py       register_app_config + build_connector — FOLD into composition.py          ~68
  connector_wiring.py  _populate_* + private reaches + os.environ side-channel — DELETE         ~260
  runtime.py         CliContext + resolve_collections_context — FOLD into composition.py        ~40
  composition.py     NEW single wiring point (registry build, from_manifest, 2 callables)       ~120
  errors.py          exit-code table (wire it up), mcp_error_envelope                          ~34
  config/cli.py      config get/set/inspect: mask secrets, stop echo, route to .env           ~1959
  knowledge/commands/  search/update/inspect/remove/_create_helpers — honest failures, markup
  mcp/server.py      scope/invalidate ResponseCachingMiddleware; drop double register           ~60
  mcp/tools.py mcp/resources.py  except Exception envelope; core raises IndexedError            ~128/98
  mcp/formatting.py  surface per-collection errors instead of continue                          ~77
```

---

## Contract / API

### `get_config()` / `reload()` — cached, read-mostly (R3)

Replaces `ConfigService.instance()` (the conditional-self-replacement singleton
at `service.py:63-81`) and the *second* module-level singleton in
`core.v1.engine.services.search_service` (`search_service.py:301`, per
research §9). One cached snapshot per process; explicit `reload()` for tests.

```python
# indexed_config/__init__.py  (target)
@dataclass(frozen=True)
class ResolvedConfig:
    mode: StorageMode                 # "global" | "local"
    paths: StoragePaths               # collections / caches / config / env
    raw: dict[str, Any]               # merged config.toml + .env + INDEXED__*
    def with_overrides(self, overrides: dict[str, Any]) -> "ResolvedConfig": ...
    def get(self, dot_path: str, default=None) -> Any: ...

def get_config(*, mode_override: StorageMode | None = None) -> ResolvedConfig: ...  # cached
def reload() -> None: ...                                                            # clears cache
def set_value(dot_path: str, value: Any, *, sensitive: bool = False) -> None: ...    # ONLY writer
```

`with_overrides` returns a new snapshot with an **in-memory overlay** merged on
top of `raw` (via `deep_merge`, `path_utils.py:83`) — it never touches disk.
This is what create/update/search consume instead of calling `ConfigService.set`
mid-run.

### Composition module (R2) — replaces 3 modules

```python
# indexed/composition.py  (target shape)
@dataclass(frozen=True)
class AppContext:
    cfg: ResolvedConfig
    registry: dict[str, type[BaseConnector]]   # built lazily, not at import

def build_context(mode_override: str | None = None,
                  overrides: dict | None = None) -> AppContext: ...

def create_connector_factory(ctx: AppContext) -> Callable[[SourceConfig], BaseConnector]:
    return lambda cfg: ctx.registry[cfg.type].from_config(ctx.cfg.with_overrides(_overrides_for(cfg)))

def manifest_connector_factory(ctx: AppContext) -> Callable[[Manifest], ConnectorBundle]:
    return lambda m: ctx.registry[m.reader.type].from_manifest(m, ctx.cfg)
```

Two **required** callables handed to the core facade (create-time,
update-time). No `Callable | None`, no `missing_wiring_error` (`errors.py:31`).
Per-connector `from_manifest(manifest, cfg) -> (reader, converter, deletions,
post_run)` replaces the four `_populate_*` blocks, the private-attribute reaches
(`connector_wiring.py:227-231`: `connector._config/._path/._include_patterns`),
and the `os.environ` side-channel (`connector_wiring.py:164`).

---

## Implementation Detail

### 1. Read-mostly config (R3) — stop writing `config.toml` at runtime

Today three runtime paths persist to disk during create/update:

- `bootstrap.build_connector` (`bootstrap.py:59-65`) writes CLI args:
  ```python
  if cfg.base_url_or_path:
      if cfg.type == "localFiles":
          config_service.set(f"{namespace}.path", cfg.base_url_or_path)   # ← writes TOML
      else:
          config_service.set(f"{namespace}.url", cfg.base_url_or_path)
  if cfg.query:
      config_service.set(f"{namespace}.query", cfg.query)                 # ← writes TOML
  ```
- `connector_wiring._populate_jira_config` etc. (`connector_wiring.py:43-121`)
  write **date-stamped derived JQL/CQL** into the user's config on every update:
  ```python
  query_addition = f'AND (created >= "{update_date}" OR updated >= "{update_date}")'
  config_service.set(f"{namespace}.query", f"{reader_config['query']} {query_addition}")
  ```
- `_create_helpers.execute_create_command` (`_create_helpers.py:142`) persists
  CLI overrides + prompted values **before** create succeeds:
  ```python
  for key, value in cli_overrides.items():
      config.set_value(f"{namespace}.{key}", value, field_info=field_info)   # ← persists
  ```

Every `ConfigService.set` (`service.py:183-187`) is a load→mutate→`save_raw`
round-trip; research §"Performance" measured update doing up to 8 sequential
read-parse-write cycles.

**After:** these become in-memory overlays. The connector factory builds the
overlay dict and calls `from_config(cfg.with_overrides(overlay))`; nothing hits
disk. `set_value()` (backing only `indexed config set`) is the single writer.

```python
# before (bootstrap.build_connector)
config_service.set(f"{namespace}.url", cfg.base_url_or_path)
return cls.from_config(config_service)

# after (composition.create_connector_factory)
overlay = {namespace: {"url": cfg.base_url_or_path, "query": cfg.query}}
return cls.from_config(ctx.cfg.with_overrides(overlay))
```

### 2. Atomic `config.toml` write — kill `config set … null` zeroing (R3/R5)

`TomlStore.write` (`store.py:322-359`) opens the real file `"w"` (truncate)
**then** dumps — so if the value is unserializable, the file is already empty.
Reproduced: `config set <key> null` maps to `None` (`config/cli.py:114` via
`_coerce_value` + JSON `null`), `tomlkit.dump({...None...})` raises, and
`config.toml` (credential pointers included) is left 0 bytes.

```python
# before (store.py:358)
with open(target, "w", encoding="utf-8") as f:   # truncates FIRST
    tomlkit.dump(out, f)                          # may raise AFTER truncation

# after — serialize to a string first, reject bad values, then atomic replace
text = tomlkit.dumps(out)                         # raises here, file untouched
tmp = target.with_suffix(f".toml.tmp-{os.getpid()}")
tmp.write_text(text, encoding="utf-8")
os.fsync(...)                                     # same tmp→fsync→rename the collection persister already uses
os.replace(tmp, target)
```

Mirror `disk_persister.py`'s proven tmp→fsync→`os.replace`. `config set null`
should either delete the key or error with a non-zero exit — never truncate.

### 3. One home for path/mode (R3)

Path/mode logic is triplicated (research §9): `TomlStore.has_local_config`
(`store.py:195`) vs `storage.has_local_config` (`storage.py:140`) vs
`StorageResolver.resolve_root` (`storage.py:264`) vs
`WorkspaceManager.resolve_storage_mode` (`workspace.py:106`) — the same
CLI-override → workspace-pref → auto-detect → global cascade written four times,
plus `TomlStore._env_path` (`store.py:88-97`) re-deriving it a fifth time.
Collapse to one resolver used everywhere; delete `WorkspaceManager` and the
`ConfigService`↔`TomlStore`↔`StorageResolver` fan-out (`service.py:49-59`).

Delete `Provider`/`registry.py`/`bind()`: `bind()` (`service.py:150-175`) and
`Provider.get` (`provider.py:30`) exist only so the app can validate sections it
already knows the type of. Connectors validate their own section in
`from_config`; the MCP `_get_config` fallback (`server.py:31-37`) becomes a
direct `Model.model_validate(cfg.get(path, {}))`.

### 4. Secret handling (R3 secret + R6 crossover, foundation/4)

`_is_sensitive_key` (`config/cli.py:194-208`) and
`EnvFileWriter.is_sensitive_field` (`env_writer.py:47-51`) exist but the `set`
path never applies them:

- `set_config` (`config/cli.py:1464-1568`) calls `config.set(key, coerced)`
  (`:1533`) — plaintext to TOML — then echoes the value in the change-summary
  card (`:1521`, `:1557` via `_format_config_value`). Route sensitive keys to
  `.env` via `set_value(..., sensitive=_is_sensitive_key(key))` and render
  `••••••` in the card.
- `config inspect` prints secrets unmasked (`config/cli.py:1020` feeds
  `info["value"]` straight to `_format_config_value`); apply `_is_sensitive_key`
  before formatting each Sources/Core row.
- `ConfigService.set_value` (`service.py:268-283`) already routes when
  `field_info["sensitive"]` — but `set_config` never passes `field_info`. Fix at
  the call site.
- Stop baking `INDEXED__*` env overrides into TOML: `load_raw` merges env
  (`store.py:163-171` `_apply_env_and_finalize`), so any later `set` round-trips
  env-supplied secrets into `save_raw` (research §11, `service.py:183`). `set`
  must write only the changed key, not the whole merged dict.
- `.env` quoting: `EnvFileWriter.write` (`env_writer.py:20-45`) writes
  `KEY=value` raw; tokens with ` #` truncate or `${…}` interpolate on the next
  `load_dotenv`. Quote values.

### 5. Honest failure behavior (R7)

**Exit codes are dead** (`app.py:365-371`): the handler runs *outside* the click
runner, so `raise typer.Exit(...)` after `app()` returns produces a traceback +
exit 1, and the `EXIT_CODES` table (`errors.py:7-10`, 2=config, 3=storage) is
never consulted.

```python
# before (app.py:371)
except IndexedError as exc:
    _shared_console.print(format_cli_error(exc), style=get_error_style())
    raise typer.Exit(exit_code_for(exc)) from None    # traceback, ignores table

# after
except IndexedError as exc:
    _shared_console.print(format_cli_error(exc), style=get_error_style())
    sys.exit(exit_code_for(exc))
```

**MCP swallows real failures.** `tools.py:45` and `resources.py:57,75,96` catch
only `IndexedError`, but core raises none for missing collection / corrupt
manifest → the envelope is unreachable and an uncaught error propagates as an
MCP protocol error. Two-part fix: core raises `IndexedError` subclasses for
expected failures; the MCP boundary catches broad `Exception`:

```python
# before (tools.py:45)
except IndexedError as e:
    return mcp_error_envelope(e)
# after
except Exception as e:                 # envelope any expected failure
    return mcp_error_envelope(e)
```

**InspectService zero-fills missing collections** so guards never fire
(research §22, `inspect_service.py:204-220`). Downstream:

- `search.py:423` — `indexer=coll_status.indexers[0]` raises raw `IndexError`
  for a nonexistent `-c` collection (even under `--simple-output`). Once
  `status`/`inspect` **omit** missing collections, `if not statuses` at
  `search.py:405` fires and errors with exit 1.
- `update.py` — a missing/failed collection currently `continue`s or the loop
  `break`s (`update.py:366,414`) while returning **exit 0**. Make the update
  loop not abort on the first failure, collect per-collection errors, and
  `raise typer.Exit(1)` if any failed. (`update_error`/`break` at `:365-366`
  must not swallow the exit code.)
- Default `search` across collections must not crash wholesale when one
  manifest is corrupt — per-collection try/except, surface the bad one.

**Rich markup crashes on user/content strings** (research §23). Query and
*indexed document content* are interpolated into markup f-strings:
`search.py:400` (query in headline), `search.py:184-187` (excerpt panel),
`search.py:211-214` (`_show_compact_match` doc_id/collection),
`cards.py:38`, and the error print at `app.py:370`. Content containing `[/...]`
raises `MarkupError`; `arr[i]`/`dict[key]` is silently swallowed — the common
case for a code-search tool. Fix: `rich.markup.escape()` (or `Text`/
`markup=False`) on every user/content string before it enters a styled string.

```python
# before (search.py:400)
console.print(f'\n[{get_heading_style()}]Searching for [{get_accent_style()}]"{query}"...')
# after
from rich.markup import escape
console.print(f'\n[{get_heading_style()}]Searching for [{get_accent_style()}]"{escape(query)}"...')
```

**Logger reset to WARNING** (research §24). Every knowledge command calls
`setup_root_logger(level_str=effective_level, ...)`; the shim at
`logger.py:361` reduces `None`→`bootstrap_logging("WARNING")`, clobbering the
`--verbose`/`--log-level`/`INDEXED_LOG_LEVEL` resolved in the app callback
(`app.py:121-141`) and dropping the themed console + file log. The command-level
`setup_root_logger(None)` must not downgrade a level already set by the
callback; and note per root `AGENTS.md`, `is_verbose_mode()` is unreliable at
command entry because logger setup runs *inside* the command, not at the
callback.

**`--local` flag parity.** `app.py:73-78` defines `--local` on the root
callback and stores `mode_override` on `ctx.obj`, and `create` re-accepts a
`local` kwarg (`_create_helpers.py:90-103`), but `search`/`update`/`inspect`/
`remove` only read `ctx.obj["mode_override"]` and expose no `--local` of their
own (research §33). Either surface `--local` on each or document that the root
flag (`indexed --local search …`) is the only form — but make it consistent.

### 6. MCP specifics (R7)

**Response caching serves hour-stale results.** `server.py:56`
`mcp.add_middleware(ResponseCachingMiddleware())` uses FastMCP defaults (~1h
TTL) with no invalidation on CLI re-index, and it caches error envelopes too
(research §17). Remove it, or scope it to genuinely static resources with a
short TTL, and invalidate on any collection mutation. A search tool must reflect
the latest index.

**Per-collection errors silently swallowed** (`formatting.py:27`):

```python
# before
for collection_name, collection_data in raw_results.items():
    if isinstance(collection_data, dict) and "error" in collection_data:
        continue                          # agent sees "0 matches", not "index failed"
# after
        errors.append({"collection": collection_name, "error": collection_data["error"]})
        continue
# … and include `formatted["collection_errors"] = errors` in the payload
```

The CLI formatters have the identical bug (`search.py:77`, `:222`, `:269` all
`if "error" in collection_results: continue`) — surface them there too.

**`collections_path` defeats the searcher cache.** MCP tools/resources pass
`collections_path=str(cli_ctx.collections_path)` on every call
(`tools.py:43,94`; `resources.py:56,72,90`). Because the core `SearchService`
caches searchers but the collections_path is re-resolved per request via
`resolve_collections_context()` (`config.py:36` fallback builds a fresh
`CliContext` and eagerly re-imports all connectors, ~0.4s — research
§"Performance"), the cache is bypassed. Resolve the context once in the
lifespan (`server.py:45` already does) and reuse it; don't rebuild per request.

### 7. Config-section truth (R7)

**`core.v1.storage` registered under the wrong path.** `register_app_config`
registers `CoreV1StorageConfig` at `core.v1.vector_store`
(`bootstrap.py:28`), but the CLI defaults template and `config set` write/read
`core.v1.storage` (`config/cli.py:295-302`). So any `config set
core.v1.storage.*` is silently ignored by the reader. Pick one path (align both
to `core.v1.storage`) and register/read/template consistently.

**Dead indexing/embedding sections & batch mismatch** (research §20):
`core.v1.indexing` / `core.v1.embedding` are registered
(`bootstrap.py:26,29`), settable, and templated (`config/cli.py:287-288`) but
read nowhere — the model comes from the indexer name, and batch size is
hardcoded 64 in the embedder while config default is 128. Either wire these into
the engine (foundation/2 owns the embedder token/batch work) or delete the dead
sections so the CLI never offers a no-op knob.

**CLI ignores `[core.v1.search]`.** `search.py` hardcodes `max_docs=limit`,
`max_chunks=limit*3` (`search.py:437-438,456-457`) and never reads
`CoreV1SearchConfig`, while MCP *does* (`tools.py:38-42`, `server.py:47`). Same
query returns different results by surface. CLI search must load
`cfg.get("core.v1.search")` (through the read-mostly snapshot) so both surfaces
honor the same `max_docs`/`max_chunks`/`score_threshold`.

<!-- merge -->
## Architectural rules (config + app)

- **`config.toml` is user-owned.** Runtime flows (create/update/search) read a
  cached `get_config()` snapshot and apply in-memory `with_overrides`; only
  `indexed config set` persists, atomically (tmp→fsync→rename), routing secrets
  to `.env` and never echoing them.
- **One resolver** owns path/mode resolution (CLI override → workspace pref →
  local `./.indexed/config.toml` present → global). No duplicate cascades.
- **`composition.py` is the single wiring point** for the app: it builds the
  connector registry lazily and hands the core facade two required callables.
  `bootstrap.py`, `connector_wiring.py`, `runtime.py` are gone.
- **Fail loud:** missing/corrupt collections raise `IndexedError` in core →
  non-zero CLI exit via `exit_code_for` + broad-`Exception` MCP envelope. No
  tracebacks, no success exits on failure, no hour-stale MCP results.
- Every settable config section is actually read; user/content strings are
  Rich-escaped before display.
<!-- /merge -->

## Open Questions

1. **Delete vs error on `config set … null`.** Deleting the key is friendlier;
   erroring is safer against typos. Atomic write makes either safe — pick one
   and document it in `config inspect` help.
2. **Keep any response caching on MCP?** A short-TTL cache on the static
   `resource://collections` list is cheap and safe; search must never cache.
   Decide whether to keep a scoped middleware or drop it entirely.
