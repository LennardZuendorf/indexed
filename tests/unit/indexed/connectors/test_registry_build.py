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
    "github",
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
    "github": SourceConfig(
        name="github-col",
        type="github",
        base_url_or_path="github.acme.internal",
    ),
}

EXPECTED_PATH_KEYS = {
    "localFiles": "sources.files.path",
    "jira": "sources.jira.url",
    "jiraCloud": "sources.jira.url",
    "confluence": "sources.confluence.url",
    "confluenceCloud": "sources.confluence.url",
    "outline": "sources.outline.url",
    "github": "sources.github.host",
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


@pytest.mark.parametrize("connector_type", CONNECTOR_TYPES)
def test_build_connector_overlays_registry_path_key(connector_type: str) -> None:
    """``base_url_or_path`` must land on each source's own key — ``path`` for
    files, ``host`` for GitHub, ``url`` for the rest — never a hardcoded
    ``url``."""
    registry = build_connector_registry()
    config_service = MagicMock()
    cfg = SOURCE_CONFIGS[connector_type]

    with patch.object(
        registry[connector_type], "from_config", return_value=MagicMock()
    ):
        build_connector(cfg, config_service, registry)

    keys = [c.args[0] for c in config_service.set_overlay.call_args_list]
    assert EXPECTED_PATH_KEYS[connector_type] in keys
    config_service.set_overlay.assert_any_call(
        EXPECTED_PATH_KEYS[connector_type], cfg.base_url_or_path
    )
