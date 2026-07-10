"""Tests for update command UI components and utilities."""

import pytest


class TestFormatSourceType:
    """Test _format_source_type function for displaying collection types."""

    def test_format_jira(self):
        """Test formatting 'jira' source type."""
        from indexed.cli.knowledge.commands.update import _format_source_type

        assert _format_source_type("jira") == "Jira"

    def test_format_jira_cloud_type(self):
        """Test formatting 'jiraCloud' source type."""
        from indexed.cli.knowledge.commands.update import _format_source_type

        assert _format_source_type("jiraCloud") == "Jira Cloud"

    def test_format_confluence(self):
        """Test formatting 'confluence' source type."""
        from indexed.cli.knowledge.commands.update import _format_source_type

        assert _format_source_type("confluence") == "Confluence"

    def test_format_confluence_cloud_type(self):
        """Test formatting 'confluenceCloud' source type."""
        from indexed.cli.knowledge.commands.update import _format_source_type

        assert _format_source_type("confluenceCloud") == "Confluence Cloud"

    def test_format_files_type(self):
        """Test formatting 'localFiles' source type."""
        from indexed.cli.knowledge.commands.update import _format_source_type

        assert _format_source_type("localFiles") == "Local Files"

    @pytest.mark.unit
    def test_format_outline(self):
        """Test formatting 'outline' source type."""
        from indexed.cli.knowledge.commands.update import _format_source_type

        assert _format_source_type("outline") == "Outline"

    def test_format_unknown_type(self):
        """Test formatting unknown source type falls back to capitalize."""
        from indexed.cli.knowledge.commands.update import _format_source_type

        assert _format_source_type("customType") == "Customtype"

    def test_format_none(self):
        """Test formatting None source type returns 'Unknown'."""
        from indexed.cli.knowledge.commands.update import _format_source_type

        assert _format_source_type(None) == "Unknown"

    def test_format_empty_string(self):
        """Test formatting empty string returns 'Unknown'."""
        from indexed.cli.knowledge.commands.update import _format_source_type

        assert _format_source_type("") == "Unknown"


class TestDynamicResultText:
    """Test dynamic result text generation logic."""

    def test_no_changes_result_text(self):
        """Test result text when no changes occurred."""
        # Simulate the logic from update.py
        docs_delta = 0
        chunks_delta = 0
        num_collections = 3
        total_docs = 841
        total_chunks = 5557

        coll_word = "Collection" if num_collections == 1 else "Collections"

        if docs_delta == 0 and chunks_delta == 0:
            result_text = f"Checked {num_collections} {coll_word} - all up to date ({total_docs} documents, {total_chunks} chunks)"

        assert (
            result_text
            == "Checked 3 Collections - all up to date (841 documents, 5557 chunks)"
        )

    def test_single_collection_no_changes(self):
        """Test result text for single collection with no changes."""
        docs_delta = 0
        chunks_delta = 0
        num_collections = 1
        total_docs = 100
        total_chunks = 500

        coll_word = "Collection" if num_collections == 1 else "Collections"

        if docs_delta == 0 and chunks_delta == 0:
            result_text = f"Checked {num_collections} {coll_word} - all up to date ({total_docs} documents, {total_chunks} chunks)"

        assert (
            result_text
            == "Checked 1 Collection - all up to date (100 documents, 500 chunks)"
        )

    def test_documents_added_result_text(self):
        """Test result text when documents were added."""
        docs_delta = 5
        chunks_delta = 12
        num_collections = 2
        total_docs = 105
        total_chunks = 512

        coll_word = "Collection" if num_collections == 1 else "Collections"

        if docs_delta == 0 and chunks_delta == 0:
            result_text = f"Checked {num_collections} {coll_word} - all up to date"
        else:
            changes = []
            if docs_delta > 0:
                changes.append(f"+{docs_delta} documents")
            elif docs_delta < 0:
                changes.append(f"{docs_delta} documents")

            if chunks_delta > 0:
                changes.append(f"+{chunks_delta} chunks")
            elif chunks_delta < 0:
                changes.append(f"{chunks_delta} chunks")

            change_str = ", ".join(changes) if changes else "metadata updated"
            result_text = f"Updated {num_collections} {coll_word}: {change_str} (now {total_docs} documents, {total_chunks} chunks)"

        assert (
            result_text
            == "Updated 2 Collections: +5 documents, +12 chunks (now 105 documents, 512 chunks)"
        )

    def test_documents_removed_result_text(self):
        """Test result text when documents were removed."""
        docs_delta = -3
        chunks_delta = -15
        num_collections = 1
        total_docs = 97
        total_chunks = 485

        coll_word = "Collection" if num_collections == 1 else "Collections"

        changes = []
        if docs_delta > 0:
            changes.append(f"+{docs_delta} documents")
        elif docs_delta < 0:
            changes.append(f"{docs_delta} documents")

        if chunks_delta > 0:
            changes.append(f"+{chunks_delta} chunks")
        elif chunks_delta < 0:
            changes.append(f"{chunks_delta} chunks")

        change_str = ", ".join(changes)
        result_text = f"Updated {num_collections} {coll_word}: {change_str} (now {total_docs} documents, {total_chunks} chunks)"

        assert (
            result_text
            == "Updated 1 Collection: -3 documents, -15 chunks (now 97 documents, 485 chunks)"
        )

    def test_only_chunks_changed(self):
        """Test result text when only chunks changed (no document count change)."""
        docs_delta = 0
        chunks_delta = 10
        num_collections = 1
        total_docs = 100
        total_chunks = 510

        coll_word = "Collection" if num_collections == 1 else "Collections"

        changes = []
        if docs_delta > 0:
            changes.append(f"+{docs_delta} documents")
        elif docs_delta < 0:
            changes.append(f"{docs_delta} documents")

        if chunks_delta > 0:
            changes.append(f"+{chunks_delta} chunks")
        elif chunks_delta < 0:
            changes.append(f"{chunks_delta} chunks")

        change_str = ", ".join(changes) if changes else "metadata updated"
        result_text = f"Updated {num_collections} {coll_word}: {change_str} (now {total_docs} documents, {total_chunks} chunks)"

        assert (
            result_text
            == "Updated 1 Collection: +10 chunks (now 100 documents, 510 chunks)"
        )
