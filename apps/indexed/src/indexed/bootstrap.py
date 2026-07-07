"""App composition root — config registration and connector wiring."""

from __future__ import annotations

from typing import Any, Type

from indexed_config import ConfigService
from indexed_config.errors import ConfigurationError
from protocols import BaseConnector, SourceConfig


def register_app_config(config_service: ConfigService) -> None:
    """Register all config specs — idempotent, raises on failure."""
    from core.v1.config_models import (
        CoreV1EmbeddingConfig,
        CoreV1IndexingConfig,
        CoreV1SearchConfig,
        CoreV1StorageConfig,
    )
    from connectors.confluence.schema import ConfluenceCloudConfig
    from connectors.files.schema import FileSystemConfig
    from connectors.jira.schema import JiraCloudConfig
    from connectors.outline.schema import OutlineConfig
    from core.v1.config_models import MCPConfig

    config_service.register(CoreV1IndexingConfig, path="core.v1.indexing")
    config_service.register(CoreV1SearchConfig, path="core.v1.search")
    # Registered path must match what config/cli.py's schema/template and
    # `config set core.v1.storage.*` actually write — it was previously
    # registered under "core.v1.vector_store", so storage overrides were
    # silently never validated/bound (foundation/6 E12).
    config_service.register(CoreV1StorageConfig, path="core.v1.storage")
    config_service.register(CoreV1EmbeddingConfig, path="core.v1.embedding")
    config_service.register(MCPConfig, path="mcp")
    config_service.register(FileSystemConfig, path="sources.files")
    config_service.register(JiraCloudConfig, path="sources.jira")
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
    from connectors.registry import get_config_namespace

    registry = registry or build_connector_registry()
    cls = registry.get(cfg.type)
    if cls is None:
        available = ", ".join(sorted(registry))
        raise ConfigurationError(
            f"Unknown connector type: {cfg.type}. Available: {available}"
        )

    namespace = get_config_namespace(cfg.type)
    # In-memory overlay only (R3): a failed create must not leave the
    # override on disk (foundation/6b bug E4) — see ConfigService.set_overlay.
    if cfg.base_url_or_path:
        if cfg.type == "localFiles":
            config_service.set_overlay(f"{namespace}.path", cfg.base_url_or_path)
        else:
            config_service.set_overlay(f"{namespace}.url", cfg.base_url_or_path)
    if cfg.query:
        config_service.set_overlay(f"{namespace}.query", cfg.query)

    return cls.from_config(config_service)  # type: ignore[return-value]
