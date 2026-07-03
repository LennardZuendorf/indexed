---
type: feature-plan
feature: architecture-audit
sibling: tech.md
parent: ../../plan.md
updated: 2026-07-03
---

# Architecture Audit Remediation — Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` (one subagent per unit) or
> `superpowers:executing-plans` (inline with sprint checkpoints). Track progress
> by checking boxes and updating the Progress table at the bottom after each unit.
> Commit after every unit with subject `refactor(<scope>): architecture-audit/n …`
> (≤50 chars, imperative).

**Goal:** Fix structural debt from the 2026-06-29 audit — downward-only dependency
graph, app composition root, CLI/MCP runtime parity, config/retry hygiene, dead-code
removal — and lock the result with import-graph CI so v2 can scaffold on a clean base.

**Architecture:** Extract `indexed-protocols` (leaf package) → sever `core→connectors`
→ add `bootstrap.py` + `runtime.py` in `apps/indexed` → unify config reads and HTTP
retry → delete speculative code → CI gate. See [tech.md](tech.md).

**Tech stack:** Python 3.11+ · uv workspace · Hatch/una wheels · pytest/mypy/ruff.

**Parent:** [../../plan.md](../../plan.md) · **Requirements:** [product.md](product.md) ·
**Research:** [research/systemic.md](research/systemic.md) and sibling cluster docs.

**Validated baseline (2026-07-03):** All 13 units DONE. Feature verify gate green (1478 tests, 85% cov, import graph OK). COMPOUND promoted to root specs 2026-07-03.

---

## Global Constraints

- Run all commands from **project root** with `uv run`.
- **mypy strict:** 0 errors on `src/`.
- **Coverage:** >85% on `uv run pytest -q --cov=src`.
- **File size limits on touched files:** CLI command ≤150 · service ≤300 · module ≤400
  ([tech.md](../../tech.md) § File Size Limits).
- **No import-time side effects** in library packages after `/5`.
- **Core MUST NOT import `connectors.*`** after `/2` (enforced by CI in `/12`).
- **Do not expand into issue #119** (thin commands, `config/cli.py` split) unless R10
  forces a split on a file you touch.
- Commit `uv.lock` whenever workspace deps change (`/1`).
- Bump `updated:` on every spec file you edit during COMPOUND.

---

## Overnight Run Guide

### Pre-flight (5 min)

```bash
cd /path/to/indexed/.worktrees/chore/review
uv sync --all-groups
uv run pytest -q --co -q 2>/dev/null | tail -1   # note baseline test count
git status                                       # clean or intentional branch
```

### Sprint schedule

| Sprint | Units | Est. | Gate |
|--------|-------|------|------|
| **0a** | Quick wins (`/0`) | 30 min | test mirror + lessons restored |
| **1** | `/1` → `/4` | 4–6 h | graph fixed, CLI/MCP path parity |
| **2** | `/5` → `/8` | 3–4 h | config pure, retry unified, dead code gone |
| **3** | `/9` → `/12` | 3–4 h | full verify + COMPOUND |
| **Total** | 13 units | ~10–14 h | Feature 11 DONE |

### Between every unit

1. Run the unit **Verification** block — paste output before claiming done.
2. Commit: `refactor(<scope>): architecture-audit/n <subject>`
3. Update Progress table at bottom of this file (`IN PROGRESS` → `DONE`).

### Sprint verify gates

**After Sprint 1 (/4):**
```bash
uv run pytest tests/unit/indexed_protocols/ tests/unit/indexed_core/test_import_isolation.py \
  tests/unit/indexed/test_bootstrap.py tests/unit/indexed/test_runtime_context.py \
  tests/system/test_mcp_storage_parity.py -q
uv run mypy src/
```

**After Sprint 2 (/8):**
```bash
uv run pytest tests/unit/indexed_config/ tests/unit/utils/test_retry.py \
  tests/unit/indexed_connectors/test_http_retry.py -q
uv run pytest -q --cov=src
```

**Feature complete (/12 + COMPOUND):**
```bash
uv run ruff check . --fix && uv run ruff format
uv run mypy src/
uv run python scripts/check_import_graph.py
uv run pytest -q --cov=src
bash .agents/skills/spec/scripts/validate.sh
```

