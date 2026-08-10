"""Tests for Jira document converters."""

from unittest.mock import MagicMock

import pytest

from indexed.connectors.jira.unified_jira_document_converter import (
    UnifiedJiraDocumentConverter,
)

pytestmark = pytest.mark.connectors  # Mark all tests in this file as connector tests


class TestUnifiedJiraDocumentConverter:
    """Test UnifiedJiraDocumentConverter which handles both Cloud and Server formats."""

    def setup_method(self):
        self.converter = UnifiedJiraDocumentConverter()

    def test_simple_issue_conversion(self):
        document = {
            "key": "TEST-123",
            "self": "https://company.atlassian.net/rest/api/2/issue/123456",
            "fields": {
                "summary": "Simple test issue",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "This is a simple description"}
                            ],
                        }
                    ],
                },
                "comment": {"comments": []},
            },
        }

        result = self.converter.convert(document)

        assert len(result) == 1
        doc = result[0]
        assert doc["id"] == "TEST-123"
        assert doc["url"] == "https://company.atlassian.net/browse/TEST-123"
        assert doc["modifiedTime"] == "2024-01-01T12:00:00.000+0000"
        assert "TEST-123 : Simple test issue" in doc["text"]
        assert "This is a simple description" in doc["text"]

        # Verify chunks
        chunks = doc["chunks"]
        assert len(chunks) >= 1
        assert chunks[0]["indexedData"] == "TEST-123 : Simple test issue"

    def test_adf_paragraph_parsing(self):
        """Test ADF paragraph parsing through convert method."""
        document = {
            "key": "TEST-1",
            "self": "https://company.atlassian.net/rest/api/2/issue/1",
            "fields": {
                "summary": "Test",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "First paragraph"}],
                        },
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Second paragraph"}],
                        },
                    ],
                },
                "comment": {"comments": []},
            },
        }

        result = self.converter.convert(document)
        text = result[0]["text"]
        assert "First paragraph" in text
        assert "Second paragraph" in text

    def test_adf_heading_parsing(self):
        """Test ADF heading parsing through convert method."""
        document = {
            "key": "TEST-1",
            "self": "https://company.atlassian.net/rest/api/2/issue/1",
            "fields": {
                "summary": "Test",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "heading",
                            "attrs": {"level": 1},
                            "content": [{"type": "text", "text": "Main Heading"}],
                        },
                        {
                            "type": "heading",
                            "attrs": {"level": 3},
                            "content": [{"type": "text", "text": "Sub Heading"}],
                        },
                    ],
                },
                "comment": {"comments": []},
            },
        }

        result = self.converter.convert(document)
        text = result[0]["text"]
        assert "# Main Heading" in text
        assert "### Sub Heading" in text

    def test_adf_list_parsing(self):
        """Test ADF list parsing through convert method."""
        document = {
            "key": "TEST-1",
            "self": "https://company.atlassian.net/rest/api/2/issue/1",
            "fields": {
                "summary": "Test",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "bulletList",
                            "content": [
                                {
                                    "type": "listItem",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {"type": "text", "text": "First item"}
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "type": "listItem",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {"type": "text", "text": "Second item"}
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                },
                "comment": {"comments": []},
            },
        }

        result = self.converter.convert(document)
        text = result[0]["text"]
        assert "- First item" in text
        assert "- Second item" in text

    def test_adf_text_marks(self):
        """Test ADF text marks parsing through convert method."""
        document = {
            "key": "TEST-1",
            "self": "https://company.atlassian.net/rest/api/2/issue/1",
            "fields": {
                "summary": "Test",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Bold text",
                                    "marks": [{"type": "strong"}],
                                },
                                {"type": "text", "text": " and "},
                                {
                                    "type": "text",
                                    "text": "italic text",
                                    "marks": [{"type": "em"}],
                                },
                                {"type": "text", "text": " and "},
                                {
                                    "type": "text",
                                    "text": "code",
                                    "marks": [{"type": "code"}],
                                },
                            ],
                        }
                    ],
                },
                "comment": {"comments": []},
            },
        }

        result = self.converter.convert(document)
        text = result[0]["text"]
        assert "**Bold text**" in text
        assert "*italic text*" in text
        assert "`code`" in text

    def test_adf_code_block(self):
        """Test ADF code block parsing through convert method."""
        document = {
            "key": "TEST-1",
            "self": "https://company.atlassian.net/rest/api/2/issue/1",
            "fields": {
                "summary": "Test",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "codeBlock",
                            "content": [
                                {"type": "text", "text": "console.log('Hello World');"}
                            ],
                        }
                    ],
                },
                "comment": {"comments": []},
            },
        }

        result = self.converter.convert(document)
        text = result[0]["text"]
        assert "```\nconsole.log('Hello World');\n```" in text

    def test_complex_adf_structure(self):
        """Test complex ADF structure conversion."""
        document = {
            "key": "BUG-1",
            "self": "https://company.atlassian.net/rest/api/2/issue/1",
            "fields": {
                "summary": "Bug Report",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "heading",
                            "attrs": {"level": 2},
                            "content": [{"type": "text", "text": "Bug Report"}],
                        },
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "The following issue occurs when ",
                                },
                                {
                                    "type": "text",
                                    "text": "authentication fails",
                                    "marks": [{"type": "strong"}],
                                },
                                {"type": "text", "text": ":"},
                            ],
                        },
                        {
                            "type": "bulletList",
                            "content": [
                                {
                                    "type": "listItem",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {
                                                    "type": "text",
                                                    "text": "User gets redirected",
                                                }
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "type": "listItem",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {
                                                    "type": "text",
                                                    "text": "Session is cleared",
                                                }
                                            ],
                                        }
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "codeBlock",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "if (auth.failed) {\n  redirect('/login');\n}",
                                }
                            ],
                        },
                    ],
                },
                "comment": {"comments": []},
            },
        }

        result = self.converter.convert(document)
        text = result[0]["text"]

        # Verify structure is preserved
        assert "## Bug Report" in text
        assert "The following issue occurs when **authentication fails**:" in text
        assert "- User gets redirected" in text
        assert "- Session is cleared" in text
        assert "```\nif (auth.failed) {\n  redirect('/login');\n}\n```" in text

    def test_issue_with_comments(self):
        document = {
            "key": "PROJ-456",
            "self": "https://company.atlassian.net/rest/api/2/issue/456789",
            "fields": {
                "summary": "Issue with comments",
                "updated": "2024-01-02T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Main description"}],
                        }
                    ],
                },
                "comment": {
                    "comments": [
                        {
                            "body": {
                                "type": "doc",
                                "version": 1,
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {"type": "text", "text": "First comment"}
                                        ],
                                    }
                                ],
                            }
                        },
                        {
                            "body": {
                                "type": "doc",
                                "version": 1,
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {"type": "text", "text": "Second comment"}
                                        ],
                                    }
                                ],
                            }
                        },
                    ]
                },
            },
        }

        result = self.converter.convert(document)
        doc = result[0]

        # Verify all content is included
        assert "Main description" in doc["text"]
        assert "First comment" in doc["text"]
        assert "Second comment" in doc["text"]

    def test_empty_or_missing_fields(self):
        document = {
            "key": "EMPTY-1",
            "self": "https://company.atlassian.net/rest/api/2/issue/1",
            "fields": {
                "summary": "Empty issue",
                "updated": "2024-01-03T12:00:00.000+0000",
                "description": None,
                "comment": {"comments": []},
            },
        }

        result = self.converter.convert(document)
        doc = result[0]

        assert doc["id"] == "EMPTY-1"
        assert "Empty issue" in doc["text"]
        # Should not crash on empty/null description

    def test_server_plain_text_description(self):
        """Test Jira Server format with plain text description."""
        document = {
            "key": "SRV-1",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "fields": {
                "summary": "Server issue",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": "This is a plain text description from Jira Server",
                "comment": {"comments": []},
            },
        }

        result = self.converter.convert(document)
        doc = result[0]

        assert doc["id"] == "SRV-1"
        assert "This is a plain text description from Jira Server" in doc["text"]

    def test_server_plain_text_comments(self):
        """Test Jira Server format with plain text comments."""
        document = {
            "key": "SRV-2",
            "self": "https://jira.example.com/rest/api/2/issue/2",
            "fields": {
                "summary": "Server issue with comments",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": "Description",
                "comment": {
                    "comments": [
                        {"body": "Plain text comment 1"},
                        {"body": "Plain text comment 2"},
                    ]
                },
            },
        }

        result = self.converter.convert(document)
        doc = result[0]

        assert "Plain text comment 1" in doc["text"]
        assert "Plain text comment 2" in doc["text"]

    def test_attachment_parsing_with_mock(self):
        """Test attachment bytes are parsed via ParsingModule."""
        mock_parsed_att = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.contextualized_text = "Attachment content"
        mock_chunk.metadata = {"page": 1}
        mock_parsed_att.chunks = [mock_chunk]

        mock_parsed_text = MagicMock()
        mock_text_chunk = MagicMock()
        mock_text_chunk.contextualized_text = "Description text"
        mock_text_chunk.metadata = {}
        mock_parsed_text.chunks = [mock_text_chunk]

        converter = UnifiedJiraDocumentConverter(include_attachments=True)
        mock_parser = MagicMock()
        mock_parser.parse_bytes.side_effect = lambda data, filename: (
            mock_parsed_att if filename == "doc.pdf" else mock_parsed_text
        )
        converter._parsing = mock_parser

        document = {
            "key": "ATT-1",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "fields": {
                "summary": "With attachment",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": "Some description",
                "comment": {"comments": []},
            },
            "attachments": [
                {
                    "filename": "doc.pdf",
                    "bytes": b"pdf data",
                    "mimeType": "application/pdf",
                },
            ],
        }

        result = converter.convert(document)
        chunks = result[0]["chunks"]
        att_chunks = [c for c in chunks if c.get("metadata", {}).get("attachment")]
        assert len(att_chunks) == 1
        assert att_chunks[0]["indexedData"] == "Attachment content"
        assert att_chunks[0]["metadata"]["attachment"] == "doc.pdf"

    def test_attachment_skipped_when_disabled(self):
        """Attachments ignored when include_attachments=False."""
        converter = UnifiedJiraDocumentConverter(include_attachments=False)
        document = {
            "key": "ATT-2",
            "self": "https://jira.example.com/rest/api/2/issue/2",
            "fields": {
                "summary": "No attachments",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": None,
                "comment": {"comments": []},
            },
            "attachments": [{"filename": "ignored.pdf", "bytes": b"data"}],
        }
        result = converter.convert(document)
        chunks = result[0]["chunks"]
        att_chunks = [c for c in chunks if c.get("metadata", {}).get("attachment")]
        assert len(att_chunks) == 0

    def test_attachment_parse_error_handled(self):
        """Failed attachment parse logs warning and continues."""
        converter = UnifiedJiraDocumentConverter(include_attachments=True)
        mock_parser = MagicMock()
        mock_text = MagicMock()
        mock_text.chunks = []

        def side_effect(data, filename):
            if filename == "bad.bin":
                raise RuntimeError("bad file")
            return mock_text

        mock_parser.parse_bytes.side_effect = side_effect
        converter._parsing = mock_parser

        document = {
            "key": "ATT-3",
            "self": "https://jira.example.com/rest/api/2/issue/3",
            "fields": {
                "summary": "Bad attachment",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": None,
                "comment": {"comments": []},
            },
            "attachments": [{"filename": "bad.bin", "bytes": b"\x00"}],
        }
        result = converter.convert(document)
        assert len(result) == 1

    def test_attachment_without_bytes_skipped(self):
        """Attachments without bytes key are skipped."""
        converter = UnifiedJiraDocumentConverter(include_attachments=True)
        mock_parser = MagicMock()
        mock_parser.parse_bytes.return_value = MagicMock(chunks=[])
        converter._parsing = mock_parser

        document = {
            "key": "ATT-4",
            "self": "https://jira.example.com/rest/api/2/issue/4",
            "fields": {
                "summary": "No bytes",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": None,
                "comment": {"comments": []},
            },
            "attachments": [{"filename": "empty.pdf"}],
        }
        result = converter.convert(document)
        assert len(result) == 1
        # parse_bytes should not be called for body (no description) or attachment (no bytes)

    def test_chunk_metadata_included(self):
        """Chunks with metadata get metadata field in output."""
        converter = UnifiedJiraDocumentConverter()
        mock_parser = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.contextualized_text = "chunk text"
        mock_chunk.metadata = {"headings": ["Section"]}
        mock_parser.parse_bytes.return_value = MagicMock(chunks=[mock_chunk])
        converter._parsing = mock_parser

        document = {
            "key": "META-1",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "fields": {
                "summary": "Metadata test",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": "some text",
                "comment": {"comments": []},
            },
        }
        result = converter.convert(document)
        body_chunks = result[0]["chunks"][1:]  # skip title chunk
        assert len(body_chunks) == 1
        assert body_chunks[0]["metadata"] == {"headings": ["Section"]}

    def test_comment_with_empty_body_skipped(self):
        """Comments with empty/None body are skipped."""
        converter = UnifiedJiraDocumentConverter()
        document = {
            "key": "CMT-1",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "fields": {
                "summary": "Empty comment",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": None,
                "comment": {"comments": [{"body": None}, {"body": ""}]},
            },
        }
        result = converter.convert(document)
        assert result[0]["id"] == "CMT-1"

    def test_hardbreak_in_adf(self):
        """Test hardBreak ADF node."""
        converter = UnifiedJiraDocumentConverter()
        document = {
            "key": "HB-1",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "fields": {
                "summary": "HardBreak",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "line1"},
                                {"type": "hardBreak"},
                                {"type": "text", "text": "line2"},
                            ],
                        }
                    ],
                },
                "comment": {"comments": []},
            },
        }
        result = converter.convert(document)
        assert "line1" in result[0]["text"]
        assert "line2" in result[0]["text"]

    def test_adf_list_items_separated_by_newline(self):
        """D3: sibling list items must not be run together on one line."""
        document = {
            "key": "LIST-1",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "fields": {
                "summary": "List separator",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "bulletList",
                            "content": [
                                {
                                    "type": "listItem",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {"type": "text", "text": "Alpha"}
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "type": "listItem",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {"type": "text", "text": "Beta"}
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                },
                "comment": {"comments": []},
            },
        }
        result = self.converter.convert(document)
        text = result[0]["text"]
        assert "- Alpha\n" in text and "- Beta" in text, (
            f"list items must be newline-separated: {text!r}"
        )
        assert "Alpha  - Beta" not in text, (
            f"sibling list items must not run together with no separator: {text!r}"
        )

    def test_adf_ordered_list_uses_ordinals(self):
        """orderedList must render "1.", "2.", … — not "-" bullets."""
        document = {
            "key": "LIST-4",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "fields": {
                "summary": "Ordered list",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "orderedList",
                            "content": [
                                {
                                    "type": "listItem",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {"type": "text", "text": "First"}
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "type": "listItem",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {"type": "text", "text": "Second"}
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "type": "listItem",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {"type": "text", "text": "Third"}
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                },
                "comment": {"comments": []},
            },
        }
        result = self.converter.convert(document)
        text = result[0]["text"]
        assert "1. First" in text, f"ordered list must number items: {text!r}"
        assert "2. Second" in text
        assert "3. Third" in text
        assert "- First" not in text, (
            f"orderedList must not fall back to bullet markers: {text!r}"
        )

    def test_adf_nested_list_separated_from_parent_item_text(self):
        """A nested list under a listItem must not run into the parent
        item's own paragraph text with no separator."""
        document = {
            "key": "LIST-5",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "fields": {
                "summary": "Nested list",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "bulletList",
                            "content": [
                                {
                                    "type": "listItem",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {
                                                    "type": "text",
                                                    "text": "Parent item",
                                                }
                                            ],
                                        },
                                        {
                                            "type": "bulletList",
                                            "content": [
                                                {
                                                    "type": "listItem",
                                                    "content": [
                                                        {
                                                            "type": "paragraph",
                                                            "content": [
                                                                {
                                                                    "type": "text",
                                                                    "text": "Child item",
                                                                }
                                                            ],
                                                        }
                                                    ],
                                                }
                                            ],
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                },
                "comment": {"comments": []},
            },
        }
        result = self.converter.convert(document)
        text = result[0]["text"]
        assert "Parent item  -" not in text, (
            f"nested list must not run into parent item text: {text!r}"
        )
        assert "Parent item\n" in text and "- Child item" in text, (
            f"nested list must be newline-separated from parent text: {text!r}"
        )

    def test_adf_mention_and_inline_card_extracted(self):
        """D3: mention display name and inlineCard url must not be dropped."""
        document = {
            "key": "MEN-1",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "fields": {
                "summary": "Mentions",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Assigned to "},
                                {
                                    "type": "mention",
                                    "attrs": {"id": "557058:abc", "text": "@Alice"},
                                },
                                {"type": "text", "text": " see "},
                                {
                                    "type": "inlineCard",
                                    "attrs": {"url": "https://example.com/card"},
                                },
                            ],
                        }
                    ],
                },
                "comment": {"comments": []},
            },
        }
        result = self.converter.convert(document)
        text = result[0]["text"]
        assert "@Alice" in text
        assert "https://example.com/card" in text

    def test_adf_media_emoji_date_status_extracted(self):
        """D3: media/emoji/date/status leaf attrs contribute to the text."""
        document = {
            "key": "LEAF-1",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "fields": {
                "summary": "Leaf nodes",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "media",
                                    "attrs": {
                                        "id": "media-1",
                                        "alt": "screenshot.png",
                                    },
                                },
                                {
                                    "type": "emoji",
                                    "attrs": {
                                        "shortName": ":smile:",
                                        "text": "😀",
                                    },
                                },
                                {
                                    "type": "date",
                                    "attrs": {"timestamp": "1700000000000"},
                                },
                                {
                                    "type": "status",
                                    "attrs": {"text": "In Progress"},
                                },
                            ],
                        }
                    ],
                },
                "comment": {"comments": []},
            },
        }
        result = self.converter.convert(document)
        text = result[0]["text"]
        assert "screenshot.png" in text
        assert "\U0001f600" in text
        assert "1700000000000" in text
        assert "In Progress" in text

    def test_unknown_adf_node_with_content(self):
        """Unknown ADF node types with content are parsed recursively."""
        converter = UnifiedJiraDocumentConverter()
        document = {
            "key": "UNK-1",
            "self": "https://jira.example.com/rest/api/2/issue/1",
            "fields": {
                "summary": "Unknown node",
                "updated": "2024-01-01T12:00:00.000+0000",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "panel",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": "Inside panel"}
                                    ],
                                }
                            ],
                        }
                    ],
                },
                "comment": {"comments": []},
            },
        }
        result = converter.convert(document)
        assert "Inside panel" in result[0]["text"]
