"""Tests for DiskPersister path safety, atomic writes, and file operations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.v1.engine.persisters.disk_persister import DiskPersister


@pytest.fixture
def disk_persister(tmp_path: Path) -> DiskPersister:
    """Return a DiskPersister rooted at a fresh temp directory."""
    return DiskPersister(str(tmp_path))


class TestDiskPersisterPathSafety:
    """Verify that _safe_join rejects paths that escape base_path."""

    def test_safe_join_allows_valid_path(
        self, disk_persister: DiskPersister, tmp_path: Path
    ) -> None:
        """Valid relative paths resolve inside base_path."""
        result = disk_persister._safe_join(str(tmp_path), "subdir/file.txt")
        assert result.startswith(str(tmp_path))

    def test_safe_join_rejects_traversal(
        self, disk_persister: DiskPersister, tmp_path: Path
    ) -> None:
        """Paths using ../ that escape base_path raise ValueError."""
        with pytest.raises(ValueError, match="Path escapes"):
            disk_persister._safe_join(str(tmp_path), "../../etc/passwd")

    def test_safe_join_rejects_absolute_escape(
        self, disk_persister: DiskPersister, tmp_path: Path
    ) -> None:
        """Absolute paths outside base_path raise ValueError."""
        with pytest.raises(ValueError, match="Path escapes"):
            disk_persister._safe_join(str(tmp_path), "/etc/passwd")

    def test_is_path_exists_returns_false_for_traversal(
        self, disk_persister: DiskPersister
    ) -> None:
        """Path traversal attempts return False rather than raising."""
        assert disk_persister.is_path_exists("../../etc/passwd") is False

    def test_save_text_file_rejects_traversal(
        self, disk_persister: DiskPersister
    ) -> None:
        """save_text_file raises ValueError for traversal paths."""
        with pytest.raises(ValueError, match="Path escapes"):
            disk_persister.save_text_file("bad", "../outside.txt")

    def test_no_pickle_import(self) -> None:
        """pickle must not be imported in disk_persister."""
        import core.v1.engine.persisters.disk_persister as mod

        assert not hasattr(mod, "pickle")


class TestDiskPersisterFileOperations:
    """Basic file and folder operations."""

    def test_save_and_read_text_file(self, disk_persister: DiskPersister) -> None:
        """Round-trip through save_text_file / read_text_file."""
        disk_persister.save_text_file("hello", "test.txt")
        assert disk_persister.read_text_file("test.txt") == "hello"

    def test_save_text_file_is_atomic(
        self, disk_persister: DiskPersister, tmp_path: Path
    ) -> None:
        """No .tmp file remains after a successful save."""
        disk_persister.save_text_file("content", "out.txt")
        assert (tmp_path / "out.txt").read_text() == "content"
        assert not any(tmp_path.glob("*.tmp"))

    def test_save_text_file_cleans_up_tmp_on_error(
        self, disk_persister: DiskPersister, tmp_path: Path
    ) -> None:
        """When os.replace fails the .tmp file is cleaned up."""
        with patch("os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                disk_persister.save_text_file("data", "file.txt")
        assert not any(tmp_path.glob("*.tmp"))

    def test_create_and_remove_folder(
        self, disk_persister: DiskPersister, tmp_path: Path
    ) -> None:
        """create_folder creates the directory; remove_folder deletes it."""
        disk_persister.create_folder("mydir")
        assert (tmp_path / "mydir").is_dir()
        disk_persister.remove_folder("mydir")
        assert not (tmp_path / "mydir").exists()

    def test_remove_file(self, disk_persister: DiskPersister, tmp_path: Path) -> None:
        """remove_file deletes an existing file."""
        disk_persister.save_text_file("data", "f.txt")
        disk_persister.remove_file("f.txt")
        assert not (tmp_path / "f.txt").exists()

    def test_get_full_path(self, disk_persister: DiskPersister, tmp_path: Path) -> None:
        """get_full_path returns the real absolute path."""
        result = disk_persister.get_full_path("a/b.txt")
        assert result == str(tmp_path / "a" / "b.txt")

    def test_read_folder_files(self, disk_persister: DiskPersister) -> None:
        """read_folder_files lists relative paths of files in a subfolder."""
        disk_persister.save_text_file("x", "sub/a.txt")
        disk_persister.save_text_file("y", "sub/b.txt")
        assert sorted(disk_persister.read_folder_files("sub")) == ["a.txt", "b.txt"]


class TestDiskPersisterFaissOperations:
    """save_faiss_index and read_faiss_index use native faiss I/O atomically."""

    def test_save_faiss_index_is_atomic(
        self, disk_persister: DiskPersister, tmp_path: Path
    ) -> None:
        """save_faiss_index writes via tmp then renames; no .tmp remains."""
        mock_faiss = MagicMock()
        with patch.dict("sys.modules", {"faiss": mock_faiss}), patch("os.replace"):
            disk_persister.save_faiss_index(MagicMock(), "idx.faiss")
        assert mock_faiss.write_index.called
        assert not any(tmp_path.glob("*.tmp"))

    def test_save_faiss_index_cleans_up_on_error(
        self, disk_persister: DiskPersister, tmp_path: Path
    ) -> None:
        """When faiss.write_index raises the .tmp file is cleaned up."""
        mock_faiss = MagicMock()
        mock_faiss.write_index.side_effect = OSError("no space")
        with patch.dict("sys.modules", {"faiss": mock_faiss}):
            with pytest.raises(OSError, match="no space"):
                disk_persister.save_faiss_index(MagicMock(), "idx.faiss")
        assert not any(tmp_path.glob("*.tmp"))

    def test_read_faiss_index_mmap(
        self, disk_persister: DiskPersister, tmp_path: Path
    ) -> None:
        """read_faiss_index calls faiss.read_index with mmap flag."""
        mock_faiss = MagicMock()
        mock_faiss.IO_FLAG_MMAP = 2
        (tmp_path / "idx.faiss").write_bytes(b"")
        with patch.dict("sys.modules", {"faiss": mock_faiss}):
            disk_persister.read_faiss_index("idx.faiss", mmap=True)
        mock_faiss.read_index.assert_called_once()
        _, flags = mock_faiss.read_index.call_args[0]
        assert flags == 2

    def test_read_faiss_index_no_mmap(
        self, disk_persister: DiskPersister, tmp_path: Path
    ) -> None:
        """read_faiss_index passes 0 as flags when mmap=False."""
        mock_faiss = MagicMock()
        mock_faiss.IO_FLAG_MMAP = 2
        (tmp_path / "idx.faiss").write_bytes(b"")
        with patch.dict("sys.modules", {"faiss": mock_faiss}):
            disk_persister.read_faiss_index("idx.faiss", mmap=False)
        _, flags = mock_faiss.read_index.call_args[0]
        assert flags == 0


class TestDiskPersisterLegacyIndexError:
    """load_indexer must reject legacy pickle-format indexes."""

    def test_load_indexer_raises_on_legacy_pickle_file(self, tmp_path: Path) -> None:
        """ValueError is raised when only the legacy 'indexer' file exists."""
        from types import SimpleNamespace

        import core.v1.engine.indexes.indexer_factory as factory

        persister = MagicMock()
        persister.is_path_exists.side_effect = lambda path: path.endswith("/indexer")

        dummy_config = SimpleNamespace(model_name="dummy-model")

        with (
            patch.object(factory, "get_indexer_config", return_value=dummy_config),
            patch(
                "core.v1.engine.indexes.embeddings.sentence_embeder.SentenceEmbedder",
                return_value=MagicMock(),
            ),
        ):
            with pytest.raises(ValueError, match="legacy index format"):
                factory.load_indexer(
                    "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
                    "my-collection",
                    persister,
                )