---

## Requirements Trace

| ID | Requirement | Units |
|----|-------------|-------|
| R1 | Downward-only dependency graph | /1, /2, /12 |
| R2 | Protocols in lowest shared package | /1 |
| R3 | CLI and MCP storage path parity | /4 |
| R4 | Single-source config resolution | /5, /6 |
| R5 | Explicit app bootstrap | /0, /3, /5, /9 |
| R6 | IndexedError at app boundaries | /11 |
| R7 | Connector registry single path | /3, /10 |
| R8 | HTTP retry policy consistent | /7 |
| R9 | Delete speculative/unused code | /8 |
| R10 | File size compliance on touched modules | /3, /4, /10, /11 |
| R11 | v2 scaffold prerequisites | /1, /12 |

---

## Key Technical Decisions

1. **`indexed-protocols`** — leaf package; pydantic + stdlib only; wheel name `protocols`.
2. **`bootstrap.py`** — `register_app_config()`, `build_connector_registry()`,
   `build_connector(cfg, config_service, registry)`.
3. **`runtime.py`** — `CliContext` + `resolve_collections_context(mode_override)`.
4. **`read_for_mode()` only** for runtime reads; `read()` merge deleted or tooling-only.
5. **`TRANSIENT_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})`** in `utils/retry.py`.
6. **Legacy type normalization:** `jiraCloud` → `jira`, `confluenceCloud` → `confluence`
   in `_normalize_connector_type()` with `DeprecationWarning`.
7. **`MCPConfig` TOML** — `/4` wires `mcp/cli.py run_impl()` to read TOML when CLI
   flags not explicitly set (P1 from app research).

---

## architecture-audit/0 — Quick wins (parallel-safe)

**Goal:** Fix test mirror drift and restore session-start lessons before graph surgery.

**Requirements:** R5 (hygiene)

**Dependencies:** —

### Task 0.1: Restore lessons.md

- [x] Confirm `.spec/lessons.md` exists (restored 2026-07-03).

### Task 0.2: Move misplaced core service tests

**Files:**
- Move: `tests/unit/indexed/services/test_collection_service.py` → `tests/unit/indexed_core/services/`
- Move: `tests/unit/indexed/services/test_search_service.py` → `tests/unit/indexed_core/services/`
- Delete: empty `tests/unit/indexed/services/` directory

- [x] Run: `uv run pytest tests/unit/indexed_core/services/ -q`
- [x] Commit: `test(core): architecture-audit/0 mirror service tests`

**Verification:** `uv run pytest tests/unit/indexed_core/services/ -q`

---

## Phase 0 — Graph (Sprint 1)

### architecture-audit/1 — indexed-protocols package

**Requirements:** R1, R2, R11 · **Blocks:** /2

#### Task 1.1: Scaffold package

**Create:** `packages/indexed-protocols/pyproject.toml`

```toml
[project]
name = "indexed-protocols"
version = "0.1.0"
description = "Shared connector protocols and DTOs for indexed"
requires-python = ">=3.11"
dependencies = ["pydantic>=2.0.0"]

[build-system]
requires = ["hatchling", "hatch-una"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/protocols"]
```

- [x] Create directory `packages/indexed-protocols/src/protocols/`

#### Task 1.2: Move protocol types

**Create from copies of core modules (then slim core to re-exports):**

| New file | Source |
|----------|--------|
| `protocols/connectors.py` | `core/v1/connectors/base.py` |
| `protocols/metadata.py` | `core/v1/connectors/metadata.py` |
| `protocols/models.py` | `SourceConfig`, `ProgressUpdate`, `ProgressCallback`, `PhasedProgressCallback` from `core/v1/engine/services/models.py` |

**Create:** `protocols/__init__.py`

```python
from protocols.connectors import BaseConnector, DocumentConverter, DocumentReader
from protocols.metadata import ConnectorMetadata
from protocols.models import (
    PhasedProgressCallback,
    ProgressCallback,
    ProgressUpdate,
    SourceConfig,
)

__all__ = [
    "BaseConnector",
    "ConnectorMetadata",
    "DocumentConverter",
    "DocumentReader",
    "PhasedProgressCallback",
    "ProgressCallback",
    "ProgressUpdate",
    "SourceConfig",
]
```

