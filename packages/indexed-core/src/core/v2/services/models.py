"""Service-layer data models for v2.

Re-exports v1 models to maintain API compatibility across versions.
These are shared data contracts consumed by CLI and MCP layers.
"""

from core.v1.engine.services.models import (
    CollectionInfo,
    CollectionStatus,
    PhasedProgressCallback,
    ProgressCallback,
    ProgressUpdate,
    SearchResult,
    SourceConfig,
)

__all__ = [
    "CollectionInfo",
    "CollectionStatus",
    "PhasedProgressCallback",
    "ProgressCallback",
    "ProgressUpdate",
    "SearchResult",
    "SourceConfig",
]
