"""Jira Cloud document converter (deprecated - use UnifiedJiraDocumentConverter instead).

This module is maintained for backward compatibility but delegates all functionality
to the unified converter implementation.
"""

import warnings

from .unified_jira_document_converter import UnifiedJiraDocumentConverter


class JiraCloudDocumentConverter:
    """Jira Cloud document converter (DEPRECATED).

    This class is deprecated and maintained only for backward compatibility.
    New code should use UnifiedJiraDocumentConverter.
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        warnings.warn(
            "JiraCloudDocumentConverter is deprecated. "
            "Use UnifiedJiraDocumentConverter instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._converter = UnifiedJiraDocumentConverter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

    def convert(self, document: dict) -> list:
        return self._converter.convert(document)