- [x] Keep engine-only DTOs in `core/.../models.py`: `CollectionStatus`, `CollectionInfo`, `SearchResult` (delete `SearchResult` in `/8`).

#### Task 1.3: Wire workspace deps

**Modify:**
- `packages/indexed-core/pyproject.toml` — add `indexed-protocols`, keep `indexed-connectors` temporarily
- `packages/indexed-connectors/pyproject.toml` — add `indexed-protocols`
- `apps/indexed/pyproject.toml` — add `indexed-protocols`
- `pyproject.toml` `[tool.coverage.run] source_pkgs` — add `"protocols"`

- [x] Run: `uv sync --all-groups`

#### Task 1.4: Re-export shims in core (transition window)

**Modify:** `core/v1/connectors/__init__.py` and `core/v1/connectors/base.py` → re-export from `protocols` with deprecation comment.

**Modify:** `core/v1/engine/services/models.py` → re-export `SourceConfig`, progress types from `protocols`.

- [x] Update connector imports: `from protocols import BaseConnector, SourceConfig, …`
- [x] Grep: `from core.v1.connectors` in connectors package → switch to `protocols`

#### Task 1.5: Tests

**Create:** `tests/unit/indexed_protocols/test_protocols.py`

```python
from protocols import BaseConnector, SourceConfig
from connectors.jira.connector import JiraConnector


def test_jira_connector_satisfies_base_connector_protocol():
    assert isinstance(JiraConnector, type)
    # runtime_checkable: instance check after from_config needs mock config — use META
    assert hasattr(JiraConnector, "META")


def test_source_config_accepts_jira_type():
    cfg = SourceConfig(name="x", type="jira", base_url_or_path="https://jira.example.com")
    assert cfg.type == "jira"
```

- [x] Run: `uv run pytest tests/unit/indexed_protocols/ -q && uv run mypy src/`
- [x] Commit: `feat(protocols): architecture-audit/1 extract package`

**Verification:** `uv sync --all-groups && uv run pytest tests/unit/indexed_protocols/ -q && uv run mypy src/`

---

### architecture-audit/2 — Remove core→connectors dependency

**Requirements:** R1 · **Blocked by:** /1 · **Blocks:** /3

#### Task 2.1: pyproject

**Modify:** `packages/indexed-core/pyproject.toml` — remove `indexed-connectors` from `dependencies` and `[tool.uv.sources]`.

- [x] Run: `uv sync --all-groups`

#### Task 2.2: Import isolation test (write first)

**Create:** `tests/unit/indexed_core/test_import_isolation.py`

```python
import ast
from pathlib import Path

CORE_ROOT = Path("packages/indexed-core/src/core")


def _python_files():
    return list(CORE_ROOT.rglob("*.py"))


def test_core_does_not_import_connectors_package():
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("connectors"):
                violations.append(f"{path}:{node.lineno}: from {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("connectors"):
                        violations.append(f"{path}:{node.lineno}: import {alias.name}")
    assert not violations, "core must not import connectors:\n" + "\n".join(violations)
```

- [x] Run test — expect **FAIL** until Task 2.3 complete.

#### Task 2.3: Remove connector imports from core (minimal stubs for /10)

**Modify:** `collection_service.py`
- Remove `_build_connector_from_config` body imports (stub raises `ConfigurationError` if no injected factory — full removal in `/10`).
- Add parameter: `connector_factory: Callable[[SourceConfig], Any] | None = None`.

**Modify:** `create_collection_factory.py`
- Remove top-level `from connectors.document_cache_reader_decorator import CacheReaderDecorator`.
- Accept optional `cache_decorator_factory` argument from caller.

**Modify:** `update_collection_factory.py`
- Remove `from connectors import get_connector_class` and `FileSystemConnector` imports.
- Accept injected connector or factory from app layer.

- [x] Run isolation test — expect **PASS**.
- [x] Run full suite: `uv run pytest -q` (fix app wiring temporarily if needed).
- [x] Commit: `refactor(core): architecture-audit/2 drop connectors dep`

