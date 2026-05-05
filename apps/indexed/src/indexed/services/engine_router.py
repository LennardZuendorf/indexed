"""Engine selection router — dispatches to v1 or v2 service modules.

Resolution order (highest priority first):
1. Per-command ``--engine`` flag (passed as ``command_engine`` arg)
2. Root callback ``--engine`` flag stored in ``ctx.obj["engine"]``
3. On-disk ``manifest.json`` for the named collection (auto-detect)
4. ``[general] engine`` key in config.toml
5. Default: ``"v1"``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

VALID_ENGINES: frozenset[str] = frozenset({"v1", "v2"})


def normalize_engine(value: Any) -> Optional[str]:
    """Lowercase a candidate engine value and validate it against ``VALID_ENGINES``.

    Returns the normalized string if valid, ``None`` otherwise. Non-string
    inputs (e.g., Typer ``OptionInfo`` sentinels) return ``None``.
    """
    if not isinstance(value, str) or not value:
        return None
    normalized = value.lower()
    return normalized if normalized in VALID_ENGINES else None


class GeneralConfig(BaseModel):
    """Top-level [general] section of config.toml."""

    engine: Literal["v1", "v2"] = Field(
        default="v1",
        description="Core engine version: v1 (default) or v2 (LlamaIndex-powered)",
    )


def detect_collection_engine(
    collection: str,
    collections_path: Union[str, Path],
) -> Optional[Literal["v1", "v2"]]:
    """Classify a collection's engine by reading its on-disk manifest.

    Both engines persist ``<collections_path>/<collection>/manifest.json``.
    Schema differences:

    - v1 manifest (writer:
      ``packages/indexed-core/src/core/v1/engine/core/documents_collection_creator.py``):
      camelCase keys (``collectionName``, ``numberOfDocuments``, ``indexers``).
      No ``"version"`` key.
    - v2 manifest (writer: ``packages/indexed-core/src/core/v2/storage.py``):
      snake_case keys (``name``, ``num_documents``, ``num_chunks``) plus an
      explicit ``"version": "2.0"`` field.

    Detection rule: a parsed manifest dict whose ``"version"`` value starts with
    ``"2"`` is ``"v2"``; any other dict is ``"v1"``. Missing files, malformed
    JSON, and non-dict payloads return ``None`` so callers fall back to the
    configured default.

    Args:
        collection: Collection directory name.
        collections_path: Root directory containing collection subdirectories.

    Returns:
        ``"v1"``, ``"v2"``, or ``None`` if the manifest is missing/unreadable.
    """
    manifest_path = Path(collections_path) / collection / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    version = payload.get("version")
    if isinstance(version, str) and version.startswith("2"):
        return "v2"
    return "v1"


def get_effective_engine(
    command_engine: Optional[str] = None,
    *,
    collection: Optional[str] = None,
    collections_path: Optional[Union[str, Path]] = None,
) -> str:
    """Resolve the active engine for the current call.

    Resolution order (highest priority first):
    1. ``command_engine`` (per-command ``--engine`` flag).
    2. ``ctx.obj["engine"]`` (root callback ``--engine`` flag).
    3. Manifest auto-detection — only when both ``collection`` and
       ``collections_path`` are supplied.
    4. ``[general] engine`` from ``config.toml``.
    5. Default: ``"v1"``.

    Args:
        command_engine: Per-command ``--engine`` flag value.
        collection: Optional collection name to auto-detect from disk.
        collections_path: Root directory containing collection subdirectories.
            Required alongside ``collection`` for manifest detection.

    Returns:
        ``"v1"`` or ``"v2"``.
    """
    cmd = normalize_engine(command_engine)
    if cmd is not None:
        return cmd

    # Root callback flag stored on Typer context
    try:
        import click

        ctx = click.get_current_context()
        root_engine = normalize_engine((ctx.obj or {}).get("engine"))
        if root_engine is not None:
            return root_engine
    except (RuntimeError, AttributeError):
        pass  # No active Typer context (e.g., during unit tests)

    # Auto-detect from on-disk manifest when a target collection is named
    if collection and collections_path is not None:
        detected = detect_collection_engine(collection, collections_path)
        if detected is not None:
            return detected

    # Fall back to [general] engine in config
    try:
        from indexed_config import ConfigService

        config = ConfigService.instance()
        provider = config.bind()
        general = provider.get(GeneralConfig)
        cfg_engine = normalize_engine(general.engine)
        if cfg_engine is not None:
            return cfg_engine
    except Exception:
        pass

    return "v1"


def get_collection_service(engine: str) -> Any:
    """Return the collection service module for the given engine.

    The returned module exposes ``create``, ``update``, and ``clear``.
    """
    if engine == "v2":
        from core.v2.services import collection_service

        return collection_service
    from core.v1.engine.services import collection_service

    return collection_service


def get_search_service(engine: str) -> Any:
    """Return the search service module for the given engine.

    The returned module exposes ``search`` and ``SearchService``.
    """
    if engine == "v2":
        from core.v2.services import search_service

        return search_service
    from core.v1.engine.services import search_service

    return search_service


def get_inspect_service(engine: str) -> Any:
    """Return the inspect service module for the given engine.

    The returned module exposes ``status`` and ``inspect``.
    """
    if engine == "v2":
        from core.v2.services import inspect_service

        return inspect_service
    from core.v1.engine.services import inspect_service

    return inspect_service
