"""DI factories must raise a clear wiring error when a dependency is unset.

The create factory still guards its cache decorator with the canonical
`missing_wiring_error`. The update path no longer uses a runtime guard — its
`manifest_factory` is a REQUIRED keyword-only argument, so omitting it is a
`TypeError` at the call site (see test_update_collection_factory_integration).
"""

from unittest.mock import Mock

import pytest

from indexed_config.errors import ConfigurationError

from core.v1.engine.factories.create_collection_factory import create_collection_creator


def test_create_creator_raises_when_cache_factory_missing() -> None:
    with pytest.raises(ConfigurationError, match="cache_decorator_factory"):
        create_collection_creator(
            "col",
            ["FAISS"],
            Mock(),
            Mock(),
            use_cache=True,
            cache_decorator_factory=None,
        )