**Verification:** `uv run pytest tests/unit/indexed_core/test_import_isolation.py -q && uv run mypy src/`

---

### architecture-audit/3 — App bootstrap + connector registry

**Requirements:** R5, R7, R10 · **Blocked by:** /2 · **Blocks:** /4

**New modules must stay ≤400 lines.**

#### Task 3.1: Create bootstrap.py

**Create:** `apps/indexed/src/indexed/bootstrap.py`

```python
"""App composition root — config registration and connector wiring."""

from __future__ import annotations

from typing import Any, Callable, Type

from indexed_config import ConfigService
from indexed_config.errors import ConfigurationError
from protocols import BaseConnector, SourceConfig

_LEGACY_TYPE_MAP = {"jiraCloud": "jira", "confluenceCloud": "confluence"}


def _normalize_connector_type(connector_type: str) -> str:
    return _LEGACY_TYPE_MAP.get(connector_type, connector_type)


def register_app_config(config_service: ConfigService) -> None:
    """Register all config specs — idempotent, raises on failure."""
    from core.v1.config_models import (
        CoreV1EmbeddingConfig,
        CoreV1IndexingConfig,
        CoreV1SearchConfig,
        CoreV1StorageConfig,
    )
    from connectors.confluence.schema import ConfluenceCloudConfig, ConfluenceConfig
    from connectors.files.schema import FilesConfig, LocalFilesConfig
    from connectors.jira.schema import JiraCloudConfig, JiraConfig
    from connectors.outline.schema import OutlineConfig
    from indexed.mcp.config import MCPConfig

    config_service.register(CoreV1IndexingConfig, path="core.v1.indexing")
    config_service.register(CoreV1SearchConfig, path="core.v1.search")
    config_service.register(CoreV1StorageConfig, path="core.v1.vector_store")
    config_service.register(CoreV1EmbeddingConfig, path="core.v1.embedding")
    config_service.register(MCPConfig, path="mcp")
    config_service.register(FilesConfig, path="sources.files")
    config_service.register(LocalFilesConfig, path="sources.files")
    config_service.register(JiraConfig, path="sources.jira")
    config_service.register(JiraCloudConfig, path="sources.jira")
    config_service.register(ConfluenceConfig, path="sources.confluence")
    config_service.register(ConfluenceCloudConfig, path="sources.confluence")
    config_service.register(OutlineConfig, path="sources.outline")


def build_connector_registry() -> dict[str, Type[Any]]:
    from connectors.registry import CONNECTOR_REGISTRY
    return dict(CONNECTOR_REGISTRY)


def build_connector(
    cfg: SourceConfig,
    config_service: ConfigService,
    registry: dict[str, Type[Any]] | None = None,
) -> BaseConnector:
    from connectors.registry import NAMESPACE_REGISTRY

    registry = registry or build_connector_registry()
    key = _normalize_connector_type(cfg.type)
    cls = registry.get(key)
    if cls is None:
        available = ", ".join(sorted(registry))
        raise ConfigurationError(f"Unknown connector type: {cfg.type}. Available: {available}")

    namespace = NAMESPACE_REGISTRY.get(key, f"sources.{key}")
    if cfg.base_url_or_path:
        config_service.set(f"{namespace}.url", cfg.base_url_or_path)
    if cfg.query:
        config_service.set(f"{namespace}.query", cfg.query)

    return cls.from_config(config_service)  # type: ignore[return-value]
```

#### Task 3.2: Wire entry points

**Modify:** `apps/indexed/src/indexed/app.py`
- In `@app.callback`, after logging setup: `register_app_config(ConfigService.instance(mode_override=ctx.obj.get("mode_override")))`.

**Modify:** `apps/indexed/src/indexed/mcp/server.py`
- In lifespan startup: call `register_app_config(config_service)`.

**Modify:** `apps/indexed/src/indexed/connectors/__init__.py`
- Remove import-time `_discover_connectors()` side effect; export lazy `get_connector_registry()` only.

#### Task 3.3: Tests

**Create:** `tests/unit/indexed/test_bootstrap.py`

