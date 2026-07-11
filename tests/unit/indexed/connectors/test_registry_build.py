"""Tests that all registered connector types build via bootstrap."""

from unittest.mock import MagicMock, patch

import pytest
from indexed.protocols import SourceConfig

from indexed.cli.composition import build_connector, build_connector_registry


CONNECTOR_TYPES = [
    "localFiles",
    "jira",
    "jiraCloud",
    "confluence",
    "confluenceCloud",
    "outline",
]

SOURCE_CONFIGS = {
    "localFiles": SourceConfig(
        name="files-col",
        type="localFiles",
        base_url_or_path="/tmp/docs",
    ),
    "jira": SourceConfig(
        name="jira-col",
        type="jira",
        base_url_or_path="https://jira.example.com",
        query="project = TEST",
    ),
    "jiraCloud": SourceConfig(
        name="jira-cloud-col",
        type="jiraCloud",
        base_url_or_path="https://company.atlassian.net",
        query="project = TEST",
    ),
    "confluence": SourceConfig(
        name="confluence-col",
        type="confluence",
        base_url_or_path="https://wiki.example.com",
        query="type=page",
    ),
    "confluenceCloud": SourceConfig(
        name="confluence-cloud-col",
        type="confluenceCloud",
        base_url_or_path="https://company.atlassian.net/wiki",
        query="type=page",
    ),
    "outline": SourceConfig(
        name="outline-col",
        type="outline",
        base_url_or_path="https://outline.example.com",
    ),
}


@pytest.mark.parametrize("connector_type", CONNECTOR_TYPES)
def test_build_connector_all_source_types(connector_type: str) -> None:
    registry = build_connector_registry()
    config_service = MagicMock()
    cfg = SOURCE_CONFIGS[connector_type]
    connector_cls = registry[connector_type]
    expected = MagicMock()

    with patch.object(
        connector_cls, "from_config", return_value=expected
    ) as mock_from_config:
        result = build_connector(cfg, config_service, registry)

    assert result is expected
    mock_from_config.assert_called_once_with(config_service)
