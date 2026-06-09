"""Tests for Outline config population during collection updates."""

import os
from unittest.mock import MagicMock, patch

import pytest

from core.v1.engine.factories.update_collection_factory import (
    _OUTLINE_MODIFIED_SINCE_ENV,
    _create_reader_and_converter,
    _populate_outline_config,
)


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
    def test_modified_since_applied_via_ephemeral_env_var(self) -> None:
        manifest = {
            "reader": {
                "type": "outline",
                "baseUrl": "https://outline.example.com",
                "collectionIds": ["col-1"],
                "includeAttachments": True,
                "ocrEnabled": True,
            },
            "indexers": [{"name": "FAISS"}],
            "lastModifiedDocumentTime": "2026-03-15T10:00:00+00:00",
        }

        mock_reader = MagicMock()
        mock_converter = MagicMock()
        mock_connector = MagicMock()
        mock_connector.reader = mock_reader
        mock_connector.converter = mock_converter

        captured_env: list[str | None] = []

        def capture_from_config(_config_service: object) -> MagicMock:
            captured_env.append(os.environ.get(_OUTLINE_MODIFIED_SINCE_ENV))
            return mock_connector

        mock_connector_cls = MagicMock()
        mock_connector_cls.from_config.side_effect = capture_from_config

        with (
            patch("indexed_config.ConfigService") as mock_config_service_cls,
            patch(
                "connectors.get_connector_class",
                return_value=mock_connector_cls,
            ),
            patch(
                "connectors.get_config_namespace",
                return_value="sources.outline",
            ),
            patch.dict(os.environ, {"OUTLINE_API_TOKEN": "ol_api_test"}, clear=False),
        ):
            mock_config_service = mock_config_service_cls.return_value
            reader, converter = _create_reader_and_converter(manifest)

        assert reader is mock_reader
        assert converter is mock_converter
        assert captured_env == ["2026-03-15T10:00:00+00:00"]
        assert _OUTLINE_MODIFIED_SINCE_ENV not in os.environ
        modified_since_calls = [
            call
            for call in mock_config_service.set.call_args_list
            if call.args[0].endswith(".modified_since")
        ]
        assert modified_since_calls == []
