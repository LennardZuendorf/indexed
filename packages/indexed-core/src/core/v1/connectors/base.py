"""Base connector protocol for document sources.

Deprecated: import from ``protocols`` instead. Re-exported during transition.
"""

from protocols.connectors import BaseConnector, DocumentConverter, DocumentReader

__all__ = ["BaseConnector", "DocumentConverter", "DocumentReader"]
