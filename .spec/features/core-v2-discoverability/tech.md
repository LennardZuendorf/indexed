---
type: feature-tech
feature: core-v2-discoverability
sibling: product.md
parent: ../../tech.md
updated: 2026-09-01
---

# Feature: Core v2 Discoverability — Architecture

Where each of #188's five findings lives at HEAD, plus two same-shape
sibling defects folded in on maintainer request (R6, R7), and the fix shape
for each. Line numbers are anchors — verify against the file before editing.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

---

## Files

```
src/indexed/cli/app.py                                        # root --engine option (R1, unchanged reference)
src/indexed/cli/composition.py                                # normalize_engine_selector / resolve_engine_selector (R1, R3 reuse)
src/indexed/cli/knowledge/commands/_create_options.py         # new EngineOpt + GroupEngineOpt aliases (R1)
src/indexed/cli/knowledge/commands/_create_commands.py        # thread engine through 4 shells + group callback (R1)
src/indexed/cli/knowledge/commands/create.py                  # _create() forwards engine (R1)
src/indexed/cli/knowledge/commands/_create_helpers.py         # execute_create_command: subcommand engine overrides context (R1)
src/indexed/cli/knowledge/commands/search.py                  # new --rerank/--no-rerank option + v1-no-effect hint (R2)
src/indexed/core/engine.py                                    # search() facade: thread optional rerank kwarg to v2 only (R2)
src/indexed/core/v2/retrieval.py                               # search(): optional rerank override of resolve_rerank_config() (R2)
src/indexed/core/v2/_common.py                                 # resolve_rerank_config() (R2, reference — no change)
src/indexed/core/versioning.py                                 # detect_engine_version() (R2, reference — no change)
src/indexed/config/commands/set.py                             # core.engine special case: reuse normalize_engine_selector (R3)
src/indexed/cli/composition.py                                 # resolve_engine_selector config.toml branch: raw get() instead of bind() (R6)
README.md                                                      # Usage section: --engine + index migrate examples (R4)
src/indexed/cli/knowledge/cli.py                                # drop help= override on migrate + search/inspect/update/remove (R5, R7)
src/indexed/cli/knowledge/commands/migrate.py                  # dead module-level Typer app (R5, optional cleanup)
```

---

## Implementation Detail

### R1 — `--engine` invisible at `index create` (CONFIRMED)