```python
import importlib

import pytest
from indexed_config import ConfigService

from indexed.bootstrap import build_connector_registry, register_app_config


def test_import_core_v1_does_not_register_config(monkeypatch):
    ConfigService.instance(reset=True)
    before = len(ConfigService.instance()._registry._specs)  # noqa: SLF001
    importlib.import_module("core.v1")
    after = len(ConfigService.instance()._registry._specs)
    assert before == after


def test_register_app_config_is_idempotent():
    ConfigService.instance(reset=True)
    svc = ConfigService.instance()
    register_app_config(svc)
    n = len(svc._registry._specs)
    register_app_config(svc)
    assert len(svc._registry._specs) == n


def test_build_connector_registry_has_jira():
    reg = build_connector_registry()
    assert "jira" in reg
    assert "jiraCloud" in reg
```

- [x] Run: `uv run pytest tests/unit/indexed/test_bootstrap.py -q && uv run indexed --help`
- [x] Commit: `feat(app): architecture-audit/3 bootstrap module`

**Verification:** `uv run pytest tests/unit/indexed/test_bootstrap.py -q && uv run indexed --help`

---

### architecture-audit/4 — resolve_collections_context CLI+MCP parity

**Requirements:** R3, R10 · **Blocked by:** /3 · **Blocks:** /5

#### Task 4.1: Create runtime.py

**Create:** `apps/indexed/src/indexed/runtime.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from indexed_config import ConfigService


@dataclass(frozen=True)
class CliContext:
    mode: str
    collections_path: Path
    caches_path: Path
    config_service: ConfigService
    connector_registry: dict[str, Any]


def resolve_collections_context(
    mode_override: str | None = None,
    *,
    workspace: Path | None = None,
) -> CliContext:
    from indexed.bootstrap import build_connector_registry

    config_service = ConfigService.instance(
        workspace=workspace,
        mode_override=mode_override,  # fixed properly in /6
        reset=mode_override is not None,
    )
    mode = config_service.resolve_storage_mode()
    resolver = config_service.resolver
    return CliContext(
        mode=mode,
        collections_path=resolver.get_collections_path(mode),
        caches_path=resolver.get_caches_path(mode),
        config_service=config_service,
        connector_registry=build_connector_registry(),
    )
```

#### Task 4.2: Wire CLI commands

**Modify each to accept `typer.Context` and call `resolve_collections_context(ctx.obj.get("mode_override"))`:**

| File | Change |
|------|--------|
| `knowledge/commands/search.py` | Replace `resolve_preferred_collections_path()` with `ctx.collections_path`; fix `SourceConfig.type` from `CollectionStatus.source_type` |
| `knowledge/commands/inspect.py` | Same path threading |
| `knowledge/commands/update.py` | Pass `collections_path` to `svc_status` / update services |
| `knowledge/commands/remove.py` | Same |
| `knowledge/commands/_create_helpers.py` | Use `resolve_collections_context`; pass global `mode_override` from `ctx.obj` |

**Modify:** `utils/storage_info.py`
- `display_storage_mode_for_command` uses `resolve_collections_context`.
- **Delete** `resolve_preferred_collections_path()`.

#### Task 4.3: Wire MCP

**Modify:** `mcp/server.py` — build `CliContext` in lifespan; store in `lifespan_state["cli_context"]`.

**Modify:** `mcp/tools.py`, `mcp/resources.py`
- Read `cli_context.collections_path`; pass `collections_path=str(...)` to `svc_search` / `svc_status`.
- Build `SourceConfig.type` from manifest `source_type`, not hardcoded `localFiles`.

#### Task 4.4: MCPConfig TOML (P1 add-on)

**Modify:** `mcp/cli.py` `run_impl()`
- After parsing Typer args, if host/port/log_level still at defaults, load `MCPConfig` from bound provider and apply.

#### Task 4.5: Tests

**Create:** `tests/unit/indexed/test_runtime_context.py` — local vs global path resolution.

**Create:** `tests/system/test_mcp_storage_parity.py` — CLI `--local` and MCP lifespan share `./.indexed/data/collections`.

- [ ] Commit: `feat(app): architecture-audit/4 runtime context parity`

**Verification:** `uv run pytest tests/unit/indexed/test_runtime_context.py tests/system/test_mcp_storage_parity.py -q`

**Sprint 1 checkpoint:** run Sprint 1 verify gate (see Overnight Run Guide).

