"""App composition root — the single wiring site that binds connectors to core.

This module is the ONLY place the app assembles configuration, the connector
registry, and the two callables the core facade needs:

- ``connector_factory`` (create-time)  — build a connector from a SourceConfig
- ``manifest_factory``  (update-time)  — rebuild a connector from its manifest
  by dispatching to the connector's own ``from_manifest``.

It replaces the former ``bootstrap.py`` + ``runtime.py`` + ``connector_wiring.py``
trio. Connector/core imports stay lazy so CLI startup remains <1s.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Type

from indexed.config import ConfigService, StorageMode, get_config, reload
from indexed.config.errors import ConfigurationError, ConfigValidationError
from indexed.protocols import BaseConnector, ConnectorRun, Manifest, SourceConfig

from indexed.core.v1.engine.persisters.disk_persister import DiskPersister


# --- config registration ------------------------------------------------------


def register_app_config(config_service: ConfigService) -> None:
    """Register all config specs — idempotent, raises on failure."""
    from indexed.core.v1.config_models import (
        CoreEngineConfig,
        CoreV1EmbeddingConfig,
        CoreV1IndexingConfig,
        CoreV1SearchConfig,
        CoreV1StorageConfig,
        MCPConfig,
    )
    from indexed.connectors.confluence.schema import ConfluenceCloudConfig
    from indexed.connectors.files.schema import FileSystemConfig
    from indexed.connectors.jira.schema import JiraCloudConfig
    from indexed.connectors.outline.schema import OutlineConfig

    # ``[core] engine`` — default engine for NEW collections (R3). Registered at
    # path ``core``; the model ignores the ``core.v1.*``/``core.v2.*`` extras.
    config_service.register(CoreEngineConfig, path="core")
    config_service.register(CoreV1IndexingConfig, path="core.v1.indexing")
    config_service.register(CoreV1SearchConfig, path="core.v1.search")
    config_service.register(CoreV1StorageConfig, path="core.v1.storage")
    config_service.register(CoreV1EmbeddingConfig, path="core.v1.embedding")
    config_service.register(MCPConfig, path="mcp")
    config_service.register(FileSystemConfig, path="sources.files")
    config_service.register(JiraCloudConfig, path="sources.jira")
    config_service.register(ConfluenceCloudConfig, path="sources.confluence")
    config_service.register(OutlineConfig, path="sources.outline")


# --- engine selection (R3) ----------------------------------------------------

_DEFAULT_ENGINE = "1"
_ENGINE_ALIASES = {"1": "1", "v1": "1", "2": "2", "v2": "2"}


def normalize_engine_selector(value: str) -> str:
    """Map a user/config engine selector (``1``/``2``/``v1``/``v2``) to ``"1"``/``"2"``."""
    normalized = _ENGINE_ALIASES.get(str(value).strip().lower())
    if normalized is None:
        raise ConfigurationError(
            f"Invalid engine {value!r}; expected one of: 1, 2, v1, v2"
        )
    return normalized


def resolve_engine_selector(flag: str | None, config_service: ConfigService) -> str:
    """Resolve the engine for NEW collections (R3).

    Precedence: ``--engine`` flag > ``INDEXED__CORE__ENGINE`` env >
    ``[core] engine`` in config.toml > built-in default ``"1"``. Env is read
    explicitly (not only via the config merge) so the precedence is
    deterministic.

    A malformed ``[core] engine`` value fails loud (a ``ConfigValidationError``
    for the ``core`` path propagates) so it is NOT silently downgraded to the
    default — consistent with the env path, which validates before this point.
    The default fallback is reserved for the genuinely-absent / unregistered
    case (and any unrelated binding hiccup, which the command surfaces in its own
    context rather than as an engine error).
    """
    if flag is not None:
        return normalize_engine_selector(flag)

    import os

    env_value = os.environ.get("INDEXED__CORE__ENGINE")
    if env_value:
        return normalize_engine_selector(env_value)

    try:
        from indexed.core.v1.config_models import CoreEngineConfig

        cfg = config_service.bind().get(CoreEngineConfig)
        return normalize_engine_selector(cfg.engine)
    except ConfigValidationError as exc:
        # A bad ``[core] engine`` value trips ``CoreEngineConfig``'s validator at
        # ``bind()`` time → ``ConfigValidationError(path="core")``. That must
        # surface (fail loud, consistent with the env path), not be downgraded to
        # the default. An unrelated config error (different path) is not the
        # engine selector's concern — fall through so the invoking command
        # reports it where it belongs.
        if exc.path == "core":
            raise
        return _DEFAULT_ENGINE
    except Exception:
        # Genuinely absent / unregistered ``[core] engine`` (KeyError from the
        # provider) or another binding hiccup → built-in default. A real
        # ``cfg.engine`` is already validated to "1"/"2", so
        # ``normalize_engine_selector`` here only fails for a non-config test
        # double, which correctly falls back.
        return _DEFAULT_ENGINE


# --- connector construction ---------------------------------------------------


def build_connector_registry() -> dict[str, Type[Any]]:
    from indexed.connectors.registry import CONNECTOR_REGISTRY

    return dict(CONNECTOR_REGISTRY)


def build_connector(
    cfg: SourceConfig,
    config_service: ConfigService,
    registry: dict[str, Type[Any]] | None = None,
) -> BaseConnector:
    from indexed.connectors.registry import get_config_namespace

    registry = registry or build_connector_registry()
    cls = registry.get(cfg.type)
    if cls is None:
        available = ", ".join(sorted(registry))
        raise ConfigurationError(
            f"Unknown connector type: {cfg.type}. Available: {available}"
        )

    namespace = get_config_namespace(cfg.type)
    # In-memory overlay only (R3): a failed create must not leave the override
    # on disk (foundation/6b bug E4).
    if cfg.base_url_or_path:
        if cfg.type == "localFiles":
            config_service.set_overlay(f"{namespace}.path", cfg.base_url_or_path)
        else:
            config_service.set_overlay(f"{namespace}.url", cfg.base_url_or_path)
    if cfg.query:
        config_service.set_overlay(f"{namespace}.query", cfg.query)

    connector: BaseConnector = cls.from_config(config_service)
    return connector


# --- runtime context ----------------------------------------------------------


@dataclass(frozen=True)
class CliContext:
    mode: str
    collections_path: Path
    caches_path: Path
    config_service: ConfigService
    # Built lazily on first access (see ``connector_registry``): constructing it
    # imports every connector module, so commands that never touch the registry
    # (search/update/inspect/remove — update dispatches through the
    # ``manifest_factory``/``get_connector_class`` seam instead) don't pay that
    # import cost, keeping CLI startup <1s. ``compare=False`` keeps the cached
    # value out of eq/hash.
    _connector_registry: dict[str, Any] | None = field(default=None, compare=False)

    @property
    def connector_registry(self) -> dict[str, Any]:
        """The connector registry, constructed on first use and then cached."""
        registry = self._connector_registry
        if registry is None:
            registry = build_connector_registry()
            object.__setattr__(self, "_connector_registry", registry)
        return registry


def resolve_collections_context(
    mode_override: StorageMode | None = None,
    *,
    workspace: Path | None = None,
) -> CliContext:
    # A non-None mode_override forces a fresh ConfigService (via reload()) so a
    # runtime global→local switch is honored; get_config() otherwise reuses the
    # cached instance.
    if mode_override is not None:
        reload()
    config_service = get_config(
        workspace=workspace,
        mode_override=mode_override,
    )
    # The reload() above replaces the singleton with a fresh ConfigRegistry
    # whenever a non-None mode_override is passed; re-register here (idempotent)
    # so every caller gets the specs back for free (foundation/6d E12).
    register_app_config(config_service)
    mode = config_service.resolve_storage_mode()
    resolver = config_service.resolver
    # ``connector_registry`` is intentionally omitted: CliContext builds it
    # lazily on first access so commands that never need connectors skip the
    # import cost (startup <1s). Create-time wiring still gets it via the
    # ``connector_factory`` closure.
    return CliContext(
        mode=mode,
        collections_path=resolver.get_collections_path(mode),
        caches_path=resolver.get_caches_path(mode),
        config_service=config_service,
    )


# --- the two core-facade callables + wiring bundles ---------------------------


def make_connector_factory(ctx: CliContext) -> Callable[[SourceConfig], BaseConnector]:
    """Create-time seam: build a connector from a SourceConfig."""
    return lambda cfg: build_connector(cfg, ctx.config_service, ctx.connector_registry)


def make_cache_decorator_factory() -> Callable[[Any, DiskPersister], Any]:
    from indexed.connectors.document_cache_reader_decorator import CacheReaderDecorator

    def factory(reader: Any, persister: DiskPersister) -> Any:
        return CacheReaderDecorator(reader=reader, persister=persister)

    return factory


def make_manifest_factory(ctx: CliContext) -> Callable[[Manifest, str], ConnectorRun]:
    """Update-time seam: dispatch a manifest to its connector's ``from_manifest``.
    One path for every source — no per-type branches."""
    from indexed.connectors import get_connector_class

    def factory(manifest: Manifest, storage_path: str) -> ConnectorRun:
        connector_cls = get_connector_class(manifest.reader.type)
        run: ConnectorRun = connector_cls.from_manifest(
            manifest, ctx.config_service, storage_path=storage_path
        )
        return run

    return factory


def wiring_kwargs_for_create(ctx: CliContext) -> dict[str, Any]:
    return {
        "connector_factory": make_connector_factory(ctx),
        "cache_decorator_factory": make_cache_decorator_factory(),
    }


def wiring_kwargs_for_update(ctx: CliContext) -> dict[str, Any]:
    return {"manifest_factory": make_manifest_factory(ctx)}
