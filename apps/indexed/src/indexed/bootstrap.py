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
    from connectors.confluence.schema import ConfluenceCloudConfig, ConfluenceConfig
    from connectors.files.schema import FileSystemConfig, LocalFilesConfig
    from connectors.jira.schema import JiraCloudConfig, JiraConfig
    from connectors.outline.schema import OutlineConfig
    from indexed.mcp.config import MCPConfig

    config_service.register(CoreV1IndexingConfig, path="core.v1.indexing")
    config_service.register(CoreV1SearchConfig, path="core.v1.search")
    config_service.register(CoreV1StorageConfig, path="core.v1.vector_store")
    config_service.register(CoreV1EmbeddingConfig, path="core.v1.embedding")
    config_service.register(MCPConfig, path="mcp")
    config_service.register(FileSystemConfig, path="sources.files")
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
    cls = registry.get(cfg.type)
    if cls is None:
        available = ", ".join(sorted(registry))
        raise ConfigurationError(
            f"Unknown connector type: {cfg.type}. Available: {available}"
        )

    namespace = NAMESPACE_REGISTRY.get(cfg.type, f"sources.{cfg.type}")
    if cfg.base_url_or_path:
        if cfg.type == "localFiles":
            config_service.set(f"{namespace}.path", cfg.base_url_or_path)
        else:
            config_service.set(f"{namespace}.url", cfg.base_url_or_path)
    if cfg.query:
        config_service.set(f"{namespace}.query", cfg.query)

    return cls.from_config(config_service)  # type: ignore[return-value]
