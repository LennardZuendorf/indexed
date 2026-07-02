---
type: feature-research
feature: architecture-audit
cluster: app
parent: ../product.md
updated: 2026-06-29
---

# App Cluster Research — CLI + MCP

Audit of `apps/indexed` conducted 2026-06-29. Covers the Typer CLI entry
(`app.py`, command groups) and embedded FastMCP server (`mcp/`). Cross-refs:
[tech-app.md](../../../tech-app.md), [issue #119](https://github.com/LennardZuendorf/indexed/issues/119).

---

## Summary

The app layer violates its own thin-command contract. Three command files exceed
the 150-line limit by 3–13×; `config/cli.py` is nearly 2 000 lines. Storage-mode
resolution is inconsistent: the global `--local` flag is stored on `ctx.obj` but
most commands never pass it to `ConfigService`, while search/inspect use a
separate heuristic (`resolve_preferred_collections_path`) that diverges from the
spec precedence chain. MCP reuses core services but omits `collections_path`,
ignores `MCPConfig` transport settings at runtime, and swallows errors into dicts
instead of the `IndexedError` hierarchy. CLI and MCP duplicate search orchestration
with no shared facade. Refactoring should be phased: fix correctness bugs (P0)
before structural extraction (P1–P3).

---

## CLI Architecture Findings

### File sizes

| File | Lines | Limit (tech-app.md) | Ratio |
|------|------:|--------------------:|------:|
| `config/cli.py` | 1 959 | 150 | 13× |
| `knowledge/commands/create.py` | 967 | 150 | 6.4× |
| `knowledge/commands/search.py` | 501 | 150 | 3.3× |
| `knowledge/commands/update.py` | 501 | 150 | 3.3× |
| `app.py` | 360 | — | entry OK |
| `knowledge/cli.py` | 47 | 150 | ✓ |

`create.py` is a monolith of hardcoded connector subcommands (files, jira-cloud,
jira-server, confluence-*, outline-*) with inline credential prompts, validation,
and progress display. `search.py` embeds ~300 lines of Rich formatters that were
previously a separate module. `config/cli.py` mixes inspect/set/validate/delete,
interactive TUI flows, merge logic, and raw TOML manipulation.

### Global `--local` broken (`ctx.obj` display-only)

`app.py` callback stores `ctx.obj["mode_override"] = "local" if local else None`
and calls `ensure_storage_dirs` when `--local` is set, but subcommands do not
consistently propagate this to `ConfigService`:

- **create** — `_create_helpers.py` passes `mode_override` only from the
  per-command `--local` flag, not from the global callback.
- **search / inspect / update / remove** — call `ConfigService.instance()` with
  no `mode_override`.
- **display only** — `display_storage_mode_for_command()` reads `ctx.obj` for the
  reason string but `ConfigService.resolve_storage_mode()` was already initialized
  without the override.

**Effect:** `indexed --local search "…"` may show "via --local flag" in the
storage indicator while actually searching global collections (or vice versa via
the heuristic below).

### `resolve_preferred_collections_path` heuristic vs spec

Spec precedence ([tech-app.md § Storage Mode Resolution](../../../tech-app.md)):

1. CLI `--local` / `--global`
2. `storage.mode` in config.toml
3. `./.indexed/` present → local
4. Global fallback

`resolve_preferred_collections_path()` (`utils/storage_info.py`) instead:

1. If `./.indexed/data/collections/` exists **and is non-empty** → local
2. Else `ConfigService.instance().resolver.get_collections_path()` (global default)

Gaps:

- Ignores `ctx.obj["mode_override"]` entirely.
- Requires non-empty collections dir, not merely `./.indexed/` presence.
- Used by `search.py` and `inspect.py` for all `collections_path=` kwargs to
  `svc_search` / `status`, bypassing single-source config resolution.

### Eager command imports hurt startup

Despite lazy `__getattr__` on `app.py` for test exports, module-level wiring
defeats it:

```python
# app.py:154
from . import config, info, knowledge, mcp
```

`knowledge/commands/__init__.py` eagerly imports all five command modules.
`create.py` imports `ConfigService`, `loguru`, and connector schemas at top level.
Every CLI invocation pays the import cost of the largest command files even for
`indexed config inspect` or `indexed mcp inspect`.

### Formatters embedded in commands

`search.py` lines 45–280 host `format_search_results`, compact variants, and
Rich card layout — UI logic mixed with orchestration. `search.py` also imports
`format_search_results_for_llm` from `mcp/formatting.py` for `--simple-output`,
creating a circular dependency direction (CLI → MCP formatting). Formatters belong
in `utils/` or a dedicated `knowledge/formatters/` package.

### Private core / config APIs used from CLI

| Call site | Private API | Risk |
|-----------|-------------|------|
| `_create_helpers.py:163` | `collection_service._collection_exists` | breaks on rename/refactor |
| `config/cli.py:1300,1367` | `config._store._read_toml_file` | bypasses store abstraction |

These should be replaced with public methods on `ConfigService` / collection
service before v2.

---

## MCP Findings

### No `collections_path` passed

`mcp/tools.py` calls `svc_search()` and `svc_status()` without
`collections_path=`. Resolution falls through to `ConfigService` defaults, which
use cwd-based global/local logic — but MCP has no equivalent of `--local` and no
access to `resolve_preferred_collections_path`. An agent connected via stdio from
a workspace with local collections may see different results than
`indexed search` in the same directory.

### `IndexedError` unused; bare `Exception` → error dict

`errors.py` defines `CLIError` and `MCPError` extending `IndexedError`, but
`tools.py` and `resources.py` catch bare `Exception` and return
`{"error": str(e)}`. Failures are silent to log consumers; no structured error
codes; tests cannot assert on exception types.

### `MCPConfig` TOML ignored by `run_impl`

`MCPConfig` (`core/v1/config_models.py`) defines `host`, `port`, `log_level`,
`include_index_size`. Server lifespan loads it for resources, but `mcp/cli.py`
`run_impl()` uses hardcoded Typer defaults (`host=127.0.0.1`, `port=8000`,
`log_level=INFO`) and never reads TOML. Users setting `[mcp] port = 9000` see no
effect unless they pass CLI flags.

### `search_collection` hardcodes `localFiles`

```python
source_config = SourceConfig(
    name=collection,
    type="localFiles",  # always
    base_url_or_path="",
    indexer=default_indexer,
)
```

Jira/Confluence/Outline collections are searched with wrong source metadata.
CLI `search.py` has the same hardcode (line 425) — shared bug, not MCP-only.

### Tools vs spec drift (resources vs tools)

| Surface | Spec ([tech-app.md](../../../tech-app.md)) | Actual |
|---------|---------------------------------------------|--------|
| Tools | `search`, `list_collections`, `collection_status` | `search`, `search_collection` |
| Resources | `resource://collections/{name}` | `resource://collection/{name}` (singular) |
| Status tool | dedicated `collection_status(name)` tool | status via resources only |

Resource URI change was intentional (FastMCP v3 dispatch collision — see
`resources.py` header comment) but spec was not updated. Missing
`list_collections` tool forces agents to use resources for discovery.

---

## CLI/MCP DRY Gaps

### `search_facade` needed

Both CLI `search.py` and MCP `tools.py` independently:

1. Resolve collections to search
2. Build `SourceConfig` per collection (with hardcoded `localFiles`)
3. Call `svc_search()` with overlapping kwargs
4. Format results (Rich vs LLM dict)

Extract to `knowledge/services/search_facade.py` (~80 lines): accept query,
optional collection filter, `collections_path`, search config; return raw results.
CLI and MCP each own one formatting path.

### `bootstrap.py` for config registration

Config model registration is scattered:

- `mcp/server.py` registers `MCPConfig`, `CoreV1SearchConfig` in lifespan
- Commands call `ConfigService.instance()` and register ad hoc
- No single place listing all models the app needs

A `indexed/bootstrap.py` (or `knowledge/bootstrap.py`) should register all app
config sections once, accept `mode_override`, and return a bound provider.

### Shared `resolve_collections_context`

Unify storage resolution for CLI and MCP:

```python
@dataclass
class CollectionsContext:
    mode: StorageMode
    collections_path: Path
    reason: str

def resolve_collections_context(
    mode_override: str | None = None,
    workspace: Path | None = None,
) -> CollectionsContext: ...
```

Replace `resolve_preferred_collections_path`, wire global `--local` through
`ConfigService.instance(mode_override=…)`, and pass result to all service calls.

---

## Refactoring Proposals (Phased)

### Phase 0 — Correctness (no file moves)

1. Wire `ctx.obj["mode_override"]` into every command's `ConfigService.instance(mode_override=…)`.
2. Replace `resolve_preferred_collections_path` with `resolve_collections_context` using spec precedence.
3. Pass `collections_path` from context to all `svc_search` / `status` / MCP tool calls.
4. Read `MCPConfig` host/port/log_level in `run_impl` when CLI flags not set.
5. Use manifest `source_type` when building `SourceConfig` (fix `localFiles` hardcode).

### Phase 1 — Extract services (issue #119 scope)

1. Create `knowledge/services/search_facade.py`, `create_facade.py` (thin wrappers).
2. Move formatters out of `search.py` → `utils/` or `knowledge/formatters/`.
3. Split `create.py` by connector into `commands/create/files.py`, `jira.py`, etc.
4. Add public `collection_exists()` to core; remove `_collection_exists` import.

### Phase 2 — Config + bootstrap

1. Add `bootstrap.py` with centralized config registration.
2. Replace `config._store._read_toml_file` with public store API.
3. Decompose `config/cli.py` into commands + `config/services/`.

### Phase 3 — MCP alignment + perf

1. Align MCP tools with spec: add `list_collections`, rename or alias resources.
2. Raise `MCPError` subclasses; map to error dict only at FastMCP boundary.
3. Lazy-import command modules in `app.py` (register commands via callback or
   `importlib` on first use).
4. Update [tech-app.md](../../../tech-app.md) MCP section to match shipped surface.

---

## Priority Table

| ID | Item | Severity | Effort | Phase |
|----|------|----------|--------|-------|
| **P0** | Global `--local` not applied to `ConfigService` | Bug — wrong data path | S | 0 |
| **P0** | `resolve_preferred_collections_path` diverges from spec | Bug — inconsistent search scope | S | 0 |
| **P0** | MCP omits `collections_path` | Bug — CLI/MCP result mismatch | S | 0 |
| **P0** | `SourceConfig.type="localFiles"` hardcoded | Bug — wrong metadata for remote sources | S | 0 |
| **P1** | `MCPConfig` TOML ignored by `run_impl` | Config drift | S | 0 |
| **P1** | Extract `search_facade` + shared collections context | DRY / maintainability | M | 0–1 |
| **P1** | `config/cli.py` 1 959 lines | Unmaintainable | L | 2 |
| **P1** | `create.py` 967 lines | Unmaintainable | L | 1 |
| **P2** | Formatters embedded in `search.py` | Layer violation | M | 1 |
| **P2** | Private API usage (`_collection_exists`, `_read_toml_file`) | Fragile coupling | S | 1–2 |
| **P2** | MCP tools vs spec drift | Agent integration confusion | M | 3 |
| **P2** | Bare `Exception` → error dict in MCP | Poor observability | S | 3 |
| **P3** | Eager command imports | Startup regression risk | M | 3 |
| **P3** | `IndexedError` hierarchy unused in MCP | Consistency | S | 3 |
| **P3** | Update tech-app.md MCP examples | Spec drift | S | 3 |

Severity: **Bug** = wrong behavior today; **Config drift** = user settings ignored;
**Layer violation** = UI logic in command layer; **Unmaintainable** = blocks
future changes. Effort: S ≤ 1 day, M ≤ 3 days, L > 3 days.

---

## Evidence Paths

```
apps/indexed/src/indexed/
  app.py                          # ctx.obj mode_override, eager imports
  config/cli.py                   # 1959L, _read_toml_file
  knowledge/commands/create.py    # 967L
  knowledge/commands/search.py    # 501L, formatters, heuristic path
  knowledge/commands/update.py    # 501L
  knowledge/commands/_create_helpers.py  # _collection_exists
  utils/storage_info.py           # resolve_preferred_collections_path
  mcp/tools.py                    # no collections_path, localFiles
  mcp/cli.py                      # run_impl ignores MCPConfig
  mcp/resources.py                # resource URI design
  errors.py                       # unused MCPError
```