`--engine` is defined only on the root callback (`app.py:105-110`), normalized
via `normalize_engine_selector` and stashed on `ctx.obj["engine"]`
(`app.py:150-157`). The `index create` tree
(`app` → `"index create"` mounted from `knowledge.create.app` in
`_app_setup.py:50-55` → the 4 `@app.command()` leaves in
`_create_commands.py:20-184`) has no `--engine` anywhere — `create_files` etc.
don't declare it, and `_create_options.py` has no `EngineOpt`. That's why
`index create files --engine v2 ...` fails with a bare Click `No such option:
--engine` — it's a pure Click parse-time error, no custom `UsageError` hook
exists anywhere in the CLI (`app.py:61-67`'s Typer config has none).

`execute_create_command` (`_create_helpers.py:97-192`) already reads the
root-level value back via `context_engine = get_context_value("engine")`
(line 153) and, for a genuinely new collection, resolves it through the full
`resolve_engine_selector` chain (line 189-192). It has **no subcommand-level
override slot for engine** — unlike `local`, which the same function accepts
as its own parameter (`local: bool = False`, line 114) and which overrides the
context-derived `mode_override` (`if local: mode_override = "local"`, line
155-156).

**Fix (mirrors the `local` pattern exactly):**

1. Add `EngineOpt = Annotated[Optional[str], typer.Option("--engine", help="Engine for this NEW collection: v1 or v2 (default: v1)", rich_help_panel="Storage")]` to `_create_options.py`, alongside `LocalOpt`.
2. Add `engine: _opt.EngineOpt = None` to each of the 4 `_create_commands.py` shells' signatures, and pass `engine=engine` into `_create(...)`.
3. `create.py::_create` (line 182-236) gains an `engine: Optional[str]` keyword param, forwarded to `execute_create_command(..., engine=engine, ...)` (mirrors `local=local` at line 234).
4. `execute_create_command` gains `engine: Optional[str] = None`; after computing `engine_flag` from context (line 154), add `if engine is not None: engine_flag = engine` — same shape as the `local` override at line 155-156.

5. The requirement names **both** surfaces (`index create --help` *and*
   `index create files --help`), so the `create` group gets the flag too:
   a `@app.callback()` in `_create_commands.py` taking `GroupEngineOpt`
   (`_create_options.py`, a no-help-panel twin of `EngineOpt` so it lands in
   the group's main Options block). It is a **second writer of the root's
   slot**, not a third resolution tier: Click hands a child context its
   parent's `obj` object, so `ctx.ensure_object(dict); ctx.obj["engine"] =
   normalize_engine_selector(engine)` mutates the very dict `_init_app`
   populates, and `execute_create_command`'s existing
   `get_context_value("engine")` fallback picks it up with no other change.
   It writes **only** when the flag was explicitly passed, so an unflagged
   `create` never clobbers a root-level `--engine` with `None`. Precedence
   ends up leaf flag > group flag > root flag > env > config > default; the
   leaf still wins because it arrives as an explicit kwarg, which means the
   existing-collection raw-flag-only path is untouched.

No change to the root-level `--engine` behavior (Requirement scenario 3):
when the subcommand flag is unset, `engine_flag` still comes from
`ctx.obj["engine"]` exactly as today.

**Descoped:** a generic "did you mean the top-level `--engine`?" hint for a
misplaced option on the *flat* commands (`search`/`inspect`/`update`/`remove`
— which are root-level commands, so `--engine` already works before the
subcommand name for them) would need a custom Click `UsageError` handler
wrapping `app()` in `main()` (`app.py:226-256`) — a bigger, systemic change
for a case the issue frames as an alternative ("surface the flag, **or** give
the error a hint"). Since fixing `index create` directly resolves the issue's
concrete repro, the hint is not built; see Open Questions.

### R2 — Reranking has no CLI flag (CONFIRMED, v2-only)

`index search` (`search.py:52-101`) has no `--rerank` option.
`CoreV2RerankConfig` (`core/v2/config_models.py:40-59`, registered at
`composition.py:59` under `core.v2.rerank`) is read once per call by
`resolve_rerank_config()` (`core/v2/_common.py:77-90`), consumed at
`retrieval.py:184-185` (`if rerank_cfg.enabled: _apply_rerank(...)`). v1 has
no rerank concept at all (`core/v1/engine/services/search_service.py:335-345`
has no rerank param). The facade `core/engine.py::search()` (line 512-563)
does not forward any rerank kwarg to the v2 impl today.

**Fix:**

1. `search.py`: add `rerank: Optional[bool] = typer.Option(None, "--rerank/--no-rerank", help="Rerank results with a cross-encoder (v2 collections only; overrides core.v2.rerank for this search).")`, following the same `None`-means-config-default idiom `--limit` already uses (`search.py:198-206`). The config key is written **unbracketed**, exactly as `--limit`'s `core.v1.search.max_docs` is: Rich parses `[core.v2.rerank]` as a markup tag and silently drops it from the rendered `--help`, taking the one fact the help text carries with it.
2. `core/engine.py::search()` (line 512): add `rerank: Optional[bool] = None`, forwarded only into the v2 `_engine_impl` call (v1 ignores it — no param to accept it).
3. `core/v2/retrieval.py::search()` (line 52-62): add `rerank: Optional[bool] = None`; when not `None`, override before the enabled-check — `rerank_cfg = resolve_rerank_config(); if rerank is not None: rerank_cfg = rerank_cfg.model_copy(update={"enabled": rerank})`.
4. No change inside `_apply_rerank`/`_search_one` — they already gate purely on `rerank_cfg.enabled`.

**v1-no-effect hint (resolved):** when `--rerank` is passed explicitly (not
`None`) and none of the collections actually searched are v2, print a
one-line notice rather than silently no-op. `search.py` already resolves
`collections_to_search` (a list of names) and `collections_path` before
calling `svc_search` (lines 116-196 as of this writing); `core/versioning.py`
exposes `detect_engine_version(collection_path: Path) -> EngineVersion`, a
cheap manifest-only read with no engine import needed. Add, after
`collections_to_search` is finalized (around line 196) and before/after the
search loop: check `any(detect_engine_version(Path(collections_path) /
name) == EngineVersion.V2 for name in collections_to_search)`; when `rerank
is True` and that's `False`, `print_info(...)` a note such as `"--rerank has
no effect: reranking is v2-only, and no searched collection uses the v2
engine."` (verify the exact `EngineVersion` member names in
`core/versioning.py` before implementing). No hint when `rerank` is `None`
(flag omitted) or `False` (explicitly disabled — nothing to note) or when at
least one searched collection is v2 (rerank applies to that one, even in a
mixed search).

**Stream routing (`--simple-output`):** the notice fires on *every* surface —
"never a silent no-op" is the requirement — but the stream differs.
`utils/console.py`'s shared `console` is bound to **stdout**, and under
`--simple-output` stdout is a JSON envelope (`utils/simple_output.py`'s
contract), so a `print_info` panel there would break `json.loads()` for the
programmatic consumer this mode exists for. In simple mode the notice is
therefore emitted as one plain line on **stderr** (`typer.echo(..., err=True)`
— not the Rich panel, not `console`), leaving stdout byte-for-byte parseable;
every other mode keeps the `print_info` panel unchanged.

### R3 — `config set core.engine` leaks a raw pydantic dump (CONFIRMED)

`config/commands/set.py:93-105`, the `core.engine` special case:

```python
try:
    coerced = CoreEngineConfig(engine=str(value)).engine
except ValueError as exc:
    console.print()
    print_error(str(exc))
    raise typer.Exit(1)
```

`pydantic_core.ValidationError` subclasses `ValueError`, so this catches it,
but `str(exc)` is the multi-line dump ("1 validation error for
CoreEngineConfig\nengine\n  Value error, ... [type=value_error, ...]\n    For
further information visit ..."). Meanwhile `--engine`/`INDEXED__CORE__ENGINE`
both go through `normalize_engine_selector` (`composition.py:69-80`), which
raises a plain single-line `ConfigurationError(f"Invalid engine {value!r};
expected one of: 1, 2, v1, v2")` — never touching pydantic.

`config/commands/set.py` is exempt from the config-package import-purity rule
(`scripts/check_imports.py:38`, `_EXEMPT_DIRS = {Path("config") /
"commands"}` — these are CLI-layer files merged into the config package), so
importing `indexed.cli.composition` from it is **not** a layering violation.

**Fix:** replace the `CoreEngineConfig(...)` call with
`composition.normalize_engine_selector(str(value))` directly, and catch
`ConfigurationError` instead of `ValueError`. This makes `config set` use the
exact same normalizer as the flag/env paths — byte-identical messages by
construction, not just similarly-shaped ones. Returns the same canonical
`"1"`/`"2"` value `coerced` needs downstream.

### R4 — README has zero Core v2 footprint (CONFIRMED)

`README.md`'s `## Usage` (lines 155-176) lists `create`/`search`/
`inspect`/`update`/`remove`/`config` — no `index migrate`, no `--engine`,
anywhere in the file. `## Documentation` (180-184) already funnels detail out
to `indexed.sh/docs` rather than inlining it.

**Fix:** add 1-2 lines to the `## Usage` fenced block — an `--engine` example
on `index create` and an `index migrate` example — matching the existing
`# Comment` + bash-example style, no new prose section. Keep it short; detail
stays on the hosted docs site.

### R5 — `migrate --help` never shows the docstring (CONFIRMED, repro'd)

`migrate.py:32-92` has a full docstring (the `.v1-backup`/rollback-safe
explanation + `Examples:` block). Typer's `get_command_from_info()` renders
`inspect.getdoc(callback)` **only when** `command_info.help is None`
(confirmed by reading the installed Typer source,
`typer/main.py:1391-1395`). `knowledge/cli.py:21` registers it with an
explicit override:

```python
app.command("migrate", help="Migrate a v1 collection to v2")(migrate.migrate)
```

— discarding the docstring entirely, not falling back to it. The same
mechanism affects `search`/`update`/`remove` (`cli.py:17-20`, also explicit
`help=`), but `migrate` is the one #188 names (highest stakes: safety
reassurance before a data-changing op).

**Fix:** drop the `help=` kwarg on `cli.py:21` — `app.command("migrate")
(migrate.migrate)` — letting Typer's default `inspect.getdoc()` fallback take
over. Verify the resulting short-help (used in `indexed index --help`'s
one-line command listing) still reads sensibly — it will be the docstring's
first line, `"Convert a v1 collection to the v2 engine (offline by
default)."`, which is at least as good as the current `"Migrate a v1
collection to v2"`.

**Optional cleanup (same file, not required):** `migrate.py:29`'s
module-level `app = typer.Typer(help=...)` is dead — `cli.py` imports
`migrate.migrate` directly, never `migrate.app`. Safe to delete if nothing
else references it (confirm via grep before removing).

### R6 — `[core] engine` in config.toml also leaks a raw dump (CONFIRMED, expanded scope)

`resolve_engine_selector`'s config.toml branch (`composition.py:107-121`)
today does:

```python
try:
    from indexed.core.v1.config_models import CoreEngineConfig
    cfg = config_service.bind().get(CoreEngineConfig)
    return normalize_engine_selector(cfg.engine)
except ConfigValidationError as exc:
    if exc.path == "core":
        raise
    return _DEFAULT_ENGINE
except Exception:
    return _DEFAULT_ENGINE
```

`bind()` validates via pydantic and wraps any failure as
`ConfigValidationError(path, str(exc))` (`config/service.py:157`) — same raw
multi-line dump shape as R3, and it propagates verbatim on `exc.path ==
"core"` (fail-loud is correct; the *message* is not clean).

**Fix:** stop going through `bind()`/pydantic for this lookup entirely.
`ConfigService.get(dot_path)` (`config/service.py:163-165`) returns the raw
merged value with **no** validation (`get_by_path(self.load_raw(),
dot_path)`, defaulting to `None` when absent —
`config/path_utils.py:get_by_path`). Replace the whole try/except with:

```python
raw_value = config_service.get("core.engine")
if raw_value is None:
    return _DEFAULT_ENGINE
return normalize_engine_selector(raw_value)
```

This is simpler than today's code (no `CoreEngineConfig`/
`ConfigValidationError` import needed in this function at all) and produces
the byte-identical clean message on a bad value — the exact same
`normalize_engine_selector` call the flag/env paths already make. No
semantic change to the "genuinely absent" default-fallback behavior (`None`
→ `_DEFAULT_ENGINE`, same as today's `except Exception` catch-all for an
unregistered path). By the time this branch runs, `INDEXED__CORE__ENGINE`
has already been checked and found empty (lines 103-105), so there's no risk
of this raw read disagreeing with an env-merged value.

