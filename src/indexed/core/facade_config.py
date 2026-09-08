"""Facade-level configuration + re-exported utility surface (issue #186).

CoreEngineConfig ([core] engine) selects the default engine for NEW
collections; it lives here (not inside core.v1, which stays frozen).

The lazy re-exports below (mirroring core.engine's own __getattr__ pattern)
let cli/mcp reference v1 config-model types and small utility
constants/functions without importing core.v1.*/core.v2.* directly anywhere
in their own files — satisfying .spec/tech.md's "no code above the facade
may import core.v1.*/core.v2.* directly" contract for every cli/mcp file the
check_imports.py rule covers, not just for CoreEngineConfig. (config/commands/
is a separate, pre-existing exemption in check_imports.py's _EXEMPT_DIRS, for
the same composition-adjacent rationale as config/cli.py — a file there, e.g.
config/commands/_helpers.py, importing core.v1.* directly is expected and out
of scope for this module.) Each re-export is a straight v1 pass-through (v1
is the only engine with these today, e.g. the embedding model-cache manager);
nothing is imported until first accessed, so a consumer that only needs
CoreEngineConfig never pays for the model-manager import chain, and vice
versa.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator


class CoreEngineConfig(BaseModel):
    """Default engine selector for NEW collections (``[core] engine``).

    Registered at config path ``core``, so it receives the ENTIRE ``[core]``
    subtree (including the ``core.v1.*`` / ``core.v2.*`` tables) at validation
    time. It therefore MUST keep pydantic's default ``extra="ignore"`` to drop
    those sibling tables — never ``extra="forbid"`` (OQ-T1). The value is
    validated to ``"1"``/``"2"`` here (not via a ``Literal``) so a bad value
    fails loud with a clear message. Lives next to ``MCPConfig`` — the sibling
    non-``core.v1`` model — as the minimal home.
    """

    engine: str = Field(
        default="1", description="Default engine for new collections: '1' or '2'"
    )

    @field_validator("engine")
    @classmethod
    def _check_engine_value(cls, v: str) -> str:
        # Named ``_check_engine_value`` (not ``_validate_engine``) to avoid a
        # cross-file collision with ``core.engine._validate_engine`` (the module
        # function that coerces a selector to an ``EngineVersion``).
        #
        # Accept the user-facing forms every surface documents (--engine, env,
        # config) — "1"/"2"/"v1"/"v2" (case-insensitive) — and STORE the
        # canonical "1"/"2". Kept in sync with
        # cli.composition.normalize_engine_selector (replicated, not imported:
        # config must not import the CLI layer).
        normalized = {"1": "1", "2": "2", "v1": "1", "v2": "2"}.get(
            str(v).strip().lower()
        )
        if normalized is None:
            raise ValueError(f"engine must be one of '1', '2', 'v1', 'v2', got {v!r}")
        return normalized


_REEXPORTS: dict[str, str] = {
    "CoreV1SearchConfig": "indexed.core.v1.config_models",
    "MCPConfig": "indexed.core.v1.config_models",
    "DEFAULT_INDEXER": "indexed.core.v1.constants",
    "DEFAULT_MODEL": "indexed.core.v1.engine.indexes.embeddings.model_manager",
    "ensure_model": "indexed.core.v1.engine.indexes.embeddings.model_manager",
    "get_cache_info": "indexed.core.v1.engine.indexes.embeddings.model_manager",
    "is_model_cached": "indexed.core.v1.engine.indexes.embeddings.model_manager",
}


def __getattr__(name: str) -> Any:
    module_path = _REEXPORTS.get(name)
    if module_path is None:
        raise AttributeError(
            f"module 'indexed.core.facade_config' has no attribute {name!r}"
        )
    return getattr(importlib.import_module(module_path), name)


def __dir__() -> list[str]:
    return sorted(["CoreEngineConfig", *_REEXPORTS])


if TYPE_CHECKING:  # help type-checkers/IDEs see the re-exported names
    from indexed.core.v1.config_models import (  # noqa: F401
        CoreV1SearchConfig,
        MCPConfig,
    )
    from indexed.core.v1.constants import DEFAULT_INDEXER  # noqa: F401
    from indexed.core.v1.engine.indexes.embeddings.model_manager import (  # noqa: F401
        DEFAULT_MODEL,
        ensure_model,
        get_cache_info,
        is_model_cached,
    )


__all__ = ["CoreEngineConfig", *sorted(_REEXPORTS)]
