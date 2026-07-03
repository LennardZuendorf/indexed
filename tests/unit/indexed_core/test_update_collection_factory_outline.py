"""Tests for Outline config population during collection updates."""

from unittest.mock import MagicMock

import pytest

from indexed_config.errors import ConfigurationError

from core.v1.engine.factories.update_collection_factory import (
    _create_reader_and_converter,
)
from indexed.connector_wiring import _populate_outline_config


@pytest.mark.unit
class TestPopulateOutlineConfig:
    def test_populates_outline_fields_from_manifest(self) -> None:
        config_service = MagicMock()
        reader_config = {
            "type": "outline",
            "baseUrl": "https://outline.example.com",
            "collectionIds": ["col-1", "col-2"],
            "batchSize": 25,
            "includeAttachments": False,
            "ocrEnabled": False,
        }

        _populate_outline_config(config_service, reader_config, "sources.outline")

        config_service.set.assert_any_call(
            "sources.outline.url", "https://outline.example.com"
        )
        config_service.set.assert_any_call(
            "sources.outline.collection_ids", ["col-1", "col-2"]
        )
        config_service.set.assert_any_call("sources.outline.include_attachments", False)
        config_service.set.assert_any_call("sources.outline.batch_size", 25)
        config_service.set.assert_any_call("sources.outline.ocr_enabled", False)

        modified_since_calls = [
            call
            for call in config_service.set.call_args_list
            if call.args[0].endswith(".modified_since")
        ]
        assert modified_since_calls == []


@pytest.mark.unit
class TestCreateReaderAndConverterOutline:
    def test_raises_when_factory_not_injected(self) -> None:
        manifest = {
            "reader": {"type": "outline", "baseUrl": "https://outline.example.com"},
            "indexers": [{"name": "FAISS"}],
        }

        with pytest.raises(ConfigurationError, match="manifest_connector_factory"):
            _create_reader_and_converter(manifest)

    def test_delegates_to_manifest_connector_factory(self) -> None:
        manifest = {
            "reader": {
                "type": "outline",
                "baseUrl": "https://outline.example.com",
                "collectionIds": ["col-1"],
            },
            "indexers": [{"name": "FAISS"}],
            "lastModifiedDocumentTime": "2026-03-15T10:00:00+00:00",
        }

        mock_reader = MagicMock()
        mock_converter = MagicMock()
        factory = MagicMock(return_value=(mock_reader, mock_converter))

        reader, converter = _create_reader_and_converter(
            manifest, manifest_connector_factory=factory
        )

        factory.assert_called_once_with(manifest)
        assert reader is mock_reader
        assert converter is mock_converter
