"""Coverage for core.v1.constants re-export."""

import core.v1.constants


def test_default_indexer_is_canonical() -> None:
    """DEFAULT_INDEXER re-exported from core.v1.constants is the canonical object."""
    import importlib

    mod = importlib.import_module("core.v1.constants")
    assert mod.DEFAULT_INDEXER is core.v1.constants.DEFAULT_INDEXER
