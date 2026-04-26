"""Tests for the upgraded FilesDocumentReader."""

from connectors.files.files_document_reader import FilesDocumentReader


class TestFilesDocumentReaderParsed:
    def test_read_all_parsed_yields_documents(self, tmp_path):
        (tmp_path / "hello.txt").write_text("Hello world")
        (tmp_path / "data.json").write_text('{"key": "value"}')

        reader = FilesDocumentReader(base_path=str(tmp_path))
        docs = list(reader.read_all_parsed())
        assert len(docs) == 2

    def test_read_all_parsed_empty_dir(self, tmp_path):
        reader = FilesDocumentReader(base_path=str(tmp_path))
        docs = list(reader.read_all_parsed())
        assert docs == []

    def test_read_all_parsed_nested_dirs(self, tmp_path):
        sub = tmp_path / "sub" / "deep"
        sub.mkdir(parents=True)
        (sub / "nested.txt").write_text("nested content")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        docs = list(reader.read_all_parsed())
        assert len(docs) == 1
        assert "modified_time" in docs[0].metadata

    def test_include_patterns(self, tmp_path):
        (tmp_path / "keep.txt").write_text("keep")
        (tmp_path / "skip.py").write_text("skip")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            include_patterns=[r".*\.txt$"],
        )
        docs = list(reader.read_all_parsed())
        assert len(docs) == 1
        assert "keep.txt" in docs[0].file_path

    def test_negation_pattern_excludes_file(self, tmp_path):
        (tmp_path / "keep.txt").write_text("keep")
        (tmp_path / "skip.txt").write_text("skip")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            include_patterns=["*", "!skip.txt"],
        )
        paths = list(reader._iter_file_paths())
        assert len(paths) == 1
        assert "keep.txt" in paths[0]

    def test_negation_pattern_excludes_by_extension(self, tmp_path):
        (tmp_path / "doc.txt").write_text("doc")
        (tmp_path / "binary.exe").write_bytes(b"\x00\x01\x02")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            include_patterns=["*", "!*.exe"],
        )
        paths = list(reader._iter_file_paths())
        assert len(paths) == 1
        assert "doc.txt" in paths[0]

    def test_negation_no_positive_pattern_yields_nothing(self, tmp_path):
        (tmp_path / "doc.txt").write_text("doc")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            include_patterns=["!*.txt"],
        )
        assert list(reader._iter_file_paths()) == []

    def test_multiple_negation_patterns(self, tmp_path):
        (tmp_path / "keep.py").write_text("keep")
        (tmp_path / "skip.exe").write_bytes(b"\x00")
        (tmp_path / "skip.bin").write_bytes(b"\x00")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            include_patterns=["*", "!*.exe", "!*.bin"],
        )
        paths = list(reader._iter_file_paths())
        assert len(paths) == 1
        assert "keep.py" in paths[0]

    def test_exe_included_by_default(self, tmp_path):
        (tmp_path / "doc.txt").write_text("doc")
        (tmp_path / "binary.exe").write_bytes(b"\x00\x01\x02")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        paths = list(reader._iter_file_paths())
        # No default extension blocklist — both files are included
        assert len(paths) == 2

    def test_fail_fast(self, tmp_path):
        (tmp_path / "good.txt").write_text("good")
        reader = FilesDocumentReader(base_path=str(tmp_path), fail_fast=True)
        docs = list(reader.read_all_parsed())
        assert len(docs) == 1


class TestFilesDocumentReaderErrorSummary:
    def test_error_summary_only_lists_truly_unparseable(self, tmp_path):
        """Parseable files should not appear in error stats."""
        (tmp_path / "readme.md").write_text("# Hello")
        (tmp_path / "styles.css").write_text("body { color: red; }")
        (tmp_path / ".gitignore").write_text("node_modules/")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        docs = list(reader.read_all_parsed())

        assert len(docs) == 3
        assert all(doc.metadata.get("error") is not True for doc in docs)

    def test_mixed_parseable_and_empty_files(self, tmp_path):
        """Empty files should not be flagged as errors."""
        (tmp_path / "content.txt").write_text("some content")
        (tmp_path / ".hotreload").write_text("")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        docs = list(reader.read_all_parsed())

        assert len(docs) == 2
        error_docs = [d for d in docs if d.metadata.get("error")]
        assert len(error_docs) == 0


class TestFilesDocumentReaderV1Compat:
    def test_read_all_documents_backward_compat(self, tmp_path):
        (tmp_path / "test.txt").write_text("Hello v1 world")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        docs = list(reader.read_all_documents())
        assert len(docs) == 1
        doc = docs[0]
        assert "fileRelativePath" in doc
        assert "fileFullPath" in doc
        assert "modifiedTime" in doc
        assert "content" in doc
        assert isinstance(doc["content"], list)

    def test_get_number_of_documents(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        assert reader.get_number_of_documents() == 2

    def test_get_reader_details(self, tmp_path):
        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            include_patterns=[r".*\.md$"],
        )
        details = reader.get_reader_details()
        assert details["type"] == "localFiles"
        assert details["basePath"] == str(tmp_path)
        assert "excludedDirs" in details
        assert "excludedExtensions" not in details

    def test_get_reader_details_includes_negation_patterns(self, tmp_path):
        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            include_patterns=["*", "!*.log"],
        )
        details = reader.get_reader_details()
        assert "!*.log" in details["includePatterns"]


class TestFilesDocumentReaderSpecificFiles:
    def test_specific_files_limits_iteration(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        c = tmp_path / "c.txt"
        a.write_text("aaa")
        b.write_text("bbb")
        c.write_text("ccc")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            specific_files=[str(a), str(b)],
        )
        found = list(reader._iter_file_paths())
        assert set(found) == {str(a), str(b)}
        assert str(c) not in found

    def test_specific_files_empty_yields_nothing(self, tmp_path):
        (tmp_path / "a.txt").write_text("aaa")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            specific_files=[],
        )
        assert list(reader._iter_file_paths()) == []

    def test_specific_files_get_number_of_documents(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("a")
        b.write_text("b")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            specific_files=[str(a), str(b)],
        )
        assert reader.get_number_of_documents() == 2

    def test_specific_files_missing_file_skipped(self, tmp_path):
        a = tmp_path / "a.txt"
        a.write_text("aaa")
        missing = str(tmp_path / "does_not_exist.txt")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            specific_files=[str(a), missing],
        )
        found = list(reader._iter_file_paths())
        assert found == [str(a)]

    def test_none_specific_files_walks_directory(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("a")
        b.write_text("b")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            specific_files=None,
        )
        assert reader.get_number_of_documents() == 2

    def test_specific_files_negation_pattern_applied(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "skip.txt"
        a.write_text("aaa")
        b.write_text("bbb")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            specific_files=[str(a), str(b)],
            include_patterns=["*", "!skip.txt"],
        )
        found = list(reader._iter_file_paths())
        assert found == [str(a)]


class TestFilesDocumentReaderStartFromTime:
    def test_start_from_time_filters_old_files(self, tmp_path):
        import datetime
        import time

        old = tmp_path / "old.txt"
        old.write_text("old content")

        # Wait briefly then create new file
        time.sleep(0.05)
        cutoff = datetime.datetime.now()
        time.sleep(0.05)

        new = tmp_path / "new.txt"
        new.write_text("new content")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            start_from_time=cutoff,
        )
        found = list(reader._iter_file_paths())
        assert len(found) == 1
        assert "new.txt" in found[0]


class TestFilesDocumentReaderGlobFallback:
    def test_glob_pattern_compiled(self, tmp_path):
        """Patterns that aren't valid regex should fall back to glob."""
        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            include_patterns=["*.txt"],
        )
        # The pattern should be compiled (glob fallback)
        assert len(reader.compiled_include_patterns) == 1

    def test_regex_pattern_compiled(self, tmp_path):
        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            include_patterns=[r".*\.txt$"],
        )
        assert len(reader.compiled_include_patterns) == 1

    def test_negation_glob_pattern_compiled(self, tmp_path):
        """Negation glob patterns should compile via fallback too."""
        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            include_patterns=["*", "!*.pyc"],
        )
        assert len(reader.compiled_include_patterns) == 1
        assert len(reader._compiled_exclude_patterns) == 1
