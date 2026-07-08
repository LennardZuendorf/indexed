from typing import Any, ClassVar

from protocols import BaseConnector, ConnectorRun, SourceConfig


class _MinimalConnector:
    """Minimal stub that satisfies the BaseConnector protocol."""

    META: ClassVar[Any] = None

    @property
    def reader(self):
        return None

    @property
    def converter(self):
        return None

    @property
    def connector_type(self) -> str:
        return "minimal"

    @classmethod
    def config_spec(cls):
        return {}

    @classmethod
    def from_config(cls, config_service):
        return cls()

    @classmethod
    def from_manifest(cls, manifest, config_service, *, storage_path):
        return ConnectorRun(None, None, [], None)


def test_base_connector_protocol_conformance():
    assert isinstance(_MinimalConnector(), BaseConnector)


def test_non_conforming_object_fails_base_connector_check():
    assert not isinstance(object(), BaseConnector)


def test_source_config_accepts_jira_type():
    cfg = SourceConfig(
        name="x", type="jira", base_url_or_path="https://jira.example.com"
    )
    assert cfg.type == "jira"
