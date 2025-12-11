"""Jira Server/DC document converter (deprecated - use UnifiedJiraDocumentConverter instead).

This module is maintained for backward compatibility but delegates all functionality
to the unified converter implementation.
"""

from .unified_jira_document_converter import UnifiedJiraDocumentConverter


class JiraDocumentConverter:
    """Jira Server/DC document converter (DEPRECATED).

    This class is deprecated and maintained only for backward compatibility.
    New code should use UnifiedJiraDocumentConverter.

    All functionality is delegated to UnifiedJiraDocumentConverter.
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        """
        Create a deprecated JiraDocumentConverter that delegates to UnifiedJiraDocumentConverter.
        
        This constructor initializes an internal UnifiedJiraDocumentConverter and exposes its
        text_splitter attribute for backward compatibility. New code should use
        UnifiedJiraDocumentConverter directly.
        
        Parameters:
            chunk_size (int): Maximum number of characters per chunk when splitting text.
            chunk_overlap (int): Number of characters to overlap between consecutive chunks.
        """
        self._converter = UnifiedJiraDocumentConverter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        # Expose text_splitter for compatibility
        self.text_splitter = self._converter.text_splitter

    def convert(self, document: dict) -> list:
        """
        Convert a Jira document into the indexed document format used by the connector.
        
        Parameters:
            document (dict): Jira document payload to convert.
        
        Returns:
            list: List of indexed document dictionaries ready for indexing.
        """
        return self._converter.convert(document)