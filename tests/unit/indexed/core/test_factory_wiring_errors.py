"""DI factories must raise a clear wiring error when a dependency is unset.

The create factory still guards its cache decorator with the canonical
`missing_wiring_error`. The other injected dependencies no longer use a runtime
guard — they are REQUIRED keyword-only arguments, so omitting them is a
`TypeError` at the call site. That call-binding contract is asserted directly in
this module: `test_update_updater_requires_manifest_factory` (update path) and
`test_create_requires_connector_factory` (create path).
"""

from unittest.mock import Mock

import pytest

from indexed.config.errors import ConfigurationError

from indexed.core.v1.engine.factories.create_collection_factory import (
    create_collection_creator,
)


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


def test_update_updater_requires_manifest_factory(tmp_path) -> None:
    """`manifest_factory` is keyword-only and required — omitting it is a TypeError.

    The binding error fires before the body runs, so no collection needs to
    exist on disk.
    """
    from indexed.core.v1.engine.factories.update_collection_factory import (
        create_collection_updater,
    )

    with pytest.raises(TypeError, match="manifest_factory"):
        create_collection_updater("x", collections_path=str(tmp_path))  # type: ignore[call-arg]


def test_create_requires_connector_factory() -> None:
    """`connector_factory` is keyword-only and required on the create path."""
    from indexed.core.v1.engine.services import collection_service

    with pytest.raises(TypeError, match="connector_factory"):
        collection_service.create([])  # type: ignore[call-arg]
