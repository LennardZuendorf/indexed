import importlib
from unittest.mock import MagicMock, patch

import pytest
from indexed_config import ConfigService
from indexed_config.errors import ConfigurationError
from protocols import SourceConfig

from indexed.bootstrap import (
    build_connector,
    build_connector_registry,
    register_app_config,
)


def test_import_core_v1_does_not_register_config(monkeypatch):
    ConfigService.instance(reset=True)
    before = len(ConfigService.instance()._registry._specs)  # noqa: SLF001
    importlib.import_module("core.v1")
    after = len(ConfigService.instance()._registry._specs)
    assert before == after


def test_import_connectors_jira_does_not_register_config():
    ConfigService.instance(reset=True)
    before = len(ConfigService.instance()._registry._specs)  # noqa: SLF001
    importlib.import_module("connectors.jira")
    after = len(ConfigService.instance()._registry._specs)
    assert before == after


def test_register_app_config_is_idempotent():
    ConfigService.instance(reset=True)
    svc = ConfigService.instance()
    register_app_config(svc)
    n = len(svc._registry._specs)
    register_app_config(svc)
    assert len(svc._registry._specs) == n


def test_build_connector_registry_has_jira():
    reg = build_connector_registry()
    assert "jira" in reg
    assert "jiraCloud" in reg


def test_build_connector_jira_cloud_returns_cloud_connector():
    from connectors.jira import JiraCloudConnector

    config_service = MagicMock()
    cfg = SourceConfig(
        name="test",
        type="jiraCloud",
        base_url_or_path="https://company.atlassian.net",
        query="project = TEST",
    )
    expected = MagicMock(spec=JiraCloudConnector)

    with patch.object(JiraCloudConnector, "from_config", return_value=expected):
        result = build_connector(cfg, config_service, build_connector_registry())

    assert result is expected
    # E4: overrides go to the in-memory overlay only — never persisted.
    config_service.set_overlay.assert_any_call(
        "sources.jira.url", "https://company.atlassian.net"
    )
    config_service.set_overlay.assert_any_call("sources.jira.query", "project = TEST")
    config_service.set.assert_not_called()


def test_build_connector_unknown_type_raises():
    config_service = MagicMock()
    cfg = SourceConfig(
        name="x", type="outline", base_url_or_path="https://outline.example.com"
    )
    with pytest.raises(ConfigurationError, match="Unknown connector type"):
        build_connector(cfg, config_service, {"localFiles": MagicMock()})


def test_build_connector_local_files_sets_path():
    from connectors.files import FileSystemConnector

    config_service = MagicMock()
    cfg = SourceConfig(
        name="test",
        type="localFiles",
        base_url_or_path="/tmp/docs",
    )
    expected = MagicMock(spec=FileSystemConnector)

    with patch.object(FileSystemConnector, "from_config", return_value=expected):
        result = build_connector(cfg, config_service, build_connector_registry())

    assert result is expected
    # E4: overrides go to the in-memory overlay only — never persisted.
    config_service.set_overlay.assert_any_call("sources.files.path", "/tmp/docs")
    config_service.set.assert_not_called()
    url_calls = [
        call
        for call in config_service.set_overlay.call_args_list
        if call[0][0].endswith(".url")
    ]
    assert not url_calls


def test_build_connector_sets_query_for_remote_types() -> None:
    from connectors.jira import JiraCloudConnector

    config_service = MagicMock()
    cfg = SourceConfig(
        name="j",
        type="jiraCloud",
        base_url_or_path="https://jira.example.com",
        query="project = ABC",
    )
    with patch.object(JiraCloudConnector, "from_config", return_value=MagicMock()):
        build_connector(cfg, config_service, build_connector_registry())
    config_service.set_overlay.assert_any_call("sources.jira.query", "project = ABC")
    config_service.set.assert_not_called()
