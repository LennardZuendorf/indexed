"""Tests for Jira document converters."""

import pytest
from connectors.jira.unified_jira_document_converter import UnifiedJiraDocumentConverter

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
