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
        """
        Create a deprecated JiraCloudDocumentConverter that delegates conversion work to UnifiedJiraDocumentConverter.

        This constructor builds an internal UnifiedJiraDocumentConverter with the provided chunking parameters and exposes its text_splitter for compatibility. This class is deprecated — use UnifiedJiraDocumentConverter instead.

        Parameters:
            chunk_size (int): Maximum size of text chunks when splitting document content.
            chunk_overlap (int): Number of characters to overlap between consecutive chunks.
        """
        self._converter = UnifiedJiraDocumentConverter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        # Expose text_splitter for compatibility
        self.text_splitter = self._converter.text_splitter

    def convert(self, document: dict) -> list:
        """
        Convert a Jira Cloud document into the indexed document format used by the connector.

        Parameters:
            document (dict): Jira document payload to convert.

        Returns:
            list: A list of indexed document items representing the converted document.
        """
        return self._converter.convert(document)
