"""Tests for DocumentCollectionCreator update behavior."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock



class TestUpdateCollectionTimestamp:
    """Test that update operations correctly handle timestamps."""

    def test_update_refreshes_timestamp_when_no_documents_found(self):
        """Test that updatedTime is refreshed even when no new documents are found.
        
        This is a critical behavior change: previously, when an update found 0 new
        documents, the manifest wasn't updated at all, leaving stale timestamps.
        Now, we update the timestamp to indicate we checked for updates.
        """
        from core.v1.engine.core.documents_collection_creator import (
            DocumentCollectionCreator,
            OPERATION_TYPE,
        )

        # Create mock components
        mock_persister = Mock()
        mock_reader = Mock()
        mock_converter = Mock()
        mock_indexer = Mock()

        # Set up the persister to return an existing manifest
        old_timestamp = "2024-01-01T00:00:00+00:00"
        existing_manifest = {
            "collectionName": "test-collection",
            "updatedTime": old_timestamp,
            "lastModifiedDocumentTime": old_timestamp,
            "numberOfDocuments": 10,
            "numberOfChunks": 50,
            "reader": {"type": "localFiles"},
            "indexers": [{"name": "test-indexer"}],
        }
        
        mock_persister.is_path_exists.return_value = True
        mock_persister.read_text_file.return_value = json.dumps(existing_manifest)
        
        # Reader returns 0 documents (nothing new to update)
        mock_reader.get_number_of_documents.return_value = 0
        mock_reader.read_all_documents.return_value = iter([])

        # Create the updater
        creator = DocumentCollectionCreator(
            collection_name="test-collection",
            document_reader=mock_reader,
            document_converter=mock_converter,
            document_indexers=[mock_indexer],
            persister=mock_persister,
            operation_type=OPERATION_TYPE.UPDATE,
        )

        # Run the update
        creator.run()

        # Verify save_text_file was called (to update the manifest)
        assert mock_persister.save_text_file.called
        
        # Get the saved manifest content
        save_call_args = mock_persister.save_text_file.call_args_list[-1]
        saved_content = save_call_args[0][0]
        saved_path = save_call_args[0][1]
        
        # Verify it was saved to the manifest path
        assert "manifest.json" in saved_path
        
        # Parse and verify the saved manifest
        saved_manifest = json.loads(saved_content)
        
        # The updatedTime should be different from the old timestamp
        assert saved_manifest["updatedTime"] != old_timestamp
        
        # The new timestamp should be a valid ISO format
        new_timestamp = datetime.fromisoformat(saved_manifest["updatedTime"].replace("Z", "+00:00"))
        assert new_timestamp is not None
        
        # The new timestamp should be recent (within the last minute)
        now = datetime.now(timezone.utc)
        time_diff = now - new_timestamp
        assert time_diff.total_seconds() < 60

    def test_update_preserves_other_manifest_fields_when_no_documents(self):
        """Test that other manifest fields are preserved when updating timestamp only."""
        from core.v1.engine.core.documents_collection_creator import (
            DocumentCollectionCreator,
            OPERATION_TYPE,
        )

        mock_persister = Mock()
        mock_reader = Mock()
        mock_converter = Mock()
        mock_indexer = Mock()

        # Existing manifest with specific values
        existing_manifest = {
            "collectionName": "test-collection",
            "updatedTime": "2024-01-01T00:00:00+00:00",
            "lastModifiedDocumentTime": "2024-01-01T00:00:00+00:00",
            "numberOfDocuments": 10,
            "numberOfChunks": 50,
            "reader": {"type": "localFiles", "basePath": "/test/path"},
            "indexers": [{"name": "test-indexer"}],
        }
        
        mock_persister.is_path_exists.return_value = True
        mock_persister.read_text_file.return_value = json.dumps(existing_manifest)
        mock_reader.get_number_of_documents.return_value = 0
        mock_reader.read_all_documents.return_value = iter([])

        creator = DocumentCollectionCreator(
            collection_name="test-collection",
            document_reader=mock_reader,
            document_converter=mock_converter,
            document_indexers=[mock_indexer],
            persister=mock_persister,
            operation_type=OPERATION_TYPE.UPDATE,
        )

        creator.run()

        # Get saved manifest
        save_call_args = mock_persister.save_text_file.call_args_list[-1]
        saved_manifest = json.loads(save_call_args[0][0])
        
        # Verify other fields are preserved
        assert saved_manifest["collectionName"] == "test-collection"
        assert saved_manifest["numberOfDocuments"] == 10
        assert saved_manifest["numberOfChunks"] == 50
        assert saved_manifest["reader"]["type"] == "localFiles"
        assert saved_manifest["reader"]["basePath"] == "/test/path"
        assert saved_manifest["lastModifiedDocumentTime"] == "2024-01-01T00:00:00+00:00"