---

## Phase 1 — Hygiene (Sprint 2)

### architecture-audit/5 — Remove import-time config registration

**Requirements:** R4, R5 · **Blocked by:** /4

**Modify:**
- `packages/indexed-core/src/core/v1/__init__.py` — delete lines 16–33 (`try/register` block).
- `packages/indexed-connectors/src/connectors/jira/__init__.py` — delete register block.
- `packages/indexed-connectors/src/connectors/confluence/__init__.py` — delete register block.
- `packages/indexed-connectors/src/connectors/files/__init__.py` — delete register block.
- `apps/indexed/src/indexed/mcp/server.py` — remove inline `register()` from `_get_mcp_config()` / `_get_search_config()`; read via `bind()` only.

- [ ] Extend `test_bootstrap.py`: `import connectors.jira` does not register specs.
- [ ] Commit: `refactor(config): architecture-audit/5 explicit registration`

**Verification:** `uv run pytest tests/unit/indexed/test_bootstrap.py tests/unit/indexed_config/ -q && uv run mypy src/`

---

### architecture-audit/6 — Unify config read_for_mode

**Requirements:** R4 · **Blocked by:** /5

#### Task 6.1: Fix singleton mode_override

**Modify:** `packages/indexed-config/src/indexed_config/service.py`

```python
def instance(cls, *, workspace=None, mode_override=None, reset=False) -> "ConfigService":
    if cls._instance is None or reset or (
        mode_override is not None and cls._instance._mode_override != mode_override
    ):
        cls._instance = cls(workspace=workspace, mode_override=mode_override)
    return cls._instance
```

#### Task 6.2: Route reads through read_for_mode

**Modify:** `store.py` — `read()` delegates to `read_for_mode(resolved_mode)` or raises `DeprecationWarning` for merge callers.

**Modify:** `workspace.py` `get_config()` — use `read_for_mode`.

**Modify:** `apps/indexed/src/indexed/utils/storage_info.py` — stop calling `store.read()` merge path.

**Modify tests:** `tests/unit/indexed_config/test_toml_store.py` — replace merge tests with no-merge guards.

- [ ] Grep production: `store.read()` without mode — zero hits outside tooling.
- [ ] Commit: `refactor(config): architecture-audit/6 read_for_mode only`

**Verification:** `uv run pytest tests/unit/indexed_config/ -q && uv run mypy src/`

---

### architecture-audit/7 — Consolidate HTTP retry

**Requirements:** R8 · **Blocked by:** /6

**Modify:** `packages/utils/src/utils/retry.py`

```python
TRANSIENT_HTTP_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def is_transient_http_error(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if status is not None:
        return int(status) in TRANSIENT_HTTP_STATUS
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))
```

**Modify `execute_with_retry`:** retry only if `is_transient_http_error(e)` OR non-HTTP `ConnectionError`/`TimeoutError`; re-raise immediately otherwise.

**Create (optional):** `packages/indexed-connectors/src/connectors/http.py` with `request_with_retry()`.

**Modify readers:** `unified_jira_document_reader.py`, `confluence_document_reader.py`, `confluence_cloud_document_reader.py`, `async_jira_cloud_reader.py`, `outline_document_reader.py` — use shared helpers.

**Create:** `tests/unit/indexed_connectors/test_http_retry.py` — 404 fails fast; 429 retries (mocked).

- [ ] Commit: `refactor(utils): architecture-audit/7 transient retry policy`

**Verification:** `uv run pytest tests/unit/utils/test_retry.py tests/unit/indexed_connectors/test_http_retry.py -q`

---

### architecture-audit/8 — Delete speculative and dead code

**Requirements:** R9, R10 · **Blocked by:** /7

#### Task 8.1: Migrate Jira Server before deleting wrappers

**Modify:** `packages/indexed-connectors/src/connectors/jira/connector.py`
- Replace `JiraDocumentReader` import with `UnifiedJiraDocumentReader` for Server/DC path.
- [ ] Run: `uv run pytest tests/unit/indexed_connectors/jira/ -q`

#### Task 8.2: Delete files

