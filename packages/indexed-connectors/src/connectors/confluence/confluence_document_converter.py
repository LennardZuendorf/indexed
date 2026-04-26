"""Confluence Server/DC document converter (deprecated).

Use UnifiedConfluenceDocumentConverter instead. This wrapper is maintained
for backward compatibility only.
"""

import warnings

from .unified_confluence_document_converter import UnifiedConfluenceDocumentConverter


class ConfluenceDocumentConverter:
    """Confluence Server/DC converter (DEPRECATED).

    Delegates to UnifiedConfluenceDocumentConverter(is_cloud=False).
    """

    def __init__(self) -> None:
        warnings.warn(
            "ConfluenceDocumentConverter is deprecated. "
            "Use UnifiedConfluenceDocumentConverter instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._converter = UnifiedConfluenceDocumentConverter(is_cloud=False)

    def convert(self, document: dict) -> list:
        return self._converter.convert(document)
