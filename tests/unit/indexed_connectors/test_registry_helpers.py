"""Registry helper edge-case coverage."""

import pytest

from connectors.registry import (
    get_config_class,
    get_config_namespace,
    get_connector_class,
    list_connector_types,
)


def test_get_connector_class_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown connector type"):
        get_connector_class("not-real")


def test_get_config_class_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown connector type"):
        get_config_class("not-real")


def test_get_config_namespace_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown connector type"):
        get_config_namespace("not-real")


def test_list_connector_types_includes_core_sources() -> None:
    types = list_connector_types()
    assert "jiraCloud" in types
    assert "localFiles" in types
