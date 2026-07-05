"""DI factories must raise a clear wiring error when a dependency is unset.

These lock in the F3 canonical `missing_wiring_error` paths on the create and
update factories (app composition root owns the wiring).
"""

from unittest.mock import Mock

import pytest

from indexed_config.errors import ConfigurationError

from core.v1.engine.factories.create_collection_factory import create_collection_creator
from core.v1.engine.factories.update_collection_factory import (
    _create_reader_and_converter,
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


def test_manifest_reader_raises_when_factory_missing() -> None:
    with pytest.raises(ConfigurationError, match="manifest_connector_factory"):
        _create_reader_and_converter({"reader": {"type": "jira"}}, None)


def test_manifest_reader_delegates_to_injected_factory() -> None:
    reader, converter = Mock(), Mock()
    factory = Mock(return_value=(reader, converter))
    manifest = {"reader": {"type": "jira"}}

    result = _create_reader_and_converter(manifest, factory)

    factory.assert_called_once_with(manifest)
    assert result == (reader, converter)
