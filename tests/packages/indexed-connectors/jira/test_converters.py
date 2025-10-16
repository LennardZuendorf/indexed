"""Tests for Jira document converters."""
import pytest
from connectors.jira.jira_cloud_document_converter import JiraCloudDocumentConverter

pytestmark = pytest.mark.connectors  # Mark all tests in this file as connector tests


class TestJiraCloudDocumentConverter:
    def setup_method(self):
        self.converter = JiraCloudDocumentConverter()

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
                                {
                                    "type": "text",
                                    "text": "This is a simple description"
                                }
                            ]
                        }
                    ]
                },
                "comment": {"comments": []}
            }
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
        adf_content = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "First paragraph"}
                    ]
                },
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Second paragraph"}
                    ]
                }
            ]
        }

        result = self.converter._JiraCloudDocumentConverter__parse_adf_content(adf_content)
        assert result == "First paragraph\n\nSecond paragraph"

    def test_adf_heading_parsing(self):
        adf_content = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [
                        {"type": "text", "text": "Main Heading"}
                    ]
                },
                {
                    "type": "heading",
                    "attrs": {"level": 3},
                    "content": [
                        {"type": "text", "text": "Sub Heading"}
                    ]
                }
            ]
        }

        result = self.converter._JiraCloudDocumentConverter__parse_adf_content(adf_content)
        assert result == "# Main Heading\n\n### Sub Heading"

    def test_adf_list_parsing(self):
        adf_content = {
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
                                    ]
                                }
                            ]
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": "Second item"}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        result = self.converter._JiraCloudDocumentConverter__parse_adf_content(adf_content)
        assert "- First item" in result
        assert "- Second item" in result

    def test_adf_text_marks(self):
        adf_content = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Bold text",
                            "marks": [{"type": "strong"}]
                        },
                        {"type": "text", "text": " and "},
                        {
                            "type": "text",
                            "text": "italic text",
                            "marks": [{"type": "em"}]
                        },
                        {"type": "text", "text": " and "},
                        {
                            "type": "text",
                            "text": "code",
                            "marks": [{"type": "code"}]
                        }
                    ]
                }
            ]
        }

        result = self.converter._JiraCloudDocumentConverter__parse_adf_content(adf_content)
        assert result == "**Bold text** and *italic text* and `code`"

    def test_adf_code_block(self):
        adf_content = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "codeBlock",
                    "content": [
                        {"type": "text", "text": "console.log('Hello World');"}
                    ]
                }
            ]
        }

        result = self.converter._JiraCloudDocumentConverter__parse_adf_content(adf_content)
        assert result == "```\nconsole.log('Hello World');\n```"

    def test_complex_adf_structure(self):
        adf_content = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Bug Report"}]
                },
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "The following issue occurs when "},
                        {"type": "text", "text": "authentication fails", "marks": [{"type": "strong"}]},
                        {"type": "text", "text": ":"}
                    ]
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "User gets redirected"}]
                                }
                            ]
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Session is cleared"}]
                                }
                            ]
                        }
                    ]
                },
                {
                    "type": "codeBlock",
                    "content": [
                        {"type": "text", "text": "if (auth.failed) {\n  redirect('/login');\n}"}
                    ]
                }
            ]
        }

        result = self.converter._JiraCloudDocumentConverter__parse_adf_content(adf_content)
        
        # Verify structure is preserved
        assert "## Bug Report" in result
        assert "The following issue occurs when **authentication fails**:" in result
        assert "- User gets redirected" in result
        assert "- Session is cleared" in result
        assert "```\nif (auth.failed) {\n  redirect('/login');\n}\n```" in result

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
                            "content": [{"type": "text", "text": "Main description"}]
                        }
                    ]
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
                                        "content": [{"type": "text", "text": "First comment"}]
                                    }
                                ]
                            }
                        },
                        {
                            "body": {
                                "type": "doc",
                                "version": 1,
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "Second comment"}]
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
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
                "comment": {"comments": []}
            }
        }

        result = self.converter.convert(document)
        doc = result[0]
        
        assert doc["id"] == "EMPTY-1"
        assert "Empty issue" in doc["text"]
        # Should not crash on empty/null description

    def test_malformed_adf_content(self):
        # Test various malformed/edge case ADF structures
        malformed_cases = [
            None,  # Null content
            {},    # Empty dict
            {"type": "doc"},  # Missing content
            {"content": []},  # Missing type
            {"type": "doc", "content": None},  # Null content array
        ]

        for adf_content in malformed_cases:
            result = self.converter._JiraCloudDocumentConverter__parse_adf_content(adf_content)
            assert result == ""  # Should return empty string, not crash

    def test_unknown_adf_node_types(self):
        adf_content = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "unknownNodeType",
                    "content": [
                        {"type": "text", "text": "Nested text in unknown node"}
                    ]
                },
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Regular paragraph"}
                    ]
                }
            ]
        }

        result = self.converter._JiraCloudDocumentConverter__parse_adf_content(adf_content)
        
        # Should handle unknown types gracefully by extracting nested content
        assert "Nested text in unknown node" in result
        assert "Regular paragraph" in result