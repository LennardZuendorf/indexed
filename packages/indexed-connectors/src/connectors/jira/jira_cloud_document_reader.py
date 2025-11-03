"""Jira Cloud document reader (deprecated - use UnifiedJiraDocumentReader instead).

This module is maintained for backward compatibility but delegates all functionality
to the unified reader implementation.
"""

import warnings

from .unified_jira_document_reader import UnifiedJiraDocumentReader, JiraAuthType


class JiraCloudDocumentReader:
    """Jira Cloud document reader (DEPRECATED).

    This class is deprecated and maintained only for backward compatibility.
    New code should use UnifiedJiraDocumentReader with auth_type=JiraAuthType.CLOUD.

    All functionality is delegated to UnifiedJiraDocumentReader.
    """

    def __init__(
        self,
        base_url,
        query,
        email=None,
        api_token=None,
        batch_size=500,
        number_of_retries=3,
        retry_delay=1,
        max_skipped_items_in_row=5,
    ):
        """Initialize Jira Cloud document reader.

        Note: This class is deprecated. Consider using UnifiedJiraDocumentReader instead.
        """
        # Emit deprecation warning
        warnings.warn(
            'JiraCloudDocumentReader is deprecated. Use UnifiedJiraDocumentReader instead.',
            DeprecationWarning,
            stacklevel=2
        )
        
        # Delegate to unified reader
        self._reader = UnifiedJiraDocumentReader(
            base_url=base_url,
            query=query,
            auth_type=JiraAuthType.CLOUD,
            email=email,
            api_token=api_token,
            batch_size=batch_size,
            number_of_retries=number_of_retries,
            retry_delay=retry_delay,
            max_skipped_items_in_row=max_skipped_items_in_row,
        )

        # Expose attributes for compatibility
        self.base_url = self._reader.base_url
        self.query = self._reader.query
        self.email = self._reader.email
        self.api_token = self._reader.api_token
        self.batch_size = self._reader.batch_size
        self.number_of_retries = self._reader.number_of_retries
        self.retry_delay = self._reader.retry_delay
        self.max_skipped_items_in_row = self._reader.max_skipped_items_in_row
        self.fields = self._reader.fields
        self._client = self._reader._client

    def read_all_documents(self):
        """Read all documents matching the JQL query."""
        return self._reader.read_all_documents()

    def get_number_of_documents(self):
        """Get the total count of documents matching the query."""
        return self._reader.get_number_of_documents()

    def get_reader_details(self) -> dict:
        """Get reader configuration details."""
        return self._reader.get_reader_details()
