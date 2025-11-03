"""Jira Cloud document converter (deprecated - use UnifiedJiraDocumentConverter instead).

This module is maintained for backward compatibility but delegates all functionality
to the unified converter implementation.
"""

from .unified_jira_document_converter import UnifiedJiraDocumentConverter


class JiraCloudDocumentConverter:
    """Jira Cloud document converter (DEPRECATED).

    This class is deprecated and maintained only for backward compatibility.
    New code should use UnifiedJiraDocumentConverter.

    All functionality is delegated to UnifiedJiraDocumentConverter.
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        """Initialize converter.

        Note: This class is deprecated. Consider using UnifiedJiraDocumentConverter instead.
        """
        self._converter = UnifiedJiraDocumentConverter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        # Expose text_splitter for compatibility
        self.text_splitter = self._converter.text_splitter

    def convert(self, document: dict) -> list:
        """Convert Jira document to indexed format."""
        return self._converter.convert(document)
