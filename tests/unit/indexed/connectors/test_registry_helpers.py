"""Registry helper edge-case coverage."""

import pytest

from indexed.connectors.registry import (
    get_config_namespace,
    get_connector_class,
    get_source_path_key,
)


def test_get_connector_class_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown connector type"):
        get_connector_class("not-real")


def test_get_config_namespace_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown connector type"):
        get_config_namespace("not-real")


def test_get_source_path_key_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown connector type"):
        get_source_path_key("not-real")


@pytest.mark.parametrize(
    "connector_type, expected",
    [
        ("localFiles", "path"),
        ("github", "host"),
        ("jira", "url"),
        ("jiraCloud", "url"),
        ("confluence", "url"),
        ("confluenceCloud", "url"),
        ("outline", "url"),
    ],
)
def test_get_source_path_key(connector_type: str, expected: str) -> None:
    assert get_source_path_key(connector_type) == expected


def test_every_connector_type_has_a_path_key() -> None:
    """A new connector must not silently fall back to a hardcoded ``url``."""
    from indexed.connectors.registry import CONNECTOR_REGISTRY, PATH_KEY_REGISTRY

    assert set(PATH_KEY_REGISTRY) == set(CONNECTOR_REGISTRY)