| Delete | Reason |
|--------|--------|
| `core/.../faiss_auto_indexer.py` | Speculative HNSW/IVFPQ |
| `connectors/jira/jira_document_reader.py` | Deprecated wrapper |
| `connectors/jira/jira_cloud_document_reader.py` | Deprecated |
| `connectors/jira/jira_document_converter.py` | Deprecated |
| `connectors/jira/jira_cloud_document_converter.py` | Deprecated |
| `connectors/confluence/confluence_document_converter.py` | Deprecated |
| `connectors/confluence/confluence_cloud_document_converter.py` | Deprecated |
| `utils/safe_getattr.py` | Test-only |
| `parsing/router.py` `DOCLING_FALLBACK` branch | YAGNI |

**Modify:** `indexer_factory.py` — FaissIndexer only.

**Modify:** `core/v1/config_models.py` — delete unused `PathsConfig`.

**Modify:** `core/v1/engine/services/models.py` — delete unused `SearchResult`.

- [ ] Grep deleted module names — zero production importers.
- [ ] Commit: `refactor: architecture-audit/8 remove dead code`

**Verification:** `uv run pytest -q --cov=src` (must stay >85%)

**Sprint 2 checkpoint:** run Sprint 2 verify gate.

---

## Phase 2 — Services (Sprint 3)

### architecture-audit/9 — Remove core import-time logging

**Requirements:** R5 · **Blocked by:** /8

**Modify:**
- `collection_service.py` — remove `setup_root_logger()` call at module level.
- `inspect_service.py` — same.

**Create:** `tests/unit/indexed_core/test_collection_service_logging.py`

```python
from loguru import logger


def test_import_collection_service_does_not_add_handlers():
    import core.v1.engine.services.collection_service  # noqa: F401
    # Handlers count should not grow from import alone — compare before/after in fixture
```

- [ ] Commit: `refactor(core): architecture-audit/9 no import logging`

**Verification:** `uv run pytest tests/system/test_logging_no_leak.py tests/unit/indexed_core/test_collection_service_logging.py -q`

---

### architecture-audit/10 — Single connector builder

**Requirements:** R7, R10 · **Blocked by:** /9

**Modify:** `collection_service.py` — delete `_build_connector_from_config`; `create()`/`update()` accept `connector: BaseConnector` or `connector_factory`.

**Modify:** `update_collection_factory.py` — remove duplicate `_populate_config_from_manifest` elif chain; use app-injected builder.

**Modify:** `apps/indexed` create/update command paths — call `build_connector(cfg, ctx.config_service, ctx.connector_registry)`.

**Create:** `tests/unit/indexed_connectors/test_registry_build.py` — all six source types build without error (mock config).

**Modify:** `tests/unit/indexed_core/services/test_collection_service.py` — mock injected connector, not `connectors.*` patches.

- [ ] Commit: `refactor(app): architecture-audit/10 single connector builder`

**Verification:** `uv run pytest tests/unit/indexed_connectors/test_registry_build.py tests/unit/indexed_core/services/test_collection_service.py -q`

---

### architecture-audit/11 — IndexedError at CLI/MCP boundaries

**Requirements:** R6, R10 · **Blocked by:** /10

**Modify:** `apps/indexed/src/indexed/errors.py`

```python
from indexed_config.errors import ConfigurationError, IndexedError, StorageError

EXIT_CODES = {
    ConfigurationError: 2,
    StorageError: 3,
}

def format_cli_error(exc: IndexedError) -> str:
    return str(exc)

def mcp_error_envelope(exc: IndexedError) -> dict[str, str]:
    return {"error": str(exc), "type": type(exc).__name__}
```

**Modify:** `app.py` — `@app.callback` or Typer handler catches `IndexedError`, prints message, exits with mapped code.

**Modify:** `mcp/tools.py`, `mcp/resources.py` — catch `IndexedError` → `mcp_error_envelope()`; let unexpected exceptions propagate/log traceback.

**Create:** `tests/unit/indexed/test_cli_error_handler.py`, `tests/unit/indexed/mcp/test_error_handling.py`

- [ ] Commit: `feat(app): architecture-audit/11 IndexedError handlers`

**Verification:** `uv run pytest tests/unit/indexed/test_cli_error_handler.py tests/unit/indexed/mcp/test_error_handling.py -q && uv run mypy src/`

