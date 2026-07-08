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

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Type

from indexed_config import ConfigService
from indexed_config.errors import ConfigurationError
from protocols import BaseConnector, ConnectorRun, Manifest, SourceConfig

from core.v1.engine.persisters.disk_persister import DiskPersister


# --- config registration ------------------------------------------------------


def register_app_config(config_service: ConfigService) -> None:
    """Register all config specs — idempotent, raises on failure."""
    from core.v1.config_models import (
        CoreV1EmbeddingConfig,
        CoreV1IndexingConfig,
        CoreV1SearchConfig,
        CoreV1StorageConfig,
        MCPConfig,
    )
    from connectors.confluence.schema import ConfluenceCloudConfig
    from connectors.files.schema import FileSystemConfig
    from connectors.jira.schema import JiraCloudConfig
    from connectors.outline.schema import OutlineConfig

    config_service.register(CoreV1IndexingConfig, path="core.v1.indexing")
    config_service.register(CoreV1SearchConfig, path="core.v1.search")
    config_service.register(CoreV1StorageConfig, path="core.v1.storage")
    config_service.register(CoreV1EmbeddingConfig, path="core.v1.embedding")
    config_service.register(MCPConfig, path="mcp")
    config_service.register(FileSystemConfig, path="sources.files")
    config_service.register(JiraCloudConfig, path="sources.jira")
    config_service.register(ConfluenceCloudConfig, path="sources.confluence")
    config_service.register(OutlineConfig, path="sources.outline")


# --- connector construction ---------------------------------------------------


def build_connector_registry() -> dict[str, Type[Any]]:
    from connectors.registry import CONNECTOR_REGISTRY

    return dict(CONNECTOR_REGISTRY)


def build_connector(
    cfg: SourceConfig,
    config_service: ConfigService,
    registry: dict[str, Type[Any]] | None = None,
) -> BaseConnector:
    from connectors.registry import get_config_namespace

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
    connector_registry: dict[str, Any]


def resolve_collections_context(
    mode_override: str | None = None,
    *,
    workspace: Path | None = None,
) -> CliContext:
    config_service = ConfigService.instance(
        workspace=workspace,
        mode_override=mode_override,  # type: ignore[arg-type]
        reset=mode_override is not None,
    )
    # `reset=True` above replaces the singleton with a fresh ConfigRegistry
    # whenever a non-None mode_override is passed; re-register here (idempotent)
    # so every caller gets the specs back for free (foundation/6d E12).
    register_app_config(config_service)
    mode = config_service.resolve_storage_mode()
    resolver = config_service.resolver
    return CliContext(
        mode=mode,
        collections_path=resolver.get_collections_path(mode),
        caches_path=resolver.get_caches_path(mode),
        config_service=config_service,
        connector_registry=build_connector_registry(),
    )


# --- the two core-facade callables + wiring bundles ---------------------------


def make_connector_factory(ctx: CliContext) -> Callable[[SourceConfig], BaseConnector]:
    """Create-time seam: build a connector from a SourceConfig."""
    return lambda cfg: build_connector(cfg, ctx.config_service, ctx.connector_registry)


def make_cache_decorator_factory() -> Callable[[Any, DiskPersister], Any]:
    from connectors.document_cache_reader_decorator import CacheReaderDecorator

    def factory(reader: Any, persister: DiskPersister) -> Any:
        return CacheReaderDecorator(reader=reader, persister=persister)

    return factory


def make_manifest_factory(ctx: CliContext) -> Callable[[Manifest, str], ConnectorRun]:
    """Update-time seam: dispatch a manifest to its connector's ``from_manifest``.
    One path for every source — no per-type branches."""
    from connectors import get_connector_class

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
