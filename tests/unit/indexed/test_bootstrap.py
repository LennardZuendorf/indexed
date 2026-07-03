import importlib

from indexed_config import ConfigService

from indexed.bootstrap import build_connector_registry, register_app_config


def test_import_core_v1_does_not_register_config(monkeypatch):
    ConfigService.instance(reset=True)
    before = len(ConfigService.instance()._registry._specs)  # noqa: SLF001
    importlib.import_module("core.v1")
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
