from unittest.mock import MagicMock

import pytest

from indexed.config import ConfigurationError
from indexed.connectors.github.connector import GitHubConnector
from indexed.connectors.github.schema import GitHubConfig
from indexed.connectors.github.github_document_converter import GitHubDocumentConverter
from indexed.connectors.github.github_graphql_reader import GitHubGraphQLReader
from indexed.protocols import ConnectorRun


def test_connector_type():
    connector = GitHubConnector(GitHubConfig(repos=["octo/hello"], token="ghp_x"))
    assert connector.connector_type == "github"


def test_reader_and_converter_exposed():
    connector = GitHubConnector(GitHubConfig(repos=["octo/hello"], token="ghp_x"))
    assert isinstance(connector.reader, GitHubGraphQLReader)
    assert isinstance(connector.converter, GitHubDocumentConverter)


def test_repr_reports_cloud_vs_enterprise():
    cloud = GitHubConnector(GitHubConfig(repos=["octo/hello"], token="ghp_x"))
    assert "Cloud" in repr(cloud)
    enterprise = GitHubConnector(
        GitHubConfig(repos=["octo/hello"], token="ghp_x", host="github.example.com")
    )
    assert "Enterprise" in repr(enterprise)


def test_requires_repos_or_project():
    with pytest.raises(Exception, match="repos.*project|project.*repos"):
        GitHubConnector(GitHubConfig(repos=[], project=None, token="ghp_x"))


def test_meta_identity():
    assert GitHubConnector.META.name == "github"
    assert GitHubConnector.META.config_class is GitHubConfig


def test_config_spec_has_expected_fields():
    spec = GitHubConnector.config_spec()
    assert set(["repos", "project", "host", "token", "state"]).issubset(spec.keys())
    assert spec["token"]["secret"] is True


def test_from_config_registers_and_binds():
    config_service = MagicMock()
    provider = MagicMock()
    provider.get.return_value = GitHubConfig(repos=["octo/hello"], token="ghp_x")
    config_service.bind.return_value = provider

    connector = GitHubConnector.from_config(config_service)

    config_service.register.assert_called_once_with(GitHubConfig, path="sources.github")
    assert connector.connector_type == "github"


def test_base_connector_protocol_conformance():
    from indexed.protocols import BaseConnector

    connector = GitHubConnector(GitHubConfig(repos=["octo/hello"], token="ghp_x"))
    assert isinstance(connector, BaseConnector)


class _FakeReaderDetails:
    def __init__(self, data: dict) -> None:
        self._data = data

    def model_dump(self, by_alias: bool = True) -> dict:
        return self._data


class _FakeManifest:
    def __init__(self, reader_data: dict, last_modified: str | None) -> None:
        self.reader = _FakeReaderDetails(reader_data)
        self.last_modified_document_time = last_modified
        self.collection_name = "gh-test"


def _config_service_stub(config: GitHubConfig) -> MagicMock:
    config_service = MagicMock()
    provider = MagicMock()
    provider.get.return_value = config
    config_service.bind.return_value = provider
    return config_service


def test_from_manifest_overlays_repos_and_builds_connector():
    manifest = _FakeManifest({"repos": ["octo/hello"], "state": "open"}, None)
    config_service = _config_service_stub(GitHubConfig(repos=["octo/hello"], token="ghp_x", state="open"))

    run = GitHubConnector.from_manifest(manifest, config_service, storage_path="/tmp/x")

    assert isinstance(run, ConnectorRun)
    config_service.set_overlay.assert_any_call("sources.github.repos", ["octo/hello"])
    config_service.set_overlay.assert_any_call("sources.github.state", "open")


def test_from_manifest_missing_repos_and_project_raises():
    manifest = _FakeManifest({"repos": [], "project": None}, None)
    config_service = _config_service_stub(GitHubConfig(repos=[], token="ghp_x"))

    with pytest.raises(ConfigurationError, match="repos.*project|project.*repos"):
        GitHubConnector.from_manifest(manifest, config_service, storage_path="/tmp/x")


def test_from_manifest_applies_modified_since_with_safety_buffer():
    manifest = _FakeManifest({"repos": ["octo/hello"]}, "2026-06-20T10:01:00Z")
    config_service = _config_service_stub(GitHubConfig(repos=["octo/hello"], token="ghp_x"))

    GitHubConnector.from_manifest(manifest, config_service, storage_path="/tmp/x")

    calls = {c.args[0]: c.args[1] for c in config_service.set_overlay.call_args_list}
    assert calls["sources.github.modified_since"] == "2026-06-20T10:00:00Z"


def test_from_manifest_no_prior_modified_time_skips_overlay():
    manifest = _FakeManifest({"repos": ["octo/hello"]}, None)
    config_service = _config_service_stub(GitHubConfig(repos=["octo/hello"], token="ghp_x"))

    GitHubConnector.from_manifest(manifest, config_service, storage_path="/tmp/x")

    called_keys = [c.args[0] for c in config_service.set_overlay.call_args_list]
    assert "sources.github.modified_since" not in called_keys
