"""Tests for core.v2.ingestion — collection creation pipeline."""

from unittest.mock import MagicMock, patch

import pytest

from core.v2.errors import IngestionError
from core.v2.ingestion import create_collection

# Patch targets: LlamaIndex imports happen inside create_collection body,
# so we patch them at the llama_index source.
_PATCH_VSI = "llama_index.core.VectorStoreIndex"
_PATCH_EMBED = "core.v2.embedding.get_embed_model"


def _make_mock_connector(num_docs: int = 2, chunks_per_doc: int = 2) -> MagicMock:
    """Create a mock connector that produces v1-format output."""
    connector = MagicMock()
    connector.connector_type = "localFiles"

    raw_docs = [f"raw_doc_{i}" for i in range(num_docs)]
    connector.reader.read_all_documents.return_value = iter(raw_docs)

    def convert_side_effect(raw_doc: str) -> list:
        doc_idx = raw_docs.index(raw_doc) if raw_doc in raw_docs else 0
        return [
            {
                "id": f"doc-{doc_idx}",
                "url": f"file:///doc-{doc_idx}",
                "modifiedTime": "2026-01-01",
                "text": f"doc {doc_idx} text",
                "chunks": [
                    {"indexedData": f"doc-{doc_idx} chunk {j}"}
                    for j in range(chunks_per_doc)
                ],
            }
        ]

    connector.converter.convert.side_effect = convert_side_effect
    return connector


def _mock_embed_model() -> MagicMock:
    mock = MagicMock()
    mock.get_query_embedding.return_value = [0.0] * 384
    return mock


class TestCreateCollection:
    """create_collection orchestrates the full ingestion pipeline."""

    @patch(_PATCH_VSI)
    @patch(_PATCH_EMBED)
    def test_calls_vector_store_index(
        self, mock_get_embed, mock_vsi, tmp_path
    ) -> None:
        mock_get_embed.return_value = _mock_embed_model()
        connector = _make_mock_connector(num_docs=1, chunks_per_doc=2)

        result = create_collection("test-col", connector, collections_dir=tmp_path)

        mock_vsi.assert_called_once()
        nodes = mock_vsi.call_args.kwargs["nodes"]
        assert len(nodes) == 2
        assert result["name"] == "test-col"
        assert result["num_chunks"] == 2

    @patch(_PATCH_VSI)
    @patch(_PATCH_EMBED)
    def test_empty_connector_raises(
        self, mock_get_embed, mock_vsi, tmp_path
    ) -> None:
        mock_get_embed.return_value = _mock_embed_model()
        connector = MagicMock()
        connector.reader.read_all_documents.return_value = iter([])

        with pytest.raises(IngestionError, match="No documents found"):
            create_collection("empty", connector, collections_dir=tmp_path)

    @patch(_PATCH_VSI)
    @patch(_PATCH_EMBED)
    def test_removes_existing_collection_first(
        self, mock_get_embed, mock_vsi, tmp_path
    ) -> None:
        (tmp_path / "test-col").mkdir()
        (tmp_path / "test-col" / "old-data.json").write_text("{}")

        mock_get_embed.return_value = _mock_embed_model()
        connector = _make_mock_connector(num_docs=1, chunks_per_doc=1)
        create_collection("test-col", connector, collections_dir=tmp_path)

        assert not (tmp_path / "test-col" / "old-data.json").exists()

    @patch(_PATCH_VSI)
    @patch(_PATCH_EMBED)
    def test_progress_callback(
        self, mock_get_embed, mock_vsi, tmp_path
    ) -> None:
        mock_get_embed.return_value = _mock_embed_model()
        connector = _make_mock_connector(num_docs=1, chunks_per_doc=1)
        progress = MagicMock()

        create_collection(
            "col", connector, collections_dir=tmp_path, progress=progress
        )

        phase_names = [call.args[0] for call in progress.start_phase.call_args_list]
        assert "Fetching documents" in phase_names
        assert "Generating embeddings" in phase_names
        assert "Writing to disk" in phase_names

    @patch(_PATCH_VSI)
    @patch(_PATCH_EMBED)
    def test_manifest_counts_unique_docs(
        self, mock_get_embed, mock_vsi, tmp_path
    ) -> None:
        mock_get_embed.return_value = _mock_embed_model()
        connector = _make_mock_connector(num_docs=3, chunks_per_doc=2)
        result = create_collection("col", connector, collections_dir=tmp_path)

        assert result["num_documents"] == 3
        assert result["num_chunks"] == 6

    @patch(_PATCH_VSI, side_effect=RuntimeError("FAISS error"))
    @patch(_PATCH_EMBED)
    def test_index_build_failure_raises(
        self, mock_get_embed, mock_vsi, tmp_path
    ) -> None:
        mock_get_embed.return_value = _mock_embed_model()
        connector = _make_mock_connector(num_docs=1, chunks_per_doc=1)

        with pytest.raises(IngestionError, match="Failed to build index"):
            create_collection("col", connector, collections_dir=tmp_path)
