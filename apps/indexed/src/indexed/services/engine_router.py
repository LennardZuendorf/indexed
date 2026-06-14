"""Engine selection router — resolves which engine (v1/v2) a call should use.

Precedence: per-command ``--engine`` → root ``--engine`` (``ctx.obj["engine"]``)
→ collection ``manifest.json`` auto-detect → ``[general] engine`` → default v2.
Service dispatch (engine→module) is re-exported from :mod:`engine_dispatch`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional, Union

from loguru import logger
from pydantic import BaseModel, Field

VALID_ENGINES: frozenset[str] = frozenset({"v1", "v2"})
DEFAULT_ENGINE: Literal["v1", "v2"] = "v2"


def normalize_engine(value: Any) -> Optional[str]:
    """Lowercase and validate a candidate engine; ``None`` if invalid/non-string."""
    if not isinstance(value, str) or not value:
        return None
    normalized = value.lower()
    return normalized if normalized in VALID_ENGINES else None


class GeneralConfig(BaseModel):
    """Top-level ``[general]`` section of config.toml."""

    engine: Literal["v1", "v2"] = Field(
        default=DEFAULT_ENGINE,
        description="Core engine: v2 (LlamaIndex, default) or v1 (legacy FAISS)",
    )


def detect_collection_engine(
    collection: str,
    collections_path: Union[str, Path],
) -> Optional[Literal["v1", "v2"]]:
    """Classify a collection's engine from its ``manifest.json`` (v2 carries
    ``"version": "2.x"``). Missing/malformed manifests return ``None``."""
    manifest_path = Path(collections_path) / collection / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # FileNotFoundError ⊂ OSError; JSON err ⊂ ValueError
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
    """Resolve the active engine (see module docstring for precedence)."""
    cmd = normalize_engine(command_engine)
    if cmd is not None:
        return cmd
    try:
        import click

        ctx = click.get_current_context()
        root_engine = normalize_engine((ctx.obj or {}).get("engine"))
        if root_engine is not None:
            return root_engine
    except (RuntimeError, AttributeError):
        pass  # no active CLI context (e.g. unit tests)

    if collection and collections_path is not None:
        detected = detect_collection_engine(collection, collections_path)
        if detected is not None:
            return detected

    try:
        from indexed_config import ConfigService

        general = ConfigService.instance().bind().get(GeneralConfig)
        cfg_engine = normalize_engine(general.engine)
        if cfg_engine is not None:
            return cfg_engine
    except Exception as exc:  # config not registered/bound — fall back, log
        logger.debug("engine config unavailable; default %r: %s", DEFAULT_ENGINE, exc)
    return DEFAULT_ENGINE


# Service dispatch lives in engine_dispatch; re-exported here so callers have a
# single ``engine_router`` import surface for both resolution and dispatch.
from .engine_dispatch import (  # noqa: E402,F401
    get_collection_service,
    get_inspect_service,
    get_search_service,
)
