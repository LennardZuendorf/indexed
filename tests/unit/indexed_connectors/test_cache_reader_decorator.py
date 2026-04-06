"""Tests for CacheReaderDecorator."""

from unittest.mock import Mock

from connectors.document_cache_reader_decorator import CacheReaderDecorator


class TestCacheReaderDecoratorHit:
    """Test cache hit scenarios."""

    def test_cache_hit_yields_from_persister(self):
        reader = Mock()
        reader.get_reader_details.return_value = {"type": "test"}
        persister = Mock()
        persister.is_path_exists.return_value = True
        persister.read_folder_files.return_value = ["0.json", "1.json"]
        persister.read_text_file.side_effect = [
            '{"id": "doc0"}',
            '{"id": "doc1"}',
        ]

        decorator = CacheReaderDecorator(reader, persister)
        docs = list(decorator.read_all_documents())

        assert len(docs) == 2
        assert docs[0] == {"id": "doc0"}
        assert docs[1] == {"id": "doc1"}
        # Reader should NOT be called on cache hit
        reader.read_all_documents.assert_not_called()

    def test_cache_hit_get_number_of_documents(self):
        reader = Mock()
        reader.get_reader_details.return_value = {"type": "test"}
        persister = Mock()
        persister.is_path_exists.return_value = True
        persister.read_folder_files.return_value = ["0.json", "1.json", "2.json"]

        decorator = CacheReaderDecorator(reader, persister)
        count = decorator.get_number_of_documents()

        assert count == 3
        reader.get_number_of_documents.assert_not_called()


class TestCacheReaderDecoratorMiss:
    """Test cache miss scenarios."""

    def test_cache_miss_reads_from_reader_and_persists(self):
        reader = Mock()
        reader.get_reader_details.return_value = {"type": "test"}
        reader.read_all_documents.return_value = iter(
            [{"id": "doc0"}, {"id": "doc1"}]
        )
        persister = Mock()
        persister.is_path_exists.return_value = False

        decorator = CacheReaderDecorator(reader, persister)
        docs = list(decorator.read_all_documents())

        assert len(docs) == 2
        assert docs[0] == {"id": "doc0"}
        # Persister should have saved the documents
        assert persister.save_text_file.call_count >= 3  # 2 docs + 1 completion marker

    def test_cache_miss_empty_results_not_cached(self):
        reader = Mock()
        reader.get_reader_details.return_value = {"type": "test"}
        reader.read_all_documents.return_value = iter([])
        persister = Mock()
        persister.is_path_exists.return_value = False

        decorator = CacheReaderDecorator(reader, persister)
        docs = list(decorator.read_all_documents())

        assert docs == []
        # Cache folder should be removed for empty results
        persister.remove_folder.assert_called()

    def test_cache_miss_get_number_of_documents_delegates(self):
        reader = Mock()
        reader.get_reader_details.return_value = {"type": "test"}
        reader.get_number_of_documents.return_value = 5
        persister = Mock()
        persister.is_path_exists.return_value = False

        decorator = CacheReaderDecorator(reader, persister)
        count = decorator.get_number_of_documents()

        assert count == 5
        reader.get_number_of_documents.assert_called_once()


class TestCacheReaderDecoratorOther:
    """Test other methods."""

    def test_get_reader_details_delegates(self):
        reader = Mock()
        reader.get_reader_details.return_value = {"type": "test", "path": "/docs"}
        persister = Mock()

        decorator = CacheReaderDecorator(reader, persister)
        details = decorator.get_reader_details()

        assert details == {"type": "test", "path": "/docs"}

    def test_remove_cache(self):
        reader = Mock()
        reader.get_reader_details.return_value = {"type": "test"}
        persister = Mock()

        decorator = CacheReaderDecorator(reader, persister)
        decorator.remove_cache()

        persister.remove_folder.assert_called_once()
        persister.remove_file.assert_called_once()

    def test_cache_key_deterministic(self):
        reader = Mock()
        reader.get_reader_details.return_value = {"type": "test", "path": "/a"}
        persister = Mock()

        d1 = CacheReaderDecorator(reader, persister)
        d2 = CacheReaderDecorator(reader, persister)

        # Same reader details should produce same cache key
        key1 = d1._CacheReaderDecorator__build_cache_key()
        key2 = d2._CacheReaderDecorator__build_cache_key()
        assert key1 == key2

    def test_different_readers_produce_different_keys(self):
        persister = Mock()

        reader1 = Mock()
        reader1.get_reader_details.return_value = {"type": "test", "path": "/a"}
        reader2 = Mock()
        reader2.get_reader_details.return_value = {"type": "test", "path": "/b"}

        d1 = CacheReaderDecorator(reader1, persister)
        d2 = CacheReaderDecorator(reader2, persister)

        key1 = d1._CacheReaderDecorator__build_cache_key()
        key2 = d2._CacheReaderDecorator__build_cache_key()
        assert key1 != key2
