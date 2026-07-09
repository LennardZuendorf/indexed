"""Characterization: every source type resolves to a usable connector.

Consolidates the observable behavior that the per-connector ``test_init.py``
files asserted in granular form (registry membership, class identity, config
class, namespace) into one behavior-focused check over the public registry API.
The lifecycle nets prove each connector *works*; this proves each declared type
*resolves* to the right connector contract, so the CLI/MCP can construct it.
"""

from __future__ import annotations

import pytest

# Expected type -> (connector class import, config class import, namespace).
EXPECTED = {
    "localFiles": ("connectors.files.connector:FileSystemConnector", "sources.files"),
    "jira": ("connectors.jira.connector:JiraConnector", "sources.jira"),
    "jiraCloud": ("connectors.jira.connector:JiraCloudConnector", "sources.jira"),
    "confluence": (
        "connectors.confluence.connector:ConfluenceConnector",
        "sources.confluence",
    ),
    "confluenceCloud": (
        "connectors.confluence.connector:ConfluenceCloudConnector",
        "sources.confluence",
    ),
    "outline": ("connectors.outline.connector:OutlineConnector", "sources.outline"),
}


def _resolve(dotted: str):
    module_path, _, attr = dotted.partition(":")
    import importlib

    return getattr(importlib.import_module(module_path), attr)


def test_all_expected_types_are_registered() -> None:
    from connectors.registry import CONNECTOR_REGISTRY

    assert set(EXPECTED) <= set(CONNECTOR_REGISTRY)


@pytest.mark.parametrize("source_type", sorted(EXPECTED))
def test_type_resolves_to_connector_contract(source_type: str) -> None:
    from connectors.registry import (
        get_config_namespace,
        get_connector_class,
    )

    connector_dotted, namespace = EXPECTED[source_type]
    connector_cls = get_connector_class(source_type)

    # Resolves to the expected class...
    assert connector_cls is _resolve(connector_dotted)
    # ...that exposes the connector contract the engine + composition rely on.
    assert hasattr(connector_cls, "from_config")
    assert hasattr(connector_cls, "reader")
    assert hasattr(connector_cls, "converter")

    # Namespace resolves consistently.
    assert get_config_namespace(source_type) == namespace
