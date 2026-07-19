"""Shared path + config resolution for the v2 engine (core-v2/2c).

Small helpers used by ingestion / retrieval / services. Imports only
``config``/``config_models`` (+ stdlib) — never ``core.v1`` and never
LlamaIndex — so it stays import-cheap and obeys the core/v2 import rule.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from indexed.core.v2.config_models import (
        CoreV2EmbeddingConfig,
        CoreV2RerankConfig,
        CoreV2SearchConfig,
    )

# Transient build-aside/rollback dirs the durable-create path leaves on disk;
# excluded from discovery exactly as v1's services do (v1-surface-map §7).
_INTERNAL_COLLECTION_DIR_RE = re.compile(r"\.(?:tmp|trash)-\d+")


def collections_base(collections_path: Optional[str]) -> Path:
    """Resolve the collections directory (mirrors v1's default resolution).

    An explicit ``collections_path`` wins; otherwise the active storage
    resolver decides — the same source v1's ``get_default_collections_path``
    uses, reached through ``indexed.config`` (allowed) rather than importing
    ``core.v1``.
    """
    if collections_path:
        return Path(collections_path)
    try:
        from indexed.config import get_config

        return Path(get_config().resolver.get_collections_path())
    except Exception:
        return Path.home() / ".indexed" / "data" / "collections"


def resolve_embedding_config() -> "CoreV2EmbeddingConfig":
    """The bound ``[core.v2.embedding]`` config, or its defaults.

    Mirrors the MCP ``_get_config`` fallback: a direct service/test call that
    never registered the spec still gets a valid default config.
    """
    from indexed.core.v2.config_models import CoreV2EmbeddingConfig

    try:
        from indexed.config import get_config

        return get_config().bind().get(CoreV2EmbeddingConfig)
    except Exception:
        return CoreV2EmbeddingConfig()


def resolve_search_config() -> "CoreV2SearchConfig":
    """The bound ``[core.v2.search]`` config, or its defaults."""
    from indexed.core.v2.config_models import CoreV2SearchConfig

    try:
        from indexed.config import get_config

        return get_config().bind().get(CoreV2SearchConfig)
    except Exception:
        return CoreV2SearchConfig()


def resolve_rerank_config() -> "CoreV2RerankConfig":
    """The bound ``[core.v2.rerank]`` config, or its defaults (disabled).

    A direct service/test call that never registered the spec still gets the
    default (``enabled=False``) — so the zero-cost, no-CrossEncoder path holds.
    """
    from indexed.core.v2.config_models import CoreV2RerankConfig

    try:
        from indexed.config import get_config

        return get_config().bind().get(CoreV2RerankConfig)
    except Exception:
        return CoreV2RerankConfig()


def is_v2_collection(collection_dir: Path) -> bool:
    """True when ``collection_dir`` holds a readable v2 manifest (``version:"2"``)."""
    manifest_path = collection_dir / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(raw, dict) and raw.get("version") == "2"


def discover_v2_collections(base: Path) -> list[str]:
    """Names of on-disk v2 collections under ``base`` (sorted, tmp/trash excluded)."""
    if not base.is_dir():
        return []
    names: list[str] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        if _INTERNAL_COLLECTION_DIR_RE.search(child.name):
            continue
        if is_v2_collection(child):
            names.append(child.name)
    return names


__all__ = [
    "collections_base",
    "discover_v2_collections",
    "is_v2_collection",
    "resolve_embedding_config",
    "resolve_rerank_config",
    "resolve_search_config",
]
