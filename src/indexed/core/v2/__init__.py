"""Core v2 engine package — lazy facade (core-v2/2a).

Mirrors ``core.v1.engine``'s lazy ``__getattr__`` pattern (surface map §1) so
importing ``indexed.core.v2`` stays cheap and the adapter's own LlamaIndex
import stays function-local inside ``to_nodes``. Later core-v2 sub-tasks
(2b/2c) extend ``_EXPORTS``/``_MODULE_FOR`` with engine-facing names
(ingestion, retrieval, services) — this module is the seam; no wiring into
the version-dispatching facade (``indexed.core.engine``) happens here.
"""

from typing import TYPE_CHECKING, Any

_EXPORTS = frozenset(
    {
        "V2Manifest",
        "V2EngineBlock",
        "V2EmbeddingInfo",
        "CoreV2EmbeddingConfig",
        "CoreV2SearchConfig",
        "to_nodes",
    }
)

_MODULE_FOR = {
    "V2Manifest": "manifest",
    "V2EngineBlock": "manifest",
    "V2EmbeddingInfo": "manifest",
    "CoreV2EmbeddingConfig": "config_models",
    "CoreV2SearchConfig": "config_models",
    "to_nodes": "adapter",
}


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        import importlib

        module = importlib.import_module(f"indexed.core.v2.{_MODULE_FOR[name]}")
        return getattr(module, name)
    raise AttributeError(f"module 'indexed.core.v2' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_EXPORTS)


if TYPE_CHECKING:  # help type-checkers/IDEs see the re-exported names
    from indexed.core.v2.adapter import to_nodes  # noqa: F401
    from indexed.core.v2.config_models import (  # noqa: F401
        CoreV2EmbeddingConfig,
        CoreV2SearchConfig,
    )
    from indexed.core.v2.manifest import (  # noqa: F401
        V2EmbeddingInfo,
        V2EngineBlock,
        V2Manifest,
    )


__all__ = sorted(_EXPORTS)
