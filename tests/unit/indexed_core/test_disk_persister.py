"""Tests for DiskPersister path safety and file operations."""

import os
import pytest


class TestDiskPersisterPathSafety:
    def test_safe_join_allows_valid_path(self, tmp_path):
        from core.v1.engine.persisters.disk_persister import DiskPersister

        p = DiskPersister(str(tmp_path))
        result = p._safe_join(str(tmp_path), "subdir/file.txt")
        assert result.startswith(str(tmp_path))

    def test_safe_join_rejects_traversal(self, tmp_path):
        from core.v1.engine.persisters.disk_persister import DiskPersister

        p = DiskPersister(str(tmp_path))
        with pytest.raises(ValueError, match="Path escapes"):
            p._safe_join(str(tmp_path), "../../etc/passwd")

    def test_safe_join_rejects_absolute_escape(self, tmp_path):
        from core.v1.engine.persisters.disk_persister import DiskPersister

        p = DiskPersister(str(tmp_path))
        with pytest.raises(ValueError, match="Path escapes"):
            p._safe_join(str(tmp_path), "/etc/passwd")

    def test_is_path_exists_returns_false_for_traversal(self, tmp_path):
        from core.v1.engine.persisters.disk_persister import DiskPersister

        p = DiskPersister(str(tmp_path))
        assert p.is_path_exists("../../etc/passwd") is False

    def test_save_and_read_text_file(self, tmp_path):
        from core.v1.engine.persisters.disk_persister import DiskPersister

        p = DiskPersister(str(tmp_path))
        p.save_text_file("hello", "test.txt")
        assert p.read_text_file("test.txt") == "hello"

    def test_save_text_file_rejects_traversal(self, tmp_path):
        from core.v1.engine.persisters.disk_persister import DiskPersister

        p = DiskPersister(str(tmp_path))
        with pytest.raises(ValueError, match="Path escapes"):
            p.save_text_file("bad", "../outside.txt")

    def test_create_and_remove_folder(self, tmp_path):
        from core.v1.engine.persisters.disk_persister import DiskPersister

        p = DiskPersister(str(tmp_path))
        p.create_folder("mydir")
        assert os.path.isdir(tmp_path / "mydir")
        p.remove_folder("mydir")
        assert not os.path.exists(tmp_path / "mydir")

    def test_remove_file(self, tmp_path):
        from core.v1.engine.persisters.disk_persister import DiskPersister

        p = DiskPersister(str(tmp_path))
        p.save_text_file("data", "f.txt")
        p.remove_file("f.txt")
        assert not os.path.exists(tmp_path / "f.txt")

    def test_get_full_path(self, tmp_path):
        from core.v1.engine.persisters.disk_persister import DiskPersister

        p = DiskPersister(str(tmp_path))
        result = p.get_full_path("a/b.txt")
        assert result == str(tmp_path / "a" / "b.txt")

    def test_read_folder_files(self, tmp_path):
        from core.v1.engine.persisters.disk_persister import DiskPersister

        p = DiskPersister(str(tmp_path))
        p.save_text_file("x", "sub/a.txt")
        p.save_text_file("y", "sub/b.txt")
        files = p.read_folder_files("sub")
        assert sorted(files) == ["a.txt", "b.txt"]

    def test_no_pickle_import(self):
        import core.v1.engine.persisters.disk_persister as mod

        assert not hasattr(mod, "pickle"), (
            "pickle must not be imported in disk_persister"
        )


class TestDiskPersisterLegacyIndexError:
    def test_load_indexer_raises_on_legacy_pickle_file(self, tmp_path):
        from unittest.mock import MagicMock

        from core.v1.engine.indexes.indexer_factory import load_indexer

        persister = MagicMock()
        persister.is_path_exists.side_effect = lambda path: path.endswith("/indexer")

        with pytest.raises(ValueError, match="legacy index format"):
            load_indexer(
                "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
                "my-collection",
                persister,
            )