### R7 — `--help` discards the docstring on `search`/`inspect`/`update`/`remove` too (CONFIRMED, expanded scope)

Same mechanism as R5 (Typer's `inspect.getdoc()` fallback only fires when
`command_info.help is None`), same registration file
(`knowledge/cli.py:17-20`), three more sites carrying real content dropped
today:

- `search.py:94-101` — `Examples:` block, 4 invocations.
- `inspect.py:257-264` — `Examples:` block, 4 invocations (verified: docstring exists, same override pattern).
- `remove.py:116-121` — `Examples:` block, 2 invocations (the `-f`/force behavior).
- `update.py:111` — one-line docstring only (`"Refresh and re-index a collection or all collections."`); no content is currently lost, but the override is removed anyway for consistency — a future docstring expansion here will now actually reach `--help`.

**Fix:** drop `help=` on all four registrations at `cli.py:17-20`, mirroring
R5's `migrate` fix exactly:

```python
app.command("search")(search.search)
app.command("inspect")(inspect.inspect_collections)
app.command("update")(update.update)
app.command("remove")(remove.remove)
```

Each docstring's first line becomes the new short-help shown in `indexed
index --help`'s command listing — verified readable: "Search across
collections using semantic similarity.", "Show all indexed collections or
inspect a specific collection.", "Refresh and re-index a collection or all
collections.", "Remove a collection from the index." — all at least as clear
as the current generic one-liners they replace.

**Verification risk:** any existing test asserting the exact current
one-line help text (`"Search collections"`, `"Inspect collections"`,
`"Update collections"`, `"Remove collections"`) in a `--help` snapshot will
need updating to the new docstring-derived short-help — grep
`tests/` for these literal strings before implementing.

---

## Open Questions

1. **R1 misplaced-option hint** — build a generic Click `UsageError`
   intercept (main `app.py:226-256`) that suggests moving a root-only flag
   earlier, or accept that surfacing `--engine` on `create` resolves the
   issue's concrete repro and leave the flat commands (`search`/`inspect`/
   `update`/`remove`, where `--engine` already works pre-subcommand) as is?
   **Resolved (2026-08-30, this feature): the latter** — no generic hint
   infrastructure built here; R1's own fix (adding `--engine` to `index
   create`) resolves the concrete repro, and R2's `--rerank` hint below
   covers the "don't let a flag silently do nothing" case that's actually in
   scope.
