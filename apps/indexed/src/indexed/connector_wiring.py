"""App-layer connector wiring for create/update command paths.

The update path is now a single ``manifest_factory`` that dispatches to the
connector's own ``from_manifest`` (each connector owns its manifest keys and
incremental cutoff). The per-connector ``_populate_*`` blocks, the private
attribute reaches, and the ``os.environ`` cutoff side-channel are gone.
"""

from __future__ import annotations

from typing import Any, Callable

from protocols import BaseConnector, ConnectorRun, Manifest, SourceConfig

from core.v1.engine.persisters.disk_persister import DiskPersister

from .bootstrap import build_connector
from .runtime import CliContext


def make_connector_factory(ctx: CliContext) -> Callable[[SourceConfig], BaseConnector]:
    """Build connectors via bootstrap using context registry."""
    return lambda cfg: build_connector(cfg, ctx.config_service, ctx.connector_registry)


def make_cache_decorator_factory() -> Callable[[Any, DiskPersister], Any]:
    from connectors.document_cache_reader_decorator import CacheReaderDecorator

    def factory(reader: Any, persister: DiskPersister) -> Any:
        return CacheReaderDecorator(reader=reader, persister=persister)

    return factory


def make_manifest_factory(ctx: CliContext) -> Callable[[Manifest, str], ConnectorRun]:
    """Build the update-time seam: dispatch a manifest to its connector's
    ``from_manifest``. One path for every source — no per-type branches."""
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
