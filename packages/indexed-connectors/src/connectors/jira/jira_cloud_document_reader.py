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
        """
        Deprecated wrapper that configures a Jira Cloud document reader for backward compatibility.
        
        This initializer emits a DeprecationWarning and constructs an internal UnifiedJiraDocumentReader configured for Jira Cloud authentication; the instance exposes compatibility attributes from the internal reader. Prefer using UnifiedJiraDocumentReader with auth_type set to JiraAuthType.CLOUD.
        
        Parameters:
            base_url (str): Base URL of the Jira instance (e.g., "https://your-domain.atlassian.net").
            query (str): JQL query used to select issues/documents.
            email (str | None): Account email for Cloud authentication (optional).
            api_token (str | None): API token for Cloud authentication (optional).
            batch_size (int): Number of items fetched per request.
            number_of_retries (int): Number of retry attempts for transient failures.
            retry_delay (int | float): Delay in seconds between retries.
            max_skipped_items_in_row (int): Maximum consecutive items allowed to be skipped before aborting.
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
        """
        Read all documents matching the configured JQL query.
        
        Returns:
            documents (list[dict]): Documents extracted from Jira for issues that match the reader's query.
        """
        return self._reader.read_all_documents()

    def get_number_of_documents(self):
        """
        Get the total number of documents that match the reader's query.
        
        Returns:
            int: Total count of matching documents.
        """
        return self._reader.get_number_of_documents()

    def get_reader_details(self) -> dict:
        """
        Return a dictionary describing the reader's configuration and runtime details.
        
        Returns:
            details (dict): Mapping containing reader configuration and metadata (for example: base_url, query, auth_type, email/api token presence, batch_size, number_of_retries, retry_delay, max_skipped_items_in_row, and client information).
        """
        return self._reader.get_reader_details()