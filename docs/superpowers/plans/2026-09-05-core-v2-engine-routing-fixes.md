# Core v2 Engine-Routing Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 9 correctness/consistency findings from [issue #186](https://github.com/LennardZuendorf/indexed/issues/186) (the PR #162 core-v2 review, third and final batch after #187/#188) — batch-abort contract violation, MCP startup crash, reranking scale/label/stdout bugs, silent config-validation swallowing, one-bad-manifest-breaks-everything, duplicated relevance code, migration status misreporting, and an import-boundary enforcement gap — each behind a regression test, landing as one PR that closes #186.

**Architecture:** Nine independent-by-file tasks, each: write a failing regression test against the CURRENT code (all line numbers below were re-verified live in this session, not taken from the original stale review), make the minimal fix, verify, commit. Two tasks are the ones to sequence carefully: Task 7 (relevance scoring) touches `mcp/formatting.py` and `search_render.py` and no other task touches either file, so it's still independent, just internally larger (it folds 3 issue findings). Task 9 (import-boundary enforcement, Option B — full fix per the repo owner's decision below) touches 10 files across `cli`/`mcp`/`core`/`scripts` — it's the one task worth running by itself, not interleaved with the others, since a mid-flight import move elsewhere could transiently trip its own regression test. Task 10 is the final whole-branch gate: full lint/type/test/import-graph run, `.spec` sync, and the PR that closes #186.

**Tech Stack:** Python 3.11+, `uv`, pytest, ruff, ty, loguru, FastMCP, LlamaIndex (function-local imports only).

