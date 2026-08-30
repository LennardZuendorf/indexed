import importlib
from unittest.mock import MagicMock, patch

import pytest
from indexed.config import get_config, reload
from indexed.config.errors import ConfigurationError
from indexed.protocols import SourceConfig

from indexed.cli.composition import (
    build_connector,
    build_connector_registry,
    register_app_config,
)


def test_import_core_v1_does_not_register_config(monkeypatch):
    reload()
    before = len(get_config()._registry._specs)  # noqa: SLF001
    importlib.import_module("indexed.core.v1")
    after = len(get_config()._registry._specs)
    assert before == after


def test_import_connectors_jira_does_not_register_config():
    reload()
    before = len(get_config()._registry._specs)  # noqa: SLF001
    importlib.import_module("indexed.connectors.jira")
    after = len(get_config()._registry._specs)
    assert before == after


def test_register_app_config_is_idempotent():
    reload()
    svc = get_config()
    register_app_config(svc)
    n = len(svc._registry._specs)
    register_app_config(svc)
    assert len(svc._registry._specs) == n


def test_register_app_config_registers_core_v2_specs():
    from indexed.core.v2.config_models import (
        CoreV2EmbeddingConfig,
        CoreV2RerankConfig,
        CoreV2SearchConfig,
    )

    reload()
    svc = get_config()
    register_app_config(svc)
    assert svc._registry.has("core.v2.embedding")  # noqa: SLF001
    assert svc._registry.has("core.v2.search")  # noqa: SLF001
    assert svc._registry.has("core.v2.rerank")  # noqa: SLF001
    assert svc._registry._specs["core.v2.embedding"] is CoreV2EmbeddingConfig  # noqa: SLF001
    assert svc._registry._specs["core.v2.search"] is CoreV2SearchConfig  # noqa: SLF001
    assert svc._registry._specs["core.v2.rerank"] is CoreV2RerankConfig  # noqa: SLF001


def test_core_v2_config_binds_with_defaults_and_overlay_overrides():
    from indexed.core.v2.config_models import CoreV2EmbeddingConfig, CoreV2SearchConfig

    # Register only the two specs under test (not the full app registry via
    # register_app_config) so bind() validates only core.v2.*, per
    # .spec/lessons.md's "ConfigService.set_overlay() is the right tool for
    # config-dependent unit tests" — bind() otherwise also (re)validates
    # every other registered path (e.g. sources.files) against whatever the
    # shared sandboxed config.toml happens to hold at this point in the full
    # suite, coupling this test to unrelated tests' disk state.
    reload()
    svc = get_config()
    svc.register(CoreV2EmbeddingConfig, path="core.v2.embedding")
    svc.register(CoreV2SearchConfig, path="core.v2.search")

    svc.set_overlay("core.v2.embedding.batch_size", 64)
    svc.set_overlay("core.v2.search.max_docs", 5)

    bound = svc.bind()
    embedding = bound.get(CoreV2EmbeddingConfig)
    search = bound.get(CoreV2SearchConfig)

    assert embedding.model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert embedding.batch_size == 64
    assert search.max_docs == 5
    assert search.score_threshold == 0.0


def test_build_connector_registry_has_jira():
    reg = build_connector_registry()
    assert "jira" in reg
    assert "jiraCloud" in reg


def test_build_connector_jira_cloud_returns_cloud_connector():
    from indexed.connectors.jira import JiraCloudConnector

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
    from indexed.connectors.files import FileSystemConnector

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
    from indexed.connectors.jira import JiraCloudConnector

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
