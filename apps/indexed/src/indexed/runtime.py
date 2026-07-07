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
    from indexed.bootstrap import build_connector_registry, register_app_config

    config_service = ConfigService.instance(
        workspace=workspace,
        mode_override=mode_override,
        reset=mode_override is not None,
    )
    # `reset=True` above replaces the singleton with a fresh, empty
    # ConfigRegistry whenever a non-None mode_override is passed — even when
    # unchanged from what's already active. Re-registering here (idempotent,
    # plain dict writes) restores the specs for every caller (create/update/
    # search/inspect/remove/MCP), fixing the root cause instead of leaving
    # each caller to defensively re-register before its own `.bind()`
    # (foundation/6d E12 follow-up).
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