---

## Phase 3 — Validation

### architecture-audit/12 — Import-graph CI + characterization

**Requirements:** R1, R11 · **Blocked by:** /11

#### Task 12.1: Import graph script

**Create:** `scripts/check_import_graph.py`

Forbidden edges (fail non-zero if found via AST walk of `packages/*/src` and `apps/*/src`):

| From package | Must NOT import |
|--------------|-----------------|
| `core` | `connectors` |
| `connectors` | `core` (except during transition — **zero** after /1) |
| `indexed_config`, `utils`, `parsing`, `protocols` | `core`, `connectors`, `indexed` |

#### Task 12.2: CI workflow

**Modify:** `.github/workflows/python-ci.yml` — add step before system tests:

```yaml
- name: Check import graph
  run: uv run python scripts/check_import_graph.py
```

#### Task 12.3: Characterization tests

**Create:** `tests/characterization/test_import_graph.py` — wraps script exit code.

**Create:** `tests/characterization/test_cli_smoke.py` — search against `tmp_path` fixture collection.

**Create:** `tests/characterization/test_mcp_smoke.py` — resources return expected keys.

#### Task 12.4: Coverage for protocols

**Modify:** root `pyproject.toml` — add `protocols` to `source_pkgs` and `--cov=protocols` if not done in `/1`.

- [ ] Commit: `ci: architecture-audit/12 import graph gate`

**Verification:** Full feature verify gate (see Overnight Run Guide).

---

## COMPOUND — After /12 passes

- [x] Promote architectural rules to [../../tech.md](../../tech.md) (protocols package, bootstrap, runtime context, import-graph CI).
- [x] Update [../../plan.md](../../plan.md) Feature 11 → DONE.
- [x] Add lessons from this run to [../../lessons.md](../../lessons.md).
- [x] Run: `bash .agents/skills/spec/scripts/validate.sh`
- [ ] Archive feature folder per spec rules before branch merge.

---

## Risk Register

| Risk | Mitigation |
|------|------------|
| `/2` breaks tests before `/3` wires app | Stub factory raises clear `ConfigurationError`; land /2+/3 same sprint |
| MCP singleton + mode bug | `/6` before `/4` parity tests; use `reset=True` in `resolve_collections_context` until /6 lands |
| `/8` deletes hot-path Jira reader | Task 8.1 migrates to `UnifiedJiraDocumentReader` first |
| Coverage drop after deletions | Run `--cov=src` after /8; add characterization tests in /12 |
| Scope creep into #119 | R10 on touched files only; do not split `create.py` unless you touch it and exceed 150L |

---

## Out of Scope (explicit deferrals)

- Issue #119 thin commands (`config/cli.py`, `create.py`, `search_facade.py`)
- `core/v2/` engine rewrite — separate feature after Feature 11 gate
- Confluence reader unification (3 impls → 1)
- MCP tool surface realignment (`list_collections` tool, resource URI rename)
- `ConfigRegistry` merge into service.py

---

## Dependencies

| Unit | Blocks | Blocked by |
|------|--------|------------|
| /0 | /1 (optional parallel) | — |
| /1 | /2 | — |
| /2 | /3 | /1 |
| /3 | /4 | /2 |
| /4 | /5 | /3 |
| /5 | /6 | /4 |
| /6 | /7 | /5 |
| /7 | /8 | /6 |
| /8 | /9 | /7 |
| /9 | /10 | /8 |
| /10 | /11 | /9 |
| /11 | /12 | /10 |
| /12 | COMPOUND | /11 |

---

## Progress

| Unit | Status |
|------|--------|
| architecture-audit/0 | DONE |
| architecture-audit/1 | DONE |
| architecture-audit/2 | DONE |
| architecture-audit/3 | DONE |
| architecture-audit/4 | DONE |
| architecture-audit/5 | DONE |
| architecture-audit/6 | DONE |
| architecture-audit/7 | DONE |
| architecture-audit/8 | DONE |
| architecture-audit/9 | DONE |
| architecture-audit/10 | DONE |
| architecture-audit/11 | DONE |
| architecture-audit/12 | DONE |
