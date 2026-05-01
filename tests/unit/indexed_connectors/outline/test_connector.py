"""Tests for OutlineConnector instantiation and protocol compliance."""

import pytest
from unittest.mock import MagicMock

from connectors.outline.connector import OutlineConnector
from connectors.outline.schema import OutlineConfig, OUTLINE_CLOUD_URL


@pytest.fixture
def cloud_config() -> OutlineConfig:
    return OutlineConfig(api_token="ol_api_test_cloud")


@pytest.fixture
def selfhosted_config() -> OutlineConfig:
    return OutlineConfig(url="https://wiki.acme.internal", api_token="ol_api_test_sh")


def test_connector_type(cloud_config: OutlineConfig) -> None:
    connector = OutlineConnector(cloud_config)
    assert connector.connector_type == "outline"


def test_reader_and_converter_exposed(cloud_config: OutlineConfig) -> None:
    connector = OutlineConnector(cloud_config)
    assert connector.reader is not None
    assert connector.converter is not None


def test_repr_cloud(cloud_config: OutlineConfig) -> None:
    connector = OutlineConnector(cloud_config)
    r = repr(connector)
    assert "OutlineConnector" in r
    assert "Cloud" in r


def test_repr_selfhosted(selfhosted_config: OutlineConfig) -> None:
    connector = OutlineConnector(selfhosted_config)
    r = repr(connector)
    assert "self-hosted" in r
    assert "wiki.acme.internal" in r


def test_from_config_round_trip() -> None:
    mock_config_service = MagicMock()
    mock_provider = MagicMock()
    mock_config_service.bind.return_value = mock_provider
    mock_provider.get.return_value = OutlineConfig(api_token="ol_api_test")

    connector = OutlineConnector.from_config(mock_config_service)

    mock_config_service.register.assert_called_once_with(
        OutlineConfig, path="sources.outline"
    )
    assert connector.connector_type == "outline"


def test_default_url_is_cloud() -> None:
    cfg = OutlineConfig(api_token="ol_api_test")
    assert cfg.url == OUTLINE_CLOUD_URL
    assert cfg.is_cloud() is True


def test_selfhosted_not_cloud(selfhosted_config: OutlineConfig) -> None:
    assert selfhosted_config.is_cloud() is False


def test_trailing_slash_stripped() -> None:
    cfg = OutlineConfig(url="https://wiki.acme.internal/", api_token="tok")
    assert cfg.url == "https://wiki.acme.internal"


def test_get_api_token_from_config(cloud_config: OutlineConfig) -> None:
    assert cloud_config.get_api_token() == "ol_api_test_cloud"


def test_get_api_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OUTLINE_API_TOKEN", "ol_api_from_env")
    cfg = OutlineConfig()
    assert cfg.get_api_token() == "ol_api_from_env"


def test_get_api_token_missing_raises() -> None:
    cfg = OutlineConfig()
    with pytest.raises(ValueError, match="OUTLINE_API_TOKEN"):
        cfg.get_api_token()


def test_meta_name() -> None:
    assert OutlineConnector.META.name == "outline"


def test_meta_display_name_mentions_selfhosted() -> None:
    assert "self-hosted" in OutlineConnector.META.display_name.lower()
