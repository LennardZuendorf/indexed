"""Tests for core.v2.storage — collection persistence."""

from pathlib import Path

import pytest

from core.v2.errors import CollectionNotFoundError
from core.v2.storage import (
    get_collection_path,
    list_collection_names,
    read_manifest,
    remove_collection,
    write_manifest,
)


class TestGetCollectionPath:
    """get_collection_path resolves a path under the collections dir."""

    def test_with_explicit_dir(self, tmp_path: Path) -> None:
        path = get_collection_path("my-docs", collections_dir=tmp_path)
        assert path == tmp_path / "my-docs"

    def test_different_names(self, tmp_path: Path) -> None:
        p1 = get_collection_path("a", collections_dir=tmp_path)
        p2 = get_collection_path("b", collections_dir=tmp_path)
        assert p1 != p2


class TestCollectionNameValidation:
    """get_collection_path rejects names that could escape the root."""

    def test_rejects_dotdot(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match=r"\.\.|outside"):
            get_collection_path("../etc", collections_dir=tmp_path)

    def test_rejects_absolute(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="absolute"):
            get_collection_path("/etc/passwd", collections_dir=tmp_path)

    def test_rejects_multi_segment(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="single path segment"):
            get_collection_path("a/b", collections_dir=tmp_path)

    def test_rejects_empty(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="empty"):
            get_collection_path("", collections_dir=tmp_path)

    def test_rejects_whitespace(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="empty"):
            get_collection_path("   ", collections_dir=tmp_path)


class TestWriteManifest:
    """write_manifest creates a manifest.json file."""

    def test_creates_manifest_file(self, tmp_path: Path) -> None:
        write_manifest(
            "test-col",
            num_documents=10,
            num_chunks=50,
            collections_dir=tmp_path,
        )
        manifest_path = tmp_path / "test-col" / "manifest.json"
        assert manifest_path.exists()

    def test_manifest_content(self, tmp_path: Path) -> None:
        result = write_manifest(
            "test-col",
            num_documents=10,
            num_chunks=50,
            source_type="localFiles",
            embed_model_name="all-mpnet-base-v2",
            vector_store_type="faiss",
            collections_dir=tmp_path,
        )
        assert result["name"] == "test-col"
        assert result["version"] == "2.0"
        assert result["num_documents"] == 10
        assert result["num_chunks"] == 50
        assert result["source_type"] == "localFiles"
        assert result["embed_model_name"] == "all-mpnet-base-v2"
        assert "created_time" in result
        assert "updated_time" in result

    def test_manifest_defaults(self, tmp_path: Path) -> None:
        result = write_manifest(
            "col", num_documents=0, num_chunks=0, collections_dir=tmp_path
        )
        assert result["embed_model_name"] == "all-MiniLM-L6-v2"
        assert result["vector_store_type"] == "faiss"
        assert result["source_type"] == ""


class TestReadManifest:
    """read_manifest reads a collection's manifest.json."""

    def test_round_trip(self, tmp_path: Path) -> None:
        write_manifest("col", num_documents=5, num_chunks=25, collections_dir=tmp_path)
        manifest = read_manifest("col", collections_dir=tmp_path)
        assert manifest["name"] == "col"
        assert manifest["num_documents"] == 5

    def test_missing_collection_raises(self, tmp_path: Path) -> None:
        with pytest.raises(CollectionNotFoundError, match="nonexistent"):
            read_manifest("nonexistent", collections_dir=tmp_path)


class TestRemoveCollection:
    """remove_collection deletes a collection directory."""

    def test_removes_existing(self, tmp_path: Path) -> None:
        col_dir = tmp_path / "col"
        col_dir.mkdir()
        (col_dir / "manifest.json").write_text("{}")

        assert remove_collection("col", collections_dir=tmp_path) is True
        assert not col_dir.exists()

    def test_nonexistent_returns_false(self, tmp_path: Path) -> None:
        assert remove_collection("nope", collections_dir=tmp_path) is False


class TestListCollectionNames:
    """list_collection_names scans for directories with manifest.json."""

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert list_collection_names(collections_dir=tmp_path) == []

    def test_finds_collections_with_manifest(self, tmp_path: Path) -> None:
        for name in ["beta", "alpha"]:
            d = tmp_path / name
            d.mkdir()
            (d / "manifest.json").write_text("{}")

        # Also create a dir without manifest (should be ignored)
        (tmp_path / "no-manifest").mkdir()

        result = list_collection_names(collections_dir=tmp_path)
        assert result == ["alpha", "beta"]  # sorted

    def test_missing_dir_returns_empty(self) -> None:
        result = list_collection_names(
            collections_dir=Path("/tmp/does-not-exist-indexed-test")
        )
        assert result == []
