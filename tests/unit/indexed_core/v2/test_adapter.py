"""Tests for core.v2.adapter — connector-to-LlamaIndex bridge."""

from unittest.mock import MagicMock


from core.v2.adapter import connector_to_nodes, _converted_doc_to_nodes


def _make_converted_doc(
    doc_id: str = "doc-1",
    url: str = "https://example.com/doc-1",
    num_chunks: int = 2,
) -> dict:
    """Create a v1-format converted document dict."""
    return {
        "id": doc_id,
        "url": url,
        "modifiedTime": "2026-01-01T00:00:00",
        "text": "full document text",
        "chunks": [
            {"indexedData": f"chunk {i} text", "metadata": {"page": i}}
            for i in range(num_chunks)
        ],
    }


class TestConvertedDocToNodes:
    """_converted_doc_to_nodes converts a single v1 dict to TextNodes."""

    def test_creates_nodes_for_each_chunk(self) -> None:
        doc = _make_converted_doc(num_chunks=3)
        nodes = _converted_doc_to_nodes(doc, "test-collection")
        assert len(nodes) == 3

    def test_deterministic_node_ids(self) -> None:
        doc = _make_converted_doc(doc_id="my-doc", num_chunks=2)
        nodes = _converted_doc_to_nodes(doc, "col")
        assert nodes[0].id_ == "my-doc__chunk_0"
        assert nodes[1].id_ == "my-doc__chunk_1"

    def test_node_text_from_indexed_data(self) -> None:
        doc = _make_converted_doc(num_chunks=1)
        nodes = _converted_doc_to_nodes(doc, "col")
        assert nodes[0].text == "chunk 0 text"

    def test_metadata_includes_source_fields(self) -> None:
        doc = _make_converted_doc(doc_id="d1", url="http://x.com")
        nodes = _converted_doc_to_nodes(doc, "my-col")
        meta = nodes[0].metadata
        assert meta["source_id"] == "d1"
        assert meta["url"] == "http://x.com"
        assert meta["collection_name"] == "my-col"
        assert meta["chunk_index"] == 0

    def test_chunk_metadata_merged(self) -> None:
        doc = _make_converted_doc(num_chunks=1)
        doc["chunks"][0]["metadata"] = {"page": 5, "heading": "Intro"}
        nodes = _converted_doc_to_nodes(doc, "col")
        assert nodes[0].metadata["page"] == 5
        assert nodes[0].metadata["heading"] == "Intro"

    def test_skips_empty_chunks(self) -> None:
        doc = _make_converted_doc(num_chunks=0)
        doc["chunks"] = [{"indexedData": ""}, {"indexedData": "real text"}]
        nodes = _converted_doc_to_nodes(doc, "col")
        assert len(nodes) == 1
        assert nodes[0].text == "real text"

    def test_handles_missing_optional_fields(self) -> None:
        doc = {"id": "d1", "chunks": [{"indexedData": "text"}]}
        nodes = _converted_doc_to_nodes(doc, "col")
        assert len(nodes) == 1
        assert nodes[0].metadata["url"] == ""
        assert nodes[0].metadata["modified_time"] == ""


class TestConnectorToNodes:
    """connector_to_nodes orchestrates reader + converter to TextNodes."""

    def test_converts_all_documents(self) -> None:
        doc1 = _make_converted_doc(doc_id="a", num_chunks=2)
        doc2 = _make_converted_doc(doc_id="b", num_chunks=1)

        reader = MagicMock()
        reader.read_all_documents.return_value = iter(["raw1", "raw2"])
        converter = MagicMock()
        converter.convert.side_effect = [[doc1], [doc2]]

        nodes = connector_to_nodes(reader, converter, "col")
        assert len(nodes) == 3

    def test_empty_reader_returns_empty(self) -> None:
        reader = MagicMock()
        reader.read_all_documents.return_value = iter([])
        converter = MagicMock()

        nodes = connector_to_nodes(reader, converter, "col")
        assert nodes == []

    def test_progress_callback_invoked(self) -> None:
        doc = _make_converted_doc(num_chunks=1)
        reader = MagicMock()
        reader.read_all_documents.return_value = iter(["raw1"])
        converter = MagicMock()
        converter.convert.return_value = [doc]
        progress = MagicMock()

        connector_to_nodes(reader, converter, "col", progress=progress)

        progress.start_phase.assert_called_once_with("Fetching documents")
        progress.advance.assert_called_once_with("Fetching documents", amount=1)
        progress.finish_phase.assert_called_once_with("Fetching documents")

    def test_handles_single_dict_converter_output(self) -> None:
        """Some converters return a single dict, not a list."""
        doc = _make_converted_doc(doc_id="x", num_chunks=1)

        reader = MagicMock()
        reader.read_all_documents.return_value = iter(["raw"])
        converter = MagicMock()
        converter.convert.return_value = doc  # Single dict, not list

        nodes = connector_to_nodes(reader, converter, "col")
        assert len(nodes) == 1
        assert nodes[0].id_ == "x__chunk_0"
