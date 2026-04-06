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
        new_timestamp = datetime.fromisoformat(
            saved_manifest["updatedTime"].replace("Z", "+00:00")
        )
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


class TestCreateCollection:
    """Test create collection operation."""

    def _make_creator(self, **overrides):
        from core.v1.engine.core.documents_collection_creator import (
            DocumentCollectionCreator,
            OPERATION_TYPE,
        )

        mock_persister = Mock()
        mock_reader = Mock()
        mock_converter = Mock()
        mock_indexer = Mock()

        defaults = dict(
            collection_name="test-col",
            document_reader=mock_reader,
            document_converter=mock_converter,
            document_indexers=[mock_indexer],
            persister=mock_persister,
            operation_type=OPERATION_TYPE.CREATE,
        )
        defaults.update(overrides)
        creator = DocumentCollectionCreator(**defaults)
        return creator, defaults

    def test_create_raises_when_no_documents(self):
        import pytest

        creator, parts = self._make_creator()
        parts["document_reader"].get_number_of_documents.return_value = 0
        parts["document_reader"].read_all_documents.return_value = iter([])

        with pytest.raises(ValueError, match="No documents found"):
            creator.run()

        # Folder should be cleaned up
        parts["persister"].remove_folder.assert_called()

    def test_create_raises_with_reader_details_in_error(self):
        import pytest

        mock_reader = Mock()
        mock_reader.get_number_of_documents.return_value = 0
        mock_reader.read_all_documents.return_value = iter([])
        mock_reader.base_path = "/some/path"
        mock_reader.include_patterns = ["*.md"]
        mock_reader.exclude_patterns = None
        # No nested .reader attribute
        mock_reader.reader = mock_reader

        creator, parts = self._make_creator(document_reader=mock_reader)

        with pytest.raises(ValueError, match="source path: /some/path"):
            creator.run()

    def test_create_success_with_documents(self):
        creator, parts = self._make_creator()
        reader = parts["document_reader"]
        converter = parts["document_converter"]
        indexer = parts["document_indexers"][0]
        persister = parts["persister"]

        doc_data = {
            "id": "doc1",
            "url": "http://test",
            "modifiedTime": "2026-01-01T00:00:00",
            "chunks": [{"indexedData": "chunk text"}],
        }

        reader.get_number_of_documents.return_value = 1
        reader.read_all_documents.return_value = iter([{"id": "raw1"}])
        reader.get_reader_details.return_value = {"type": "localFiles"}
        converter.convert.return_value = [doc_data]
        indexer.get_size.return_value = 1
        indexer.get_name.return_value = "test_indexer"
        indexer.get_faiss_index.return_value = Mock()
        indexer.serialize.return_value = b"binary"
        persister.read_folder_files.return_value = ["doc1.json"]
        # When reading back the document JSON during indexing
        persister.read_text_file.return_value = json.dumps(doc_data)

        creator.run()

        # Verify the collection was created
        persister.create_folder.assert_called_once_with("test-col")
        indexer.index_texts.assert_called_once()
        persister.save_faiss_index.assert_called_once()

    def test_create_with_phased_progress(self):
        phased = Mock()
        creator, parts = self._make_creator(phased_progress=phased)
        reader = parts["document_reader"]
        converter = parts["document_converter"]
        indexer = parts["document_indexers"][0]
        persister = parts["persister"]

        doc_data = {
            "id": "doc1",
            "url": "http://test",
            "modifiedTime": "2026-01-01T00:00:00",
            "chunks": [{"indexedData": "chunk text"}],
        }

        reader.get_number_of_documents.return_value = 1
        reader.read_all_documents.return_value = iter([{"id": "raw1"}])
        reader.get_reader_details.return_value = {"type": "localFiles"}
        converter.convert.return_value = [doc_data]
        indexer.get_size.return_value = 1
        indexer.get_name.return_value = "test_indexer"
        indexer.get_faiss_index.return_value = Mock()
        indexer.serialize.return_value = b"binary"
        persister.read_folder_files.return_value = ["doc1.json"]
        persister.read_text_file.return_value = json.dumps(doc_data)

        creator.run()

        phased.start_phase.assert_called()
        phased.finish_phase.assert_called()


class TestUpdateCollectionWithDeletions:
    """Test update with explicit deletions."""

    def test_update_with_explicit_deletions_only(self):
        from core.v1.engine.core.documents_collection_creator import (
            DocumentCollectionCreator,
            OPERATION_TYPE,
        )

        mock_persister = Mock()
        mock_reader = Mock()
        mock_converter = Mock()
        mock_indexer = Mock()

        existing_manifest = json.dumps(
            {
                "collectionName": "test-col",
                "updatedTime": "2024-01-01T00:00:00+00:00",
                "lastModifiedDocumentTime": "2024-01-01T00:00:00+00:00",
                "numberOfDocuments": 10,
                "numberOfChunks": 50,
            }
        )

        mock_persister.is_path_exists.return_value = True
        mock_persister.read_text_file.return_value = existing_manifest
        mock_persister.read_folder_files.return_value = ["doc1.json"] * 9
        mock_reader.get_number_of_documents.return_value = 0
        mock_reader.read_all_documents.return_value = iter([])
        mock_indexer.get_size.return_value = 45

        index_mapping = json.dumps({"0": {"documentId": "deleted.txt"}})
        reverse_mapping = json.dumps({"deleted.txt": [0]})

        # Set up read_text_file to return different values based on path
        def read_text_side_effect(path):
            if "manifest.json" in path:
                return existing_manifest
            if "index_document_mapping" in path:
                return index_mapping
            if "reverse_index_document_mapping" in path:
                return reverse_mapping
            if "index_info" in path:
                return json.dumps({"lastIndexItemId": 49})
            return "{}"

        mock_persister.read_text_file.side_effect = read_text_side_effect

        creator = DocumentCollectionCreator(
            collection_name="test-col",
            document_reader=mock_reader,
            document_converter=mock_converter,
            document_indexers=[mock_indexer],
            persister=mock_persister,
            operation_type=OPERATION_TYPE.UPDATE,
            explicit_deletions=["deleted.txt"],
        )

        creator.run()

        # Should update manifest with new counts
        assert mock_persister.save_text_file.called


class TestUpdateCollectionNonExistent:
    """Test update on non-existent collection."""

    def test_update_raises_when_collection_missing(self):
        import pytest
        from core.v1.engine.core.documents_collection_creator import (
            DocumentCollectionCreator,
            OPERATION_TYPE,
        )

        mock_persister = Mock()
        mock_persister.is_path_exists.return_value = False

        creator = DocumentCollectionCreator(
            collection_name="missing-col",
            document_reader=Mock(),
            document_converter=Mock(),
            document_indexers=[Mock()],
            persister=mock_persister,
            operation_type=OPERATION_TYPE.UPDATE,
        )

        with pytest.raises(Exception, match="does not exist"):
            creator.run()


class TestOperationType:
    """Test OPERATION_TYPE enum and run dispatch."""

    def test_unknown_operation_type_raises(self):
        import pytest
        from core.v1.engine.core.documents_collection_creator import (
            DocumentCollectionCreator,
        )

        creator = DocumentCollectionCreator(
            collection_name="test",
            document_reader=Mock(),
            document_converter=Mock(),
            document_indexers=[Mock()],
            persister=Mock(),
        )
        # Manually set invalid operation type
        creator.operation_type = "invalid"

        with pytest.raises(ValueError, match="Unknown operation type"):
            creator.run()
