"""Tests for the indexed-config exception hierarchy."""

from indexed_config.errors import ConfigurationError, missing_wiring_error


def test_missing_wiring_error_is_configuration_error() -> None:
    err = missing_wiring_error("connector_factory")

    assert isinstance(err, ConfigurationError)


def test_missing_wiring_error_names_component_and_bootstrap() -> None:
    err = missing_wiring_error("manifest_connector_factory")

    message = str(err)
    assert message == (
        "manifest_connector_factory must be injected by the app layer; "
        "see indexed.bootstrap"
    )
