"""End-to-end system tests for the parsing + indexing pipeline.

These tests exercise the full path from raw files → ParsingModule → ParsedDocument,
and from raw files → FileSystemConnector → v1 dicts, using real project files
(docs, specs, code, image) as test data.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from connectors.files.connector import FileSystemConnector
from connectors.files.v1_adapter import V1FormatAdapter
from parsing import ParsingModule
from parsing.schema import ParsedDocument

# Root of the indexed project (two levels up from tests/system/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def parsing_module() -> ParsingModule:
    """Shared ParsingModule — expensive to create (lazy Docling init)."""
    return ParsingModule(ocr=False, table_structure=False, max_tokens=512)


@pytest.fixture(scope="module")
def spec_dir() -> Path:
    """Real .spec/ directory from the project."""
    d = PROJECT_ROOT / ".spec"
    assert d.is_dir(), f"{d} does not exist"
    return d


@pytest.fixture(scope="module")
def docs_dir() -> Path:
    """Real docs/ directory from the project."""
    d = PROJECT_ROOT / "docs"
    assert d.is_dir(), f"{d} does not exist"
    return d


@pytest.fixture(scope="module")
def logo_png() -> Path:
    """Real PNG image from the project."""
    p = PROJECT_ROOT / "docs" / "img" / "logo.png"
    assert p.is_file(), f"{p} does not exist"
    return p


# ---------------------------------------------------------------------------
# E2E: ParsingModule on real files
# ---------------------------------------------------------------------------


class TestParsingModuleE2E:
    """Exercise ParsingModule.parse() on real project files."""

    def test_parse_spec_markdown(self, parsing_module: ParsingModule, spec_dir: Path):
        """Parse a real .spec/ markdown file with headings and structure."""
        target = spec_dir / "tech.md"
        assert target.exists()

        doc = parsing_module.parse(target)
        assert isinstance(doc, ParsedDocument)
        assert len(doc.chunks) > 0
        assert doc.metadata["format"] == ".md"
        # Verify we got meaningful content
        all_text = " ".join(ch.text for ch in doc.chunks)
        assert len(all_text) > 100

    def test_parse_readme_markdown(self, parsing_module: ParsingModule):
        """Parse the project README."""
        readme = PROJECT_ROOT / "README.md"
        assert readme.exists()

        doc = parsing_module.parse(readme)
        assert len(doc.chunks) > 0
        # README should mention "indexed"
        all_text = " ".join(ch.text for ch in doc.chunks).lower()
        assert "indexed" in all_text

    def test_parse_python_source(self, parsing_module: ParsingModule):
        """Parse a real Python source file from the project."""
        target = (
            PROJECT_ROOT
            / "packages"
            / "indexed-parsing"
            / "src"
            / "parsing"
            / "code_chunker.py"
        )
        assert target.exists()

        doc = parsing_module.parse(target)
        assert len(doc.chunks) > 0
        assert all(ch.source_type == "code" for ch in doc.chunks)
        # Should detect Python semantic nodes
        languages = {ch.metadata.get("language") for ch in doc.chunks}
        assert "python" in languages

    def test_parse_json_config(self, parsing_module: ParsingModule, tmp_path: Path):
        """Parse a JSON file."""
        f = tmp_path / "config.json"
        f.write_text('{"key": "value", "nested": {"a": 1, "b": 2}}')

        doc = parsing_module.parse(f)
        assert len(doc.chunks) > 0
        assert doc.metadata["format"] == ".json"

    def test_parse_png_image(self, parsing_module: ParsingModule, logo_png: Path):
        """Parse a real PNG image — routes to Docling/fallback."""
        doc = parsing_module.parse(logo_png)
        assert isinstance(doc, ParsedDocument)
        assert doc.metadata["format"] == ".png"
        # Image may or may not produce chunks depending on OCR
        # but should not crash


# ---------------------------------------------------------------------------
# E2E: FileSystemConnector on real directory
# ---------------------------------------------------------------------------


class TestFileSystemConnectorE2E:
    """Exercise the full connector pipeline on real project directories."""

    def test_connector_reads_spec_directory(self, spec_dir: Path):
        """Full pipeline: connector reads .spec/ and produces v1 docs."""
        connector = FileSystemConnector(
            path=str(spec_dir),
            include_patterns=[r".*\.md$"],
        )

        # Read via v1 compat path
        docs = list(connector.reader.read_all_documents())
        assert len(docs) >= 5  # .spec has 6 md files

        for doc in docs:
            assert "fileRelativePath" in doc
            assert "fileFullPath" in doc
            assert "modifiedTime" in doc
            assert "content" in doc
            assert len(doc["content"]) > 0

    def test_connector_reads_and_converts_spec(self, spec_dir: Path):
        """Full pipeline through converter: reader → converter → v1 indexed docs."""
        connector = FileSystemConnector(
            path=str(spec_dir),
            include_patterns=[r".*\.md$"],
        )

        reader_docs = list(connector.reader.read_all_documents())
        assert len(reader_docs) > 0

        converted = []
        for doc in reader_docs:
            result = connector.converter.convert(doc)
            converted.extend(result)

        assert len(converted) >= 5
        for doc in converted:
            assert "id" in doc
            assert "url" in doc
            assert doc["url"].startswith("file://")
            assert "chunks" in doc
            assert len(doc["chunks"]) >= 2  # file path chunk + at least 1 content chunk
            assert doc["chunks"][0]["indexedData"] == doc["id"]

    def test_connector_native_parsed_output(self, spec_dir: Path):
        """Full pipeline: reader → ParsedDocument (native, no v1 adapter)."""
        connector = FileSystemConnector(
            path=str(spec_dir),
            include_patterns=[r".*\.md$"],
        )

        parsed_docs = list(connector.reader.read_all_parsed())
        assert len(parsed_docs) >= 5

        for doc in parsed_docs:
            assert isinstance(doc, ParsedDocument)
            assert len(doc.chunks) > 0
            assert "modified_time" in doc.metadata

    def test_connector_mixed_content_directory(self, tmp_path: Path):
        """Mixed directory with markdown, code, json, and binary."""
        (tmp_path / "readme.md").write_text("# Hello\n\nWorld")
        (tmp_path / "app.py").write_text("def main():\n    print('hello')\n")
        (tmp_path / "config.json").write_text('{"key": "val"}')
        (tmp_path / "binary.exe").write_bytes(b"\x00\x01\x02\x03")

        connector = FileSystemConnector(path=str(tmp_path))
        parsed = list(connector.reader.read_all_parsed())

        # binary.exe should be excluded by default
        file_names = {Path(d.file_path).name for d in parsed}
        assert "readme.md" in file_names
        assert "app.py" in file_names
        assert "config.json" in file_names
        assert "binary.exe" not in file_names

    def test_connector_with_v1_adapter_roundtrip(self, spec_dir: Path):
        """Verify V1FormatAdapter produces valid v1 dicts from ParsedDocuments."""
        connector = FileSystemConnector(
            path=str(spec_dir),
            include_patterns=[r".*\.md$"],
        )

        for parsed in connector.reader.read_all_parsed():
            # Test reader output format
            reader_out = V1FormatAdapter.reader_output(parsed, str(spec_dir))
            assert "fileRelativePath" in reader_out
            assert not os.path.isabs(reader_out["fileRelativePath"])

            # Test converter output format
            conv_out = V1FormatAdapter.converter_output(parsed, str(spec_dir))
            assert len(conv_out) == 1
            entry = conv_out[0]
            assert entry["id"] == reader_out["fileRelativePath"]

            # Verify converter can process the reader output
            converted = connector.converter.convert(reader_out)
            assert len(converted) == 1
            assert converted[0]["id"] == reader_out["fileRelativePath"]
            break  # one file is enough for the roundtrip test


# ---------------------------------------------------------------------------
# E2E: Change tracking on real data
# ---------------------------------------------------------------------------


class TestChangeTrackingE2E:
    """Exercise change tracking with real file operations."""

    def test_full_change_tracking_lifecycle(self, tmp_path: Path):
        """Create files → index → modify → detect changes → re-index."""
        # Setup initial files
        (tmp_path / "doc1.md").write_text("# Document One\n\nOriginal content.")
        (tmp_path / "doc2.md").write_text("# Document Two\n\nOriginal content.")
        (tmp_path / "app.py").write_text("def hello():\n    return 'world'\n")

        connector = FileSystemConnector(
            path=str(tmp_path),
            change_tracking="content_hash",
        )

        # First run — everything is new
        changes = connector.get_changes()
        assert len(changes) == 3
        assert all(ch.status == "added" for ch in changes)

        # Save state
        connector.save_state(str(tmp_path / ".indexed"))
        state = connector.load_state(str(tmp_path / ".indexed"))
        assert state is not None
        assert state.indexed_file_count == 3

        # Modify one file, add one, delete one
        (tmp_path / "doc1.md").write_text("# Document One\n\nModified content!")
        (tmp_path / "doc3.md").write_text("# Document Three\n\nNew file.")
        (tmp_path / "doc2.md").unlink()

        # Detect changes
        changes = connector.get_changes(state)
        statuses = {ch.path: ch.status for ch in changes}
        assert statuses.get("doc1.md") == "modified"
        assert statuses.get("doc3.md") == "added"
        assert statuses.get("doc2.md") == "deleted"

        # Get files to process
        to_process = connector.get_files_to_process(state)
        process_names = {p.name for p in to_process}
        assert "doc1.md" in process_names
        assert "doc3.md" in process_names
        assert "doc2.md" not in process_names

        # Get deletions
        deletions = connector.get_deletions(state)
        assert "doc2.md" in deletions

    def test_state_persistence_roundtrip(self, tmp_path: Path):
        """Verify state saves and loads correctly."""
        (tmp_path / "test.txt").write_text("content")

        connector = FileSystemConnector(
            path=str(tmp_path),
            change_tracking="content_hash",
        )
        connector.save_state(str(tmp_path / ".indexed"))

        state = connector.load_state(str(tmp_path / ".indexed"))
        assert state is not None
        assert state.indexed_file_count == 1
        assert state.file_hashes is not None
        assert len(state.file_hashes) == 1
        assert state.last_indexed_at is not None

    def test_no_state_returns_none(self, tmp_path: Path):
        """Loading from empty dir returns None."""
        connector = FileSystemConnector(
            path=str(tmp_path),
            change_tracking="none",
        )
        assert connector.load_state(str(tmp_path / ".indexed")) is None
