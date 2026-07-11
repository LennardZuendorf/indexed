"""Registry helper edge-case coverage."""

import pytest

from indexed.connectors.registry import (
    get_config_namespace,
    get_connector_class,
)


def test_get_connector_class_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown connector type"):
        get_connector_class("not-real")


def test_get_config_namespace_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown connector type"):
        get_config_namespace("not-real")