**Spec:** [GitHub issue #186](https://github.com/LennardZuendorf/indexed/issues/186) is the spec this plan implements — each of its 9 bullets maps 1:1 (with one 3-way split) to a task below via the Requirements Trace. No `.spec/features/` doc exists for this issue (unlike #187/#188) because this plan follows the user's explicit superpowers workflow rather than this repo's vibe-flow spec harness; Task 10 still updates root `.spec/tech.md`/`.spec/lessons.md` per this repo's own MUST rules, since those apply regardless of which planning process produced the diff.

## Global Constraints

- Run every command via `uv run` from the repo root (`/home/user/indexed`) — never a bare `python`/`pytest`/`ruff`.
- `uv run ty check src/indexed` must report 0 diagnostics after every task.
- `uv run ruff check` must be clean after every task.
- `uv run pytest tests/unit/ --cov=indexed --cov-branch --cov-fail-under=85` must pass after every task (coverage is scoped to `core`/`connectors`/`config`/`parsing`/`protocols`/`utils` per `pyproject.toml`; `cli`/`mcp` are omitted from the gate but their own test files must still pass).
- `uv run python scripts/check_imports.py` must exit 0 after every task (Task 9 is the one task that changes its rules; every other task must not introduce a new violation).
- Module edges (never violate): `core ↛ connectors`, `connectors ↛ core`, `config`/`utils`/`parsing`/`protocols` never import up, `core/v2 ↛ core.v1`.
- Config is always read through `ConfigService` (`indexed.config.get_config()`), never a raw file read.
- Heavy ML imports (`llama_index`, `sentence_transformers`, `transformers`) stay function-local — never move one to module top.
- Commit subjects: `<type>(<scope>): <subject>`, imperative, ≤50 chars, no body/footer (this repo's own rule — append only whatever attribution trailer your own harness's session instructions separately require).
- No task adds a new third-party dependency; `uv.lock` is untouched.

---

## File Structure

```text
src/indexed/mcp/server.py                              # Task 1: guard resolve_engine_selector
src/indexed/core/v2/_common.py                          # Task 2: resolvers re-raise validation errors
src/indexed/config/commands/set.py                      # Task 3: core.engine validation before dry-run
src/indexed/core/v2/migration.py                        # Task 4: verified backup_purged
src/indexed/core/engine.py                               # Task 5: omit unknown-version collections per-name
src/indexed/cli/knowledge/commands/update_service.py     # Task 6: filter --engine batch before the loop
src/indexed/cli/knowledge/commands/update.py             # Task 6: pass engine_flag through
src/indexed/utils/relevance.py                           # Task 7: NEW shared module
src/indexed/mcp/formatting.py                            # Task 7: use shared module, forward real score_kind
src/indexed/cli/knowledge/commands/search_render.py      # Task 7: use shared module
src/indexed/core/v2/retrieval.py                         # Task 8: silence rerank stdout
src/indexed/core/v1/config_models.py                     # Task 9: remove CoreEngineConfig
src/indexed/core/facade_config.py                        # Task 9: NEW — lazy facade re-export surface
src/indexed/cli/composition.py                           # Task 9: import from new location; EXEMPT in checker
src/indexed/config/commands/get.py                       # Task 9: import CoreEngineConfig from new location
src/indexed/mcp/server.py                                # Task 9: import CoreV1SearchConfig/MCPConfig from facade
src/indexed/mcp/cli.py                                   # Task 9: import MCPConfig from facade
src/indexed/cli/app.py                                   # Task 9: import DEFAULT_INDEXER from facade
src/indexed/cli/knowledge/commands/create.py              # Task 9: import DEFAULT_INDEXER from facade
src/indexed/cli/knowledge/commands/search.py              # Task 9: import CoreV1SearchConfig from facade
src/indexed/cli/init.py                                   # Task 9: import model-cache fns from facade
scripts/check_imports.py                                 # Task 9: EXEMPT composition.py + new cli/mcp deep rule
.spec/tech.md, .spec/tech-core.md, .spec/lessons.md       # Task 10: spec sync + compounded lessons
```

---

## Requirements Trace

| Issue finding (verbatim bullet) | Task |
|---|---|
| Bulk `--engine` update aborts the whole batch | 6 |
| MCP server can crash at startup from an unused config value | 1 |
| Reranking: unbounded logits mixed with bounded cosine scores | 7 |
| Reranking: `score_kind` mislabeled as `"cosine"` in MCP output | 7 |
| Reranking: HF-Hub warning corrupts `--simple-output` stdout | 8 |
| v2 config resolvers silently swallow validation errors | 2 |
| One unrecognized manifest `version` breaks the whole batch | 5 |
| Import-boundary contract narrower than what's enforced | 9 |
| `_unified_relevance`/`_HIGHER_IS_BETTER` duplicated verbatim | 7 |
| Migration reports `backup_purged=True` without verifying | 4 |
| `config set core.engine <bad> --dry-run` shows no validation error | 3 |

---

## Task 1: MCP server startup no longer crashes on a bad `[core] engine` value

**Files:**
- Modify: `src/indexed/mcp/server.py:62`
- Test: `tests/unit/indexed/mcp/test_server.py`

**Interfaces:**
- Consumes: existing `_get_config()` guard pattern (`server.py:41-47`), existing `resolve_engine_selector(None, config_service)` (imported from `indexed.cli.composition`).
- Produces: `lifespan()`'s `state["engine"]` degrades to `"1"` instead of propagating `ConfigurationError`/`TOMLDecodeError` out of `lifespan()`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/indexed/mcp/test_server.py`, inside `class TestLifespan` (after `test_lifespan_yields_despite_malformed_global_config`, mirroring its exact structure):

```python
    def test_lifespan_survives_bad_core_engine_value(self, tmp_path, monkeypatch) -> None:
        """issue #186: an unguarded resolve_engine_selector(None, ...) call in
        lifespan() crashes MCP startup on a syntactically-valid config.toml
        whose [core] engine value is invalid — unlike every sibling config
        read in lifespan(), which is wrapped via _get_config for exactly this
        reason. A bad value must degrade the same way, not crash the server."""
        from indexed.config import reload as reload_config

        fake_home = tmp_path / "home"
        global_root = fake_home / ".indexed"
        global_root.mkdir(parents=True)
        (global_root / "config.toml").write_text('[core]\nengine = "v9"\n')

        monkeypatch.setattr(Path, "home", lambda: fake_home)
        reload_config()

        async def run_lifespan():
            async with lifespan(mcp) as state:
                return state

        result = run_async(run_lifespan())

        assert result["engine"] == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/indexed/mcp/test_server.py::TestLifespan::test_lifespan_survives_bad_core_engine_value -v`
Expected: FAIL — `ConfigurationError` (or similar) propagates out of `lifespan()` instead of the context manager yielding.

- [ ] **Step 3: Write minimal implementation**

In `src/indexed/mcp/server.py`, replace line 62:

```python
    engine = resolve_engine_selector(None, config_service)
```

with:

```python
    try:
        engine = resolve_engine_selector(None, config_service)
    except Exception:
        # Same tolerance as _get_config above: a malformed/unreadable
        # config.toml (or an invalid [core] engine value) must not crash
        # server startup — this field has no consumer yet (issue #186).
        engine = "1"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/indexed/mcp/test_server.py::TestLifespan -v`
Expected: PASS (both the new test and the existing `test_lifespan_yields_despite_malformed_global_config`).

- [ ] **Step 5: Commit**

```bash
git add src/indexed/mcp/server.py tests/unit/indexed/mcp/test_server.py
git commit -m "fix(mcp): guard engine selector at server startup"
```

---

## Task 2: v2 config resolvers fail loud on invalid values, not just unregistered specs

**Files:**
- Modify: `src/indexed/core/v2/_common.py:49-90`
- Test: `tests/unit/indexed/core/v2/test_common.py`

**Interfaces:**
- Consumes: `indexed.config.errors.ConfigValidationError` (raised by `ConfigService.bind()` on a pydantic `ValidationError`); `indexed.config.provider.Provider.get()` (raises plain `KeyError` for an unregistered spec — this must keep degrading to the model default, since direct/test calls that never registered the spec are a legitimate case per the existing docstrings).
- Produces: `resolve_embedding_config()`, `resolve_search_config()`, `resolve_rerank_config()` now propagate `ConfigValidationError` instead of silently returning a default. No caller signature changes — all 4 call sites (`core/v2/retrieval.py:73,86`, `core/v2/ingestion.py:152`, `core/v2/migration.py:122,163`) run inside `services/__init__.py`'s `_wrap()`, which already passes `IndexedError` subtypes through unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/indexed/core/v2/test_common.py`:

```python
class TestResolverValidationFailsLoud:
    """issue #186: an out-of-range value like core.v2.search.score_threshold=5.0
    (accepted by `config set`, which only warns) must not be silently discarded
    on every search — unlike resolve_engine_selector, which already fails loud
    on a bad value, these 3 resolvers caught bare Exception and returned a
    default with zero signal. Only an UNREGISTERED spec (KeyError) should
    still degrade to the default."""

    def test_resolve_search_config_reraises_validation_error(self) -> None:
        from pathlib import Path

        from indexed.cli.composition import register_app_config
        from indexed.config import get_config, reload as reload_config
        from indexed.config.errors import ConfigValidationError
        from indexed.core.v2 import _common

        config_path = Path.home() / ".indexed" / "config.toml"
        config_path.write_text("[core.v2.search]\nscore_threshold = 5.0\n")
        reload_config()
        register_app_config(get_config())

        with pytest.raises(ConfigValidationError):
            _common.resolve_search_config()

    def test_resolve_search_config_still_defaults_when_unregistered(self) -> None:
        """No register_app_config() call → Provider.get() raises KeyError →
        must still degrade to the default (unchanged prior behavior)."""
        from indexed.config import reload as reload_config
        from indexed.core.v2 import _common
        from indexed.core.v2.config_models import CoreV2SearchConfig

        reload_config()  # fresh ConfigService, nothing registered

        result = _common.resolve_search_config()

        assert result == CoreV2SearchConfig()
```

(`pytest` is already imported at the top of this file; add it if not.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/indexed/core/v2/test_common.py::TestResolverValidationFailsLoud -v`
Expected: `test_resolve_search_config_reraises_validation_error` FAILS (no exception raised, a default `CoreV2SearchConfig()` is returned instead); `test_resolve_search_config_still_defaults_when_unregistered` PASSES already (documents current-and-desired behavior).

- [ ] **Step 3: Write minimal implementation**

In `src/indexed/core/v2/_common.py`, add the import (near the top, alongside the other runtime imports — not the `TYPE_CHECKING` block, since it's needed at runtime):

```python
from indexed.config.errors import ConfigValidationError
```

Then change all three resolvers (lines 49-90) from:

```python
    try:
        from indexed.config import get_config

        return get_config().bind().get(CoreV2EmbeddingConfig)
    except Exception:
        return CoreV2EmbeddingConfig()
```

to the same shape for each of the 3 functions:

```python
    try:
        from indexed.config import get_config

        return get_config().bind().get(CoreV2EmbeddingConfig)
    except ConfigValidationError:
        raise
    except Exception:
        return CoreV2EmbeddingConfig()
```

(Apply the identical `except ConfigValidationError: raise` / `except Exception: return Default()` pair to `resolve_search_config` and `resolve_rerank_config` too — same shape, different model class.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/indexed/core/v2/test_common.py -v`
Expected: PASS. Also run `uv run pytest tests/unit/indexed/core/v2/test_retrieval.py tests/unit/indexed/core/v2/test_ingestion.py tests/unit/indexed/core/v2/test_migration.py -v` to confirm no caller regressed (none of them wrap these resolvers in try/except today, so nothing should change for valid configs).

- [ ] **Step 5: Commit**

```bash
git add src/indexed/core/v2/_common.py tests/unit/indexed/core/v2/test_common.py
git commit -m "fix(core-v2): fail loud on invalid v2 config values"
```

---

## Task 3: `config set core.engine <bad> --dry-run` reports the error instead of a silent preview

**Files:**
- Modify: `src/indexed/config/commands/set.py:71-106`
- Test: `tests/unit/indexed/config/test_cli.py`

**Interfaces:**
- Consumes: `composition.normalize_engine_selector(str) -> str` (raises `ConfigurationError` on a bad value — unchanged).
- Produces: the `core.engine` validation branch now runs before the `--dry-run` early return, for both dry-run and normal invocations alike; no other key is affected (grep confirms `core.engine` is the only special-cased key in this file).

- [ ] **Step 1: Write the failing test**

Add to the same test class as `test_set_config_engine_rejects_bad_value` in `tests/unit/indexed/config/test_cli.py`:

```python
    @patch("indexed.config.commands.set.get_config")
    def test_set_config_engine_rejects_bad_value_even_with_dry_run(
        self, mock_config_service
    ):
        """issue #186: `config set core.engine v3 --dry-run` must reject the
        value up front — today the CoreEngineConfig check sits after the
        dry-run early-return, so an invalid preview looks accepted."""
        mock_config = Mock()
        mock_config.load_raw.return_value = {}
        mock_config_service.return_value = mock_config

        from indexed.cli.app import app

        result = runner.invoke(
            app, ["config", "set", "core.engine", "v3", "--dry-run"]
        )
        assert result.exit_code == 1
        assert "Preview" not in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/indexed/config/test_cli.py -k test_set_config_engine_rejects_bad_value_even_with_dry_run -v`
Expected: FAIL — `exit_code == 0` and the "Configuration Preview" card is printed instead of an error.

- [ ] **Step 3: Write minimal implementation**

In `src/indexed/config/commands/set.py`, move the `core.engine` validation block to run immediately after `coerced = _coerce_value(value)` (line 60), before the `if dry_run:` block (line 71). Result — replace the region from line 60 through the end of the dry-run block (91) with:

```python
    config = get_config()
    coerced = _coerce_value(value)

    if key == "core.engine":
        # R3: validate/normalize through the exact same normalizer the
        # engine-selector resolution path (--engine/env) uses, so all three
        # surfaces report a byte-identical clean message on a bad value
        # instead of a raw multi-line pydantic dump. Runs BEFORE --dry-run
        # (issue #186) so a preview of an invalid value is rejected too.
        from indexed.cli import composition
        from indexed.config.errors import ConfigurationError

        try:
            coerced = composition.normalize_engine_selector(str(value))
        except ConfigurationError as exc:
            console.print()
            print_error(str(exc))
            raise typer.Exit(1)

    # Get old value if exists
    try:
        old_raw = config.load_raw() or {}
        from indexed.config.path_utils import get_by_path

        old_value = get_by_path(old_raw, key, default=None)
    except Exception:
        old_value = None

    if dry_run:
        # Preview mode
        console.print()
        console.print(
            f"[{get_heading_style()}]Configuration Preview[/{get_heading_style()}]"
        )
        console.print()

        rows = [("Key", key)]
        if old_value is not None:
            rows.append(("Previous", _masked_config_value(key, old_value)))
        rows.append(("New", _masked_config_value(key, coerced)))

        card = create_detail_card(title="Change Summary", rows=rows)
        console.print(card)
        console.print()
        console.print(
            f"[{get_secondary_style()}]Preview only - not saved (remove --dry-run to save)[/{get_secondary_style()}]"
        )
        console.print()
        return
```

Then delete the now-duplicate original `if key == "core.engine":` block that used to sit after the dry-run branch (was lines 93-106).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/indexed/config/test_cli.py -v`
Expected: PASS, including the pre-existing `test_set_config_dry_run`, `test_set_config_engine_normalizes_friendly_alias`, and `test_set_config_engine_rejects_bad_value` (unaffected — same behavior for non-dry-run and for valid values).

- [ ] **Step 5: Commit**

```bash
git add src/indexed/config/commands/set.py tests/unit/indexed/config/test_cli.py
git commit -m "fix(config): validate core.engine before dry-run preview"
```

---

## Task 4: Migration reports the real outcome of a backup purge

**Files:**
- Modify: `src/indexed/core/v2/migration.py` (two call sites, ~line 114 and ~line 239; add one helper)
- Test: `tests/unit/indexed/core/v2/test_migration.py`

**Interfaces:**
- Produces: `_purge_backup_dir(backup_dir: Path) -> bool` — new private helper in `migration.py`, mirrors `persist.replace_dir`'s post-`rmtree` check. Both existing `MigrationResult(..., backup_purged=...)` call sites use its return value instead of a hardcoded `True`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/indexed/core/v2/test_migration.py`, near the existing `test_purge_backup_*` tests:

```python
def test_purge_backup_standalone_reports_false_when_residual_files_remain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """issue #186: rmtree(ignore_errors=True) can silently leave the backup
    dir behind (e.g. a locked handle) — backup_purged must reflect that, not
    be hardcoded True, mirroring persist.replace_dir's post-check."""
    base = tmp_path / "cols"
    _write_v1_collection(base, "c1", _corpus())
    with mock_embedding(embed_dim=8):
        migration.migrate("c1", collections_path=str(base))  # keeps backup
    assert (base / "c1.v1-backup").is_dir()

    monkeypatch.setattr(migration.shutil, "rmtree", lambda *a, **kw: None)
    result = migration.migrate("c1", collections_path=str(base), purge_backup=True)

    assert result.action == "purge-backup"
    assert result.backup_purged is False
    assert (base / "c1.v1-backup").is_dir()


def test_migrate_with_purge_reports_false_when_residual_files_remain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "cols"
    _write_v1_collection(base, "c1", _corpus())

    monkeypatch.setattr(migration.shutil, "rmtree", lambda *a, **kw: None)
    with mock_embedding(embed_dim=8):
        result = migration.migrate("c1", collections_path=str(base), purge_backup=True)

    assert result.backup_purged is False
    assert (base / "c1.v1-backup").is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/indexed/core/v2/test_migration.py -k residual_files_remain -v`
Expected: both FAIL — `result.backup_purged is True` (hardcoded) despite `rmtree` being a no-op.

- [ ] **Step 3: Write minimal implementation**

In `src/indexed/core/v2/migration.py`, add `from loguru import logger` to the imports (after the existing `from indexed.core.errors import CoreV2Error` line), and add this helper near the top of the file, after the imports:

```python
def _purge_backup_dir(backup_dir: Path) -> bool:
    """Best-effort rmtree; return whether the backup is actually gone.

    Mirrors persist.replace_dir's post-rmtree check — ignore_errors=True can
    leave residual files (e.g. a locked handle) behind silently (issue #186).
    """
    shutil.rmtree(backup_dir, ignore_errors=True)
    purged = not backup_dir.exists()
    if not purged:
        logger.warning(
            f"migration: residual backup directory left behind at {str(backup_dir)!r}"
        )
    return purged
```

Replace the standalone purge-backup call site (~line 114):

```python
                shutil.rmtree(backup_dir, ignore_errors=True)
                return MigrationResult(
                    ...
                    backup_purged=True,
                    ...
                )
```

with:

```python
                backup_purged = _purge_backup_dir(backup_dir)
                return MigrationResult(
                    ...
                    backup_purged=backup_purged,
                    ...
                )
```

Replace the post-migrate purge call site (~line 239):

```python
    backup_purged = False
    backup_path: Optional[str] = str(backup_dir)
    if purge_backup:
        shutil.rmtree(backup_dir, ignore_errors=True)
        backup_purged = True
        backup_path = None
```

with:

```python
    backup_purged = False
    backup_path: Optional[str] = str(backup_dir)
    if purge_backup:
        backup_purged = _purge_backup_dir(backup_dir)
        backup_path = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/indexed/core/v2/test_migration.py -v`
Expected: PASS, including all 3 pre-existing `test_purge_backup_*` happy-path tests (unaffected — `_purge_backup_dir` returns `True` when `rmtree` genuinely succeeds).

- [ ] **Step 5: Commit**

```bash
git add src/indexed/core/v2/migration.py tests/unit/indexed/core/v2/test_migration.py
git commit -m "fix(core-v2): verify backup removal before reporting purged"
```

---

## Task 5: An unrecognized manifest version no longer aborts the whole batch

**Files:**
- Modify: `src/indexed/core/engine.py:207-243` (`_group_names_by_engine`)
- Test: `tests/unit/indexed/core/test_engine_facade.py`

**Interfaces:**
- Produces: `_group_names_by_engine` now omits (rather than raises for) a collection whose manifest carries an unrecognized `version` marker, logging a warning — mirroring the existing `engine_descriptors()` omission pattern (`core/engine.py:334-338`) and `core/v2/retrieval.py`'s documented per-collection-failure contract. `status()`/`inspect()` (the only two callers) need no changes — they already iterate whatever groups come back.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/indexed/core/test_engine_facade.py`, near the existing `test_status_without_engine_on_unknown_marker_raises`:

```python
def test_status_omits_unknown_marker_but_returns_the_rest(
    monkeypatch, tmp_path: Path
) -> None:
    """issue #186: one collection with an unrecognized manifest version must
    not break status()/inspect() for every OTHER collection in the batch —
    it should be omitted (like every other unreadable-collection case in this
    module), not fail the whole call."""
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services

    _make_collection(tmp_path, "legacy", {"version": "1"})
    _make_collection(tmp_path, "future", {"version": "3"})
    sentinel = object()
    monkeypatch.setattr(
        v1_services, "status", lambda collection_names=None, **kw: [sentinel]
    )

    result = facade.status(["legacy", "future"], collections_path=str(tmp_path))

    assert result == [sentinel]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/indexed/core/test_engine_facade.py -k test_status_omits_unknown_marker_but_returns_the_rest -v`
Expected: FAIL — `UnknownEngineVersionError` raised instead of a result.

- [ ] **Step 3: Write minimal implementation**

In `src/indexed/core/engine.py`, add `from loguru import logger` to the imports (top of file, alongside the existing `from indexed.core.versioning import ...` line). Then in `_group_names_by_engine` (lines 207-243), change:

```python
            try:
                version = detect_engine_version(collection_path)
            except UnknownEngineVersionError:
                raise
            except ValueError:
                version = _DEFAULT_ENGINE
```

to:

```python
            try:
                version = detect_engine_version(collection_path)
            except UnknownEngineVersionError:
                logger.warning(
                    f"Collection '{name}' has an unrecognized manifest "
                    "version; omitting it from this batch."
                )
                continue
            except ValueError:
                version = _DEFAULT_ENGINE
```

Also update the function's docstring (lines 216-220), which currently states the unknown-marker case "fail[s] loud" — change that bullet to say it is omitted with a warning, matching the new behavior.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/indexed/core/test_engine_facade.py -v`
Expected: PASS. Note `test_status_without_engine_on_unknown_marker_raises`/`test_search_without_engine_on_unknown_marker_raises` (single-collection-only batches) are UNCHANGED and must still pass — a solo unknown-version collection still ends up omitted, so `status()`/`search()` now returns an empty list/dict instead of raising for that scenario. Re-read those two tests before this step: if they assert `pytest.raises(UnknownEngineVersionError)` for a single-collection call, they are testing exactly the behavior this task changes and must be updated to assert the now-empty result instead (do this update in this same step, not as an afterthought) — `clear()`/`create()` are untouched (they use `_resolve_existing_engine`, not `_group_names_by_engine`, and must keep failing loud per the issue's own note).

- [ ] **Step 5: Commit**

```bash
git add src/indexed/core/engine.py tests/unit/indexed/core/test_engine_facade.py
git commit -m "fix(core): omit unknown-version collections, not abort"
```

---

## Task 6: `indexed update --engine v2` no longer aborts on the first v1 collection

**Files:**
- Modify: `src/indexed/cli/knowledge/commands/update_service.py:245-289` (`resolve_collections_to_update`)
- Modify: `src/indexed/cli/knowledge/commands/update.py:158-163` (pass `engine_flag` through)
- Test: `tests/unit/indexed/knowledge/commands/test_update.py`

**Interfaces:**
- Consumes: `indexed.core.engine.engine_descriptors(names, *, collections_path) -> List[EngineDescriptor]` (public facade function, already exists — `EngineDescriptor.name`/`.engine_version`).
- Produces: `resolve_collections_to_update` gains an `engine: str | None = None` keyword parameter (bulk path only — a named single `collection` keeps today's behavior of raising `EngineMismatchError` on mismatch, since that's an explicit, informative request). The existing `except CoreError: raise` in `run_update_loop` (lines 381-387, 407-410) is left in place as defense-in-depth and is NOT touched by this task — `test_run_update_loop_propagates_engine_mismatch` continues to test that function in isolation and must keep passing unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/indexed/knowledge/commands/test_update.py` (add `import json` to the file's imports if not already present):

```python
def test_resolve_collections_to_update_filters_by_requested_engine(tmp_path):
    """issue #186: `indexed update --engine v2` over a mixed v1/v2 set must
    exclude v1 collections from the candidate list up front — not attempt
    them and hard-abort the whole batch on the first EngineMismatchError."""
    from indexed.cli.knowledge.commands import update_service as svc

    for name, version in [("v1-coll", "1"), ("v2-coll", "2")]:
        coll = tmp_path / name
        coll.mkdir()
        (coll / "manifest.json").write_text(
            json.dumps({"version": version, "collectionName": name}),
            encoding="utf-8",
        )

    status_v1 = SimpleNamespace(name="v1-coll", source_type="localFiles", indexers=["default"])
    status_v2 = SimpleNamespace(name="v2-coll", source_type="localFiles", indexers=["default"])
    cmd = SimpleNamespace(
        svc_status=lambda names=None, **kw: [status_v1, status_v2],
        console=SimpleNamespace(print=lambda *a, **kw: None),
    )

    result = svc.resolve_collections_to_update(
        cmd, collection=None, collections_path=str(tmp_path), simple=True, engine="2"
    )

    assert result == ["v2-coll"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/indexed/knowledge/commands/test_update.py -k test_resolve_collections_to_update_filters_by_requested_engine -v`
Expected: FAIL — `TypeError: resolve_collections_to_update() got an unexpected keyword argument 'engine'`.

- [ ] **Step 3: Write minimal implementation**

In `src/indexed/cli/knowledge/commands/update_service.py`, change `resolve_collections_to_update`'s signature and bulk-path body (lines 245-277):

```python
def resolve_collections_to_update(
    cmd: Any,
    *,
    collection: str | None,
    collections_path: str,
    simple: bool,
    engine: str | None = None,
) -> list[str] | None:
    """Resolve which collections to update.

    Returns the list of collection names, or ``None`` when there is nothing to
    do (the "no collections" message was already emitted — the command should
    return cleanly). Raises ``typer.Exit(1)`` when a *named* collection does not
    exist.

    An explicit ``engine`` (bulk path only, i.e. ``collection is None``)
    filters the candidate list down to that engine's collections BEFORE the
    update loop runs, so a mismatched collection is silently out of scope
    instead of hard-aborting the whole batch (issue #186). A named single
    ``collection`` keeps today's behavior — an explicit mismatch still raises
    ``EngineMismatchError`` from inside the loop, which is the more
    informative outcome for a single targeted request.
    """
    if collection is None:
        all_statuses = cmd.svc_status(collections_path=collections_path)
        if not all_statuses:
            if simple:
                print_json({"error": "No collections found"})
                return None
            cmd.console.print(
                f"\n[{get_dim_style()}]No collections found to update[/{get_dim_style()}]"
            )
            cmd.console.print(
                f"[{get_dim_style()}]Get started: indexed index create [source][/{get_dim_style()}]"
            )
            return None

        collections = [s.name for s in all_statuses]

        if engine is not None:
            from indexed.core.engine import engine_descriptors

            versions = {
                d.name: d.engine_version
                for d in engine_descriptors(collections, collections_path=collections_path)
            }
            collections = [n for n in collections if versions.get(n) == engine]
            if not collections:
                if simple:
                    print_json({"error": f"No engine {engine!r} collections found"})
                    return None
                cmd.console.print(
                    f"\n[{get_dim_style()}]No engine {engine!r} collections to update[/{get_dim_style()}]"
                )
                return None

        if not simple and len(collections) > 1:
            # Collection names are user-controlled — escape the assembled
            # display string before it enters this markup f-string.
            names = escape(", ".join(f'"{n}"' for n in collections))
            cmd.console.print(
                f"\n[{get_heading_style()}]Updating {len(collections)} Collections: {names}[/{get_heading_style()}]"
            )
        return collections

    statuses = cmd.svc_status([collection], collections_path=collections_path)
    if not statuses:
        if simple:
            print_json(
                {"status": "error", "error": f"Collection '{collection}' not found"}
            )
        else:
            cmd.print_error(f"Collection '{collection}' not found")
        raise typer.Exit(1)

    return [collection]
```

In `src/indexed/cli/knowledge/commands/update.py`, pass `engine_flag` through at the call site (line 158-163):

```python
    collections_to_update = svc.resolve_collections_to_update(
        this_module,
        collection=collection,
        collections_path=collections_path,
        simple=simple,
        engine=engine_flag,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/indexed/knowledge/commands/test_update.py -v`
Expected: PASS, including the pre-existing `TestUpdateEngineRouting` class (unaffected — those tests exercise `run_update_loop` directly with a pre-built `collections` list, not `resolve_collections_to_update`).

- [ ] **Step 5: Commit**

```bash
git add src/indexed/cli/knowledge/commands/update_service.py src/indexed/cli/knowledge/commands/update.py tests/unit/indexed/knowledge/commands/test_update.py
git commit -m "fix(cli): filter --engine update batch before the loop"
```

---

## Task 7: One shared relevance-scoring module, with a bounded rerank scale and the real score_kind forwarded

This task combines 3 issue findings that live in the exact same duplicated function pair (`_unified_relevance`/`_HIGHER_IS_BETTER` in both `mcp/formatting.py` and `cli/knowledge/commands/search_render.py`) — splitting them into separate tasks would mean either doing the same plumbing twice or an artificial dependency chain for no independent-review benefit.

**Files:**
- Create: `src/indexed/utils/relevance.py`
- Modify: `src/indexed/mcp/formatting.py`
- Modify: `src/indexed/cli/knowledge/commands/search_render.py`
- Test: `tests/unit/indexed/utils/test_relevance.py` (new), `tests/unit/indexed/mcp/test_formatting.py`

**Interfaces:**
- Produces: `indexed.utils.relevance.HIGHER_IS_BETTER: frozenset[str]` (`{"cosine", "rerank"}`) and `indexed.utils.relevance.unified_relevance(raw_score: float, score_kind: str) -> float`. `utils` is a leaf layer both `cli` and `mcp` may import (module edge rules unaffected — this is a pure-arithmetic, engine-agnostic function with no `core.v1`/`core.v2` dependency, confirmed by reading both current implementations).
- Consumes (by `mcp/formatting.py` and `search_render.py`): the new `unified_relevance`/`HIGHER_IS_BETTER`, replacing their local private copies.

- [ ] **Step 1: Write the failing test for the new module**

Create `tests/unit/indexed/utils/test_relevance.py`:

```python
"""Tests for the shared relevance-scoring helper (issue #186 dedup + fix)."""

from __future__ import annotations

import math

from indexed.utils.relevance import HIGHER_IS_BETTER, unified_relevance


def test_higher_is_better_contains_cosine_and_rerank() -> None:
    assert HIGHER_IS_BETTER == frozenset({"cosine", "rerank"})


def test_cosine_score_passes_through_unchanged() -> None:
    assert unified_relevance(0.75, "cosine") == 0.75


def test_l2_squared_score_maps_to_cosine_similarity() -> None:
    # sim = 1 - d^2/2
    assert unified_relevance(0.1, "l2_squared") == 1.0 - 0.1 / 2.0
    assert unified_relevance(0.1, "") == 1.0 - 0.1 / 2.0  # v1 has no scoreKind at all


def test_rerank_score_is_bounded_regardless_of_raw_magnitude() -> None:
    """issue #186: unbounded cross-encoder logits (measured -11 to +6) must
    land in a comparable (0, 1) range instead of overwhelming/underwhelming
    the [0,1] cosine scale when sorted together."""
    high = unified_relevance(6.27, "rerank")
    low = unified_relevance(-11.0, "rerank")

    assert 0.0 < high < 1.0
    assert 0.0 < low < 1.0
    assert high > low  # monotonic: order among rerank scores is preserved
    assert high == 1.0 / (1.0 + math.exp(-6.27))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/indexed/utils/test_relevance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'indexed.utils.relevance'`.

- [ ] **Step 3: Create the shared module**

Create `src/indexed/utils/relevance.py`:

```python
"""Shared cross-engine relevance scoring (issue #186 — was duplicated
verbatim between mcp/formatting.py and cli/knowledge/commands/search_render.py).

Pure arithmetic, engine-agnostic: no core.v1/core.v2 import, so both the CLI
and MCP formatters (top-layer consumers) can import it directly.
"""

from __future__ import annotations

import math

# Score kinds (v2's per-collection "scoreKind" field) for which a HIGHER
# score is a BETTER match. v1 results carry no "scoreKind" key at all, so a
# plain `.get()` defaults a v1 collection out of this set — its sort key
# stays the raw ascending distance, unchanged. "rerank" is a cross-encoder
# relevance (also higher-is-better) reported when
# [core.v2.rerank] enabled=true replaces the cosine score.
HIGHER_IS_BETTER = frozenset({"cosine", "rerank"})


def unified_relevance(raw_score: float, score_kind: str) -> float:
    """Map a raw per-engine/per-mode score onto one comparable (0, 1) measure.

    - "cosine" (v2, rerank disabled): already a bounded similarity in [0,1] —
      the raw score IS the relevance, unchanged.
    - "rerank" (v2 with [core.v2.rerank] enabled): an UNBOUNDED cross-encoder
      logit (measured -11 to +6) — squashed through a sigmoid so it lands in
      (0,1), comparable to cosine/l2_squared instead of overwhelming or
      underwhelming them when sorted together (issue #186).
    - anything else ("l2_squared"/v1, or absent): v1's squared-L2 distance
      d^2 over unit-normalized vectors — sim = 1 - d^2/2 recovers the cosine
      exactly.
    """
    if score_kind == "rerank":
        return 1.0 / (1.0 + math.exp(-raw_score))
    if score_kind in HIGHER_IS_BETTER:  # "cosine"
        return raw_score
    return 1.0 - raw_score / 2.0


__all__ = ["HIGHER_IS_BETTER", "unified_relevance"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/indexed/utils/test_relevance.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing test for MCP-side score_kind forwarding + bounded mixing**

Add to `tests/unit/indexed/mcp/test_formatting.py`, near `test_mixed_v1_v2_ranks_on_one_comparable_relevance`:

```python
def test_reranked_collection_reports_real_score_kind_not_cosine() -> None:
    """issue #186: score_kind was derived from higher_is_better (a bool),
    collapsing "rerank" into "cosine" — an LLM consumer needs the real kind
    to interpret the score correctly."""
    raw = {
        "v2-coll": {
            "collectionName": "v2-coll",
            "scoreKind": "rerank",
            "results": [_chunk("d1", 6.27)],
        }
    }
    out = format_search_results_for_llm(raw, "q")
    assert out["results"][0]["score_kind"] == "rerank"


def test_rerank_score_does_not_bypass_cosine_bounds_in_mixed_sort() -> None:
    """issue #186: an unbounded rerank logit must not sit outside the [0,1]
    range a cosine/l2_squared relevance occupies once mixed together."""
    raw = {
        "v2-cosine": {
            "collectionName": "v2-cosine",
            "scoreKind": "cosine",
            "results": [_chunk("strong-cosine", 0.9)],
        },
        "v2-rerank": {
            "collectionName": "v2-rerank",
            "scoreKind": "rerank",
            "results": [_chunk("rerank-hit", 6.27)],
        },
    }
    out = format_search_results_for_llm(raw, "q")
    by_id = {r["document_id"]: r for r in out["results"]}
    assert 0.0 < by_id["rerank-hit"]["relevance"] < 1.0
    assert by_id["strong-cosine"]["relevance"] == 0.9
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/unit/indexed/mcp/test_formatting.py -k "score_kind or bypass_cosine_bounds" -v`
Expected: FAIL — `score_kind` reports `"cosine"` for the rerank collection, and its `relevance` is the raw unbounded `6.27`.

- [ ] **Step 7: Update mcp/formatting.py**

Replace lines 1-26 of `src/indexed/mcp/formatting.py` (module docstring stays; the local `_HIGHER_IS_BETTER`/`_unified_relevance` are removed and replaced with an import):

```python
"""LLM-optimized formatting for MCP search results."""

from __future__ import annotations

from typing import Any, Dict, List

from indexed.utils.relevance import HIGHER_IS_BETTER, unified_relevance
```

In `format_search_results_for_llm`, change the per-collection/per-chunk block (around lines 67-108) from tracking `higher_is_better`/`"_higher_is_better"` to also tracking the raw kind:

```python
        # v1 carries no "scoreKind" (squared-L2, lower-better); v2 records
        # "cosine" or "rerank" (both higher-better) per collection.
        raw_score_kind = collection_data.get("scoreKind")
        higher_is_better = raw_score_kind in HIGHER_IS_BETTER
        if higher_is_better:
            any_higher_is_better = True
```

and in the chunk-append block, change the sort-helper key:

```python
                        {
                            "rank": 0,
                            "relevance_score": score,
                            "collection": collection_name,
                            "document_id": doc_id,
                            "document_url": doc_url,
                            "chunk_number": chunk_number,
                            "text": content_text,
                            # Sort helper only, popped before the envelope is
                            # returned. The real score_kind ("cosine"/"rerank")
                            # when known, else None (v1 / unknown kind).
                            "_score_kind": raw_score_kind if higher_is_better else None,
                        }
```

and the two lines right after `_rank_chunks(...)`:

```python
    _rank_chunks(all_chunks, unified=any_higher_is_better)
    for chunk in all_chunks:
        del chunk["_score_kind"]
```

Finally, replace `_rank_chunks` (lines 124-148 in the original) with:

```python
def _rank_chunks(all_chunks: List[Dict[str, Any]], *, unified: bool) -> None:
    """Order ``all_chunks`` best-first, in place (R11 cross-engine / R6 v1-only).

    ``unified=True`` (a v2 collection is present, mixed or v2-only): every
    chunk gets a ``relevance`` on one comparable measure via
    ``unified_relevance`` (bounded (0,1) even for an unbounded rerank logit,
    issue #186) plus a ``score_kind`` label carrying the REAL kind
    ("cosine"/"rerank"/"l2_squared") — not a boolean-derived guess. The raw
    ``relevance_score`` is left untouched.

    ``unified=False`` (v1-only, no ``scoreKind`` anywhere): the EXACT
    pre-feature path — ascending raw score, no ``relevance``/``score_kind``
    field added — so a v1-only search's output is byte-identical (R6).
    """
    if not unified:
        all_chunks.sort(key=lambda c: c["relevance_score"])
        return

    for chunk in all_chunks:
        score_kind = chunk["_score_kind"] or "l2_squared"
        chunk["relevance"] = unified_relevance(chunk["relevance_score"], score_kind)
        chunk["score_kind"] = score_kind
    all_chunks.sort(key=lambda c: c["relevance"], reverse=True)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/unit/indexed/mcp/test_formatting.py -v`
Expected: PASS, including all pre-existing tests (`test_mixed_v1_v2_ranks_on_one_comparable_relevance` still asserts `score_kind == "cosine"`/`"l2_squared"` for those inputs — unaffected since `raw_score_kind` for a `"cosine"` collection is literally `"cosine"`).

- [ ] **Step 9: Update search_render.py**

In `src/indexed/cli/knowledge/commands/search_render.py`, remove the local `_HIGHER_IS_BETTER`/`_unified_relevance` (lines 30-50) and add the import alongside the other `...utils` imports at the top:

```python
from ...utils.relevance import HIGHER_IS_BETTER, unified_relevance
```

Change every remaining reference to `_HIGHER_IS_BETTER` in this file (the `is_known_score_kind = raw_score_kind in _HIGHER_IS_BETTER` line, ~147) to `HIGHER_IS_BETTER`.

Change `_sort_key` (lines 195-197) from using the boolean `higher_is_better_by_collection` to the raw kind already captured in `score_kind_by_collection` (line 135, populated only for known kinds):

```python
        def _sort_key(x: ChunkInfo) -> float:
            score_kind = score_kind_by_collection.get(x["collection"], "")
            return -unified_relevance(x["chunk"].get("score", 999), score_kind)
```

(`higher_is_better_by_collection` stays as-is — it still gates the `any_v2 = any(...)` branch decision above it; only the sort key's scale source changes.)

- [ ] **Step 10: Run tests to verify they pass**

Run: `uv run pytest tests/unit/indexed/knowledge/commands/test_search.py -v`
Expected: PASS, including `test_mixed_engines_rank_on_unified_relevance`. If a rerank-specific CLI display test exists and asserts a specific numeric relevance for a rerank score, update its expected value to the sigmoid result (`1 / (1 + exp(-raw_score))`) — grep first: `grep -n "rerank" tests/unit/indexed/knowledge/commands/test_search.py`.

- [ ] **Step 11: Full regression pass**

Run: `uv run pytest tests/unit/indexed/utils/test_relevance.py tests/unit/indexed/mcp/test_formatting.py tests/unit/indexed/knowledge/commands/test_search.py tests/unit/indexed/core/v2/test_retrieval.py -v`
Expected: all PASS. Also run `uv run ruff check src/indexed/mcp/formatting.py src/indexed/cli/knowledge/commands/search_render.py src/indexed/utils/relevance.py` and `uv run ty check src/indexed`.

- [ ] **Step 12: Commit**

```bash
git add src/indexed/utils/relevance.py src/indexed/mcp/formatting.py src/indexed/cli/knowledge/commands/search_render.py tests/unit/indexed/utils/test_relevance.py tests/unit/indexed/mcp/test_formatting.py
git commit -m "fix(search): bound rerank scale, forward real score_kind"
```

---

## Task 8: Reranking no longer leaks an HF-Hub warning onto stdout

**Files:**
- Modify: `src/indexed/core/v2/retrieval.py:129-145` (`_apply_rerank`)
- Test: `tests/unit/indexed/core/v2/test_retrieval.py`

**Interfaces:**
- Produces: `_apply_rerank` wraps the `SentenceTransformerRerank` construction + call in `contextlib.redirect_stdout`, so any raw stdout write from the HF/transformers stack (not just Python `logging` records, which `bootstrap_logging` already redirects) lands on stderr instead — the one guaranteed choke point regardless of CLI vs MCP entry.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/indexed/core/v2/test_retrieval.py`, near the other rerank tests:

```python
def test_rerank_never_writes_to_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """issue #186: enabling rerank must never write to stdout — it corrupts
    --simple-output JSON parsing even with stderr separately redirected."""
    import io

    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration"])])

    monkeypatch.setattr(
        retrieval,
        "resolve_rerank_config",
        lambda: CoreV2RerankConfig(enabled=True, model="x", top_n=3),
    )

    class _NoisyRerank:
        def __init__(self, *, model: str, top_n: int) -> None:
            print("a third-party library writes a warning directly to stdout")
            self._top_n = top_n

        def postprocess_nodes(self, nodes, *, query_str=None, query_bundle=None):
            return nodes[: self._top_n]

    import llama_index.core.postprocessor as pp

    monkeypatch.setattr(pp, "SentenceTransformerRerank", _NoisyRerank)

    captured = io.StringIO()
    import contextlib

    with mock_embedding(embed_dim=8):
        with contextlib.redirect_stdout(captured):
            retrieval.search("penguin", configs=[_cfg("c1")], collections_path=str(cols))

    assert captured.getvalue() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/indexed/core/v2/test_retrieval.py -k test_rerank_never_writes_to_stdout -v`
Expected: FAIL — `captured.getvalue()` contains the noisy library's print output.

- [ ] **Step 3: Write minimal implementation**

In `src/indexed/core/v2/retrieval.py`, add `import contextlib` and `import sys` to the top-level imports, then change `_apply_rerank` (lines 129-145):

```python
def _apply_rerank(
    nodes_with_scores: List["NodeWithScore"],
    query: str,
    rerank_cfg: "CoreV2RerankConfig",
) -> List["NodeWithScore"]:
    """Rerank retrieved nodes with a cross-encoder, keeping ``top_n`` (R10).

    Imports are FUNCTION-LOCAL and reached ONLY when rerank is enabled, so a
    disabled search never imports ``SentenceTransformerRerank`` or the
    ``CrossEncoder`` it loads (zero cost, proven by a lazy-import probe). The
    postprocessor is passed the query and nodes EXPLICITLY — ``Settings`` is
    never touched (retriever-only contract). Construction and inference are
    wrapped so a raw HF-Hub/transformers stdout write (issue #186) can't
    corrupt ``--simple-output`` JSON — it lands on stderr instead.
    """
    from llama_index.core.postprocessor import SentenceTransformerRerank

    with contextlib.redirect_stdout(sys.stderr):
        reranker = SentenceTransformerRerank(
            model=rerank_cfg.model, top_n=rerank_cfg.top_n
        )
        return reranker.postprocess_nodes(nodes_with_scores, query_str=query)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/indexed/core/v2/test_retrieval.py -v`
Expected: PASS, including `test_rerank_disabled_imports_no_cross_encoder` (unaffected — the redirect only wraps the enabled path) and `test_rerank_enabled_reorders_and_respects_top_n`.

- [ ] **Step 5: Commit**

```bash
git add src/indexed/core/v2/retrieval.py tests/unit/indexed/core/v2/test_retrieval.py
git commit -m "fix(core-v2): keep rerank output off stdout"
```

---

## Decision: Task 9 scope — Option B (full enforcement)

**Resolved by the repo owner: Option B.** The live blast radius is bigger than the issue's one named example: `scripts/check_imports.py` has no `cli`/`mcp` → `core.v1`/`core.v2` rule at all today, and grepping the real tree found **11 such imports across 9 files** — `mcp/server.py:17`, `mcp/cli.py:158`, `cli/app.py:197`, `cli/knowledge/commands/create.py:253`, `cli/knowledge/commands/search.py:44`, `cli/composition.py:24,32,40`, `cli/init.py:57`, `config/commands/get.py:84` (the last is already inside `check_imports.py`'s existing CLI-layer `EXEMPT`/`_EXEMPT_DIRS` mechanism for `config/commands/`, so it needs no import-graph fix, only the `CoreEngineConfig` relocation everything else in Task 9 already requires).

Task 9 below fixes all of them and turns on real enforcement: every non-composition-root site is routed through a new lazy facade re-export module (`core/facade_config.py`), `cli/composition.py` gets a principled `EXEMPT` entry (it is the one place in the app whose entire job is to know every concrete v1/v2 type — the composition-root pattern, same justification `config/cli.py` already has), and `check_imports.py` gains a real `cli`/`mcp` → `core.v1`/`core.v2` deep rule (mirroring the existing `core/v2 ↛ core.v1` deep rule) so a *new* violation is caught by CI going forward, not just today's list fixed once.

## Task 9: Enforce the facade import boundary for cli/mcp (full fix)

**Files:**
- Modify: `src/indexed/core/v1/config_models.py` (remove `CoreEngineConfig` class only — everything else in the file is untouched)
- Create: `src/indexed/core/facade_config.py`
- Modify: `src/indexed/cli/composition.py` (import `CoreEngineConfig` from the new location)
- Modify: `src/indexed/config/commands/get.py:84` (same)
- Modify: `src/indexed/mcp/server.py:17` (import `CoreV1SearchConfig`, `MCPConfig` from `core.facade_config`)
- Modify: `src/indexed/mcp/cli.py:158` (import `MCPConfig` from `core.facade_config`)
- Modify: `src/indexed/cli/app.py:197` (import `DEFAULT_INDEXER` from `core.facade_config`)
- Modify: `src/indexed/cli/knowledge/commands/create.py:253` (same)
- Modify: `src/indexed/cli/knowledge/commands/search.py:44` (import `CoreV1SearchConfig` from `core.facade_config`)
- Modify: `src/indexed/cli/init.py:57` (import `DEFAULT_MODEL`, `ensure_model`, `get_cache_info`, `is_model_cached` from `core.facade_config`)
- Modify: `scripts/check_imports.py` (add `composition.py` to `EXEMPT`; add the new `cli`/`mcp` deep rule)
- Test: `tests/characterization/test_import_graph.py`, `tests/unit/indexed/test_engine_selector.py`

**Interfaces:**
- Produces: `indexed.core.facade_config` — `CoreEngineConfig` (moved, same fields/validator) as a real class, plus a **lazy** `__getattr__` re-export (mirroring `core.engine`'s own pattern) for `CoreV1SearchConfig`, `MCPConfig`, `DEFAULT_INDEXER`, `DEFAULT_MODEL`, `ensure_model`, `get_cache_info`, `is_model_cached` — each a straight v1 pass-through, nothing imported until first attribute access, so importing `core.facade_config` for one symbol never pays for another's import chain (e.g. `mcp/server.py` importing `MCPConfig` never triggers the embedding-model-manager chain `cli/init.py` needs).
- Consumes: nothing new from other tasks.

- [ ] **Step 1: Write the failing tests**

Add to `tests/characterization/test_import_graph.py`, mirroring `test_core_importing_cli_is_a_violation`:

```python
def test_cli_composition_root_is_exempt_from_core_v1_v2_purity(tmp_path: Path) -> None:
    """issue #186: the app composition root legitimately wires concrete v1/v2
    config classes by construction — it must stay exempt from the generic
    core.v1/core.v2 purity rule the way config/cli.py already is."""
    checker = _load_checker()
    assert checker._is_exempt(Path("cli") / "composition.py")


def test_mcp_importing_core_v1_directly_is_a_violation(tmp_path: Path) -> None:
    """issue #186: cli/mcp may import the facade (core.engine/.errors/
    .versioning/.facade_config) but never core.v1/core.v2 internals directly."""
    checker = _load_checker()
    src = tmp_path / "src" / "indexed"
    mcp_dir = src / "mcp"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "server.py").write_text(
        "from indexed.core.v1.config_models import MCPConfig\n"
    )

    violations = checker.check(src)
    assert violations, "expected a violation for mcp -> core.v1, got none"
    assert any("must not import indexed.core.v1" in v for v in violations)


def test_cli_importing_core_facade_is_not_a_violation(tmp_path: Path) -> None:
    """The facade itself (core.engine, core.facade_config, ...) stays legal —
    only core.v1.*/core.v2.* internals are forbidden from cli/mcp."""
    checker = _load_checker()
    src = tmp_path / "src" / "indexed"
    cli_dir = src / "cli"
    cli_dir.mkdir(parents=True)
    (cli_dir / "app.py").write_text(
        "from indexed.core.engine import search\n"
        "from indexed.core.facade_config import MCPConfig\n"
    )

    violations = checker.check(src)
    assert violations == []
```

Also add to `tests/unit/indexed/test_engine_selector.py` (grep first: `grep -n "CoreEngineConfig" tests/unit/indexed/test_engine_selector.py` — the investigation found 4 import sites there to update in Step 4):

```python
def test_core_engine_config_lives_in_facade_config_not_v1() -> None:
    """issue #186: CoreEngineConfig is facade-level [core] engine selection,
    not v1 engine internals — it must not live inside the frozen v1 package."""
    from indexed.core.facade_config import CoreEngineConfig

    assert CoreEngineConfig().engine == "1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/characterization/test_import_graph.py tests/unit/indexed/test_engine_selector.py -k "composition_root or core_v1_directly or core_facade_is_not or facade_config" -v`
Expected: `test_cli_composition_root_is_exempt_from_core_v1_v2_purity` FAILS (not yet in `EXEMPT`); `test_mcp_importing_core_v1_directly_is_a_violation` FAILS (no such rule exists yet — `violations == []`); `test_cli_importing_core_facade_is_not_a_violation` PASSES already (nothing forbids it today, vacuously true — it'll stay passing once the new rule exists too, since it doesn't test compliance with anything absent yet); `test_core_engine_config_lives_in_facade_config_not_v1` FAILS with `ModuleNotFoundError`.

- [ ] **Step 3: Create `core/facade_config.py`**

Read the FULL current `CoreEngineConfig` class body in `src/indexed/core/v1/config_models.py` first (starts at line 136 — the class continues past what planning excerpted, read to its actual end before moving it verbatim). Create `src/indexed/core/facade_config.py`:

```python
"""Facade-level configuration + re-exported utility surface (issue #186).

CoreEngineConfig ([core] engine) selects the default engine for NEW
collections; it lives here (not inside core.v1, which stays frozen).

The lazy re-exports below (mirroring core.engine's own __getattr__ pattern)
let cli/mcp reference v1 config-model types and small utility
constants/functions without importing core.v1.*/core.v2.* directly anywhere
in their own files — satisfying .spec/tech.md's "no code above the facade
may import core.v1.*/core.v2.* directly" contract in FULL, not just for
CoreEngineConfig. Each is a straight v1 pass-through (v1 is the only engine
with these today, e.g. the embedding model-cache manager); nothing is
imported until first accessed, so a consumer that only needs CoreEngineConfig
never pays for the model-manager import chain, and vice versa.
"""

from __future__ import annotations

import importlib
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CoreEngineConfig(BaseModel):
    # ... (moved verbatim from core/v1/config_models.py — same docstring,
    # same `engine` field, same `_check_engine_value` validator)
    ...


_REEXPORTS: dict[str, str] = {
    "CoreV1SearchConfig": "indexed.core.v1.config_models",
    "MCPConfig": "indexed.core.v1.config_models",
    "DEFAULT_INDEXER": "indexed.core.v1.constants",
    "DEFAULT_MODEL": "indexed.core.v1.engine.indexes.embeddings.model_manager",
    "ensure_model": "indexed.core.v1.engine.indexes.embeddings.model_manager",
    "get_cache_info": "indexed.core.v1.engine.indexes.embeddings.model_manager",
    "is_model_cached": "indexed.core.v1.engine.indexes.embeddings.model_manager",
}


def __getattr__(name: str) -> Any:
    module_path = _REEXPORTS.get(name)
    if module_path is None:
        raise AttributeError(
            f"module 'indexed.core.facade_config' has no attribute {name!r}"
        )
    return getattr(importlib.import_module(module_path), name)


def __dir__() -> list[str]:
    return sorted(["CoreEngineConfig", *_REEXPORTS])


__all__ = ["CoreEngineConfig", *sorted(_REEXPORTS)]
```

Move the `CoreEngineConfig` class body verbatim (do not change any field, validator, or docstring text — only its module location).

- [ ] **Step 4: Update every caller to import through the facade**

Delete the `CoreEngineConfig` class from `src/indexed/core/v1/config_models.py` (nothing else in that file changes).

`src/indexed/cli/composition.py` (lines 32-39): remove `CoreEngineConfig` from the `core.v1.config_models` import list and add a separate import:

```python
    from indexed.core.facade_config import CoreEngineConfig
    from indexed.core.v1.config_models import (
        CoreV1EmbeddingConfig,
        CoreV1IndexingConfig,
        CoreV1SearchConfig,
        CoreV1StorageConfig,
        MCPConfig,
    )
```

`src/indexed/config/commands/get.py:84`: `from indexed.core.v1.config_models import CoreEngineConfig` → `from indexed.core.facade_config import CoreEngineConfig`.

`src/indexed/mcp/server.py:17`: `from indexed.core.v1.config_models import CoreV1SearchConfig, MCPConfig` → `from indexed.core.facade_config import CoreV1SearchConfig, MCPConfig`.

`src/indexed/mcp/cli.py:158`: `from indexed.core.v1.config_models import MCPConfig` → `from indexed.core.facade_config import MCPConfig`.

`src/indexed/cli/app.py:197` (inside `__getattr__`): `from indexed.core.v1.constants import DEFAULT_INDEXER` → `from indexed.core.facade_config import DEFAULT_INDEXER`.

`src/indexed/cli/knowledge/commands/create.py:253` (inside `__getattr__`): same change as `app.py`.

`src/indexed/cli/knowledge/commands/search.py:44`: `from indexed.core.v1.config_models import CoreV1SearchConfig` → `from indexed.core.facade_config import CoreV1SearchConfig`.

`src/indexed/cli/init.py:57`: `from indexed.core.v1.engine.indexes.embeddings.model_manager import (DEFAULT_MODEL, ensure_model, get_cache_info, is_model_cached)` → `from indexed.core.facade_config import (DEFAULT_MODEL, ensure_model, get_cache_info, is_model_cached)`.

`tests/unit/indexed/test_engine_selector.py`: update its 4 `CoreEngineConfig` import sites from `core.v1.config_models` to `core.facade_config`.

- [ ] **Step 5: Wire the new rule into `check_imports.py`**

Change `EXEMPT`:

```python
EXEMPT = frozenset({Path("config") / "cli.py", Path("cli") / "composition.py"})
```

Update the comment above it to name `composition.py`'s justification too (the app composition root wires every concrete layer together by construction — that's its entire, sole purpose, per its own module docstring; every OTHER cli/mcp file must go through the facade, which is what the new rule below now actually enforces).

Add a new deep-check function, right after `_v2_imports_v1`:

```python
def _app_layer_imports_core_v1_v2(tree: ast.AST) -> list[tuple[int, str]]:
    """Yield (lineno, module) for a cli/mcp file importing indexed.core.v1.*
    or indexed.core.v2.* directly — forbidden (issue #186; .spec/tech.md "no
    code above the facade may import core.v1.*/core.v2.* directly"). The
    facade itself (core.engine, core.errors, core.versioning,
    core.facade_config) stays legal — only the v1/v2-internals dotted prefix
    is checked, mirroring _v2_imports_v1's shape for the same reason: the
    generic single-level FORBIDDEN dict can't see the v1/v2 split."""
    hits: list[tuple[int, str]] = []
    for lineno, mod in _imported_modules(tree):
        if mod.startswith("indexed.core.v1") or mod.startswith("indexed.core.v2"):
            hits.append((lineno, mod))
    return hits
```

Restructure `check()` so the deep per-source checks run independent of whether the generic `FORBIDDEN` bucket is empty for `source_sub` (today `cli`/`mcp` have no generic entry at all, so the existing `if not forbidden: continue` early-return would skip them before ever reaching a new check gated after it):

```python
def check(src: Path = SRC) -> list[str]:
    violations: list[str] = []
    for path in sorted(src.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(src)
        if len(rel.parts) < 2:  # top-level module (e.g. __init__.py)
            continue
        if _is_exempt(rel):  # merged CLI command living inside a package dir
            continue
        source_sub = rel.parts[0]
        try:
            display = path.relative_to(ROOT)
        except ValueError:  # src outside the repo (e.g. a tmp tree in tests)
            display = path.relative_to(src)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        forbidden = FORBIDDEN.get(source_sub)
        if forbidden:
            for lineno, target in _imported_subpackages(tree):
                if target in forbidden:
                    violations.append(
                        f"{display}:{lineno}: {source_sub} must not import {target}"
                    )

        # Deeper edge: core/v2 must not import core.v1 (the generic 'core'
        # bucket rule above can't see the v1/v2 split).
        if source_sub == "core" and rel.parts[1] == "v2":
            for lineno, mod in _v2_imports_v1(tree):
                violations.append(
                    f"{display}:{lineno}: core/v2 must not import {mod} (v2 ↛ core.v1)"
                )

        # Deeper edge: cli/mcp must not import core.v1/core.v2 directly —
        # only the facade (core.engine/.errors/.versioning/.facade_config).
        if source_sub in _UP:
            for lineno, mod in _app_layer_imports_core_v1_v2(tree):
                violations.append(
                    f"{display}:{lineno}: {source_sub} must not import {mod} directly (use the core facade)"
                )
    return violations
```

Extend `_self_test()` with one more synthetic check, after the existing v2↛v1 assertions and before the final `print(...)`:

```python
    # cli/mcp ↛ core.v1/core.v2: a synthetic mcp file importing core.v1 IS caught...
    app_bad = ast.parse("from indexed.core.v1.config_models import MCPConfig\n")
    if len(_app_layer_imports_core_v1_v2(app_bad)) != 1:
        print(
            f"SELF-TEST FAILED: mcp->core.v1 caught "
            f"{_app_layer_imports_core_v1_v2(app_bad)}, expected 1",
            file=sys.stderr,
        )
        return 1
    # ...while importing the facade itself is NOT flagged.
    app_ok = ast.parse(
        "from indexed.core.engine import search\n"
        "from indexed.core.facade_config import MCPConfig\n"
    )
    if _app_layer_imports_core_v1_v2(app_ok):
        print(
            f"SELF-TEST FAILED: legal facade import flagged: "
            f"{_app_layer_imports_core_v1_v2(app_ok)}",
            file=sys.stderr,
        )
        return 1
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/characterization/test_import_graph.py tests/unit/indexed/test_engine_selector.py -v`
Expected: PASS, including `test_check_imports_function_reports_no_violations` against the REAL tree — this is the one that proves every one of the 8 non-composition sites was actually fixed (not just the synthetic tests). Then:

```bash
uv run python scripts/check_imports.py --self-test
uv run python scripts/check_imports.py
```

Both must exit 0. Then run the full unit suite for every file touched: `uv run pytest tests/unit/ -v -k "engine_selector or composition or config_models or mcp or app or init or create or search"` and `uv run ty check src/indexed` (the `core.facade_config` lazy `__getattr__` re-exports are untyped at the attribute level — if `ty` flags any of the 8 call sites for an unresolved import, add explicit `TYPE_CHECKING`-only re-imports in `facade_config.py` mirroring `core.engine`'s own `if TYPE_CHECKING:` block at the bottom of that file, listing the same 7 re-exported names so type-checkers can see them statically).

- [ ] **Step 7: Commit**

```bash
git add src/indexed/core/facade_config.py src/indexed/core/v1/config_models.py src/indexed/cli/composition.py src/indexed/config/commands/get.py src/indexed/mcp/server.py src/indexed/mcp/cli.py src/indexed/cli/app.py src/indexed/cli/knowledge/commands/create.py src/indexed/cli/knowledge/commands/search.py src/indexed/cli/init.py scripts/check_imports.py tests/characterization/test_import_graph.py tests/unit/indexed/test_engine_selector.py
git commit -m "refactor(core): enforce facade-only imports for cli/mcp"
```

---

## Task 10: Whole-branch verification, spec sync, and the PR

**Files:**
- Modify: `.spec/tech-core.md` and/or `.spec/tech.md` (if either documents `CoreEngineConfig`'s old location — grep first)
- Modify: `.spec/lessons.md` (append one compounded lesson)

**Interfaces:** none — this task is verification + documentation + the PR, not code.

- [ ] **Step 1: Full local gate**

```bash
uv run ruff check
uv run ty check src/indexed
uv run python scripts/check_imports.py
uv run pytest tests/unit/ --cov=indexed --cov-branch --cov-report=term-missing --cov-fail-under=85 -v
```

All four must pass clean. If coverage dropped below 85%, add tests for whatever branch is uncovered (most likely: the new `except ConfigValidationError: raise` re-raise branches in Task 2, or the residual-trash branch in Task 4 — both are already covered by the tests written in those tasks, so this should not trigger).

- [ ] **Step 2: Spec sync**

```bash
grep -rn "CoreEngineConfig" .spec/tech.md .spec/tech-core.md .spec/tech-app.md
```

For any hit that names `core/v1/config_models.py` as `CoreEngineConfig`'s location, update it to `core/facade_config.py` and bump that file's `updated:` frontmatter date to today.

- [ ] **Step 3: Compound one lesson**

Append to `.spec/lessons.md` (new entry, following the file's existing format — a dated `##` heading + bullet points), covering the load-bearing pattern from this batch: a resolver's `except Exception: return Default()` needs to distinguish "can't read/unregistered" (degrade) from "read fine, value is invalid" (fail loud) — the same split `resolve_engine_selector` already established — and that a single verbatim-duplicated helper is best fixed by extraction to a leaf `utils` module when the logic has no layer-specific dependency, rather than fixing one copy and leaving the other to drift further (as the docstrings already had, independently, before any code drifted).

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin claude/issue-186-planning-5wvcm4
```

Open the PR with `mcp__github__create_pull_request` (title referencing issue #186, body listing all 9 fixes with their task numbers, `Closes #186` in the description) against `main`. Check for a PR template first (`.github/pull_request_template.md` or similar) and follow it if present.

---

## Self-Review

**Spec coverage:** all 9 issue bullets map to a task via the Requirements Trace table above — Task 7 covers 3 of them (the scale-mixing and score_kind sub-bugs, plus the separate dedup finding, since all three live in the same duplicated function pair). No bullet is unaddressed.

**Placeholder scan:** every step above contains real, current-code-grounded before/after code (all line numbers and function bodies were re-read live from the repository during planning, not copied from the original stale review) — no "TBD"/"add appropriate handling"/"similar to Task N" placeholders. Task 9's Step 3 is the one step that says "read the file first" rather than pasting the full class body verbatim; that's because the plan's own investigation truncated it — the executor must read it before moving it, not skip understanding it.

**Type/interface consistency:** `unified_relevance(raw_score: float, score_kind: str) -> float` is the one signature introduced in Task 7 and used identically in both call sites (`mcp/formatting.py`'s `_rank_chunks`, `search_render.py`'s `_sort_key`) — verified both were updated to pass the string, not the old boolean. `CoreEngineConfig` (Task 9) keeps its exact field/validator shape; only its module path changes, verified at every one of its 6 known reference sites (composition.py, config/commands/get.py, test_engine_selector.py x4). Task 9's other 8 new `core.facade_config` call sites each import a *different* symbol (`CoreV1SearchConfig`/`MCPConfig`/`DEFAULT_INDEXER`/`DEFAULT_MODEL`/`ensure_model`/`get_cache_info`/`is_model_cached`) from the *same* module — verified `_REEXPORTS` in Step 3 lists all 7, and Step 4 updates every one of the 6 files that need them (`mcp/server.py` needs 2 of the 7 in one import line).
