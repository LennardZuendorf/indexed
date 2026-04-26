"""Jira Server/DC document reader (deprecated - use UnifiedJiraDocumentReader instead).

This module is maintained for backward compatibility but delegates all functionality
to the unified reader implementation.
"""

import warnings

from .unified_jira_document_reader import UnifiedJiraDocumentReader, JiraAuthType


class JiraDocumentReader:
    """Jira Server/DC document reader (DEPRECATED).

    This class is deprecated and maintained only for backward compatibility.
    New code should use UnifiedJiraDocumentReader with appropriate auth_type.

    All functionality is delegated to UnifiedJiraDocumentReader.
    """

    def __init__(
        self,
        base_url,
        query,
        token=None,
        login=None,
        password=None,
        batch_size=500,
        number_of_retries=3,
        retry_delay=1,
        max_skipped_items_in_row=5,
        include_attachments=False,
        max_attachment_size_mb=10,
    ):
        """
        Create a deprecated Jira Server/DC document reader wrapper that delegates functionality to UnifiedJiraDocumentReader.

        This constructor emits a DeprecationWarning and instantiates an underlying UnifiedJiraDocumentReader using the provided parameters. Authentication type is chosen by precedence: if `token` is provided, server token authentication is used; else if both `login` and `password` are provided, server credentials authentication is used; otherwise it defaults to server token and defers validation to the unified reader. Common reader attributes (base_url, query, token, login, password, batch_size, number_of_retries, retry_delay, max_skipped_items_in_row, fields, and _client) are exposed on the wrapper for compatibility.

        Parameters:
            base_url (str): Base URL of the Jira Server/DC instance.
            query (str): JQL or query string used to select issues/documents.
            token (str, optional): Personal access token; takes precedence over login/password when provided.
            login (str, optional): Username for basic authentication; used only if `token` is not provided.
            password (str, optional): Password for basic authentication; used only if `token` is not provided.
            batch_size (int, optional): Number of items to fetch per request; passed through to the unified reader.
            number_of_retries (int, optional): Retry attempts for transient failures; passed through to the unified reader.
            retry_delay (int|float, optional): Delay in seconds between retries; passed through to the unified reader.
            max_skipped_items_in_row (int, optional): Maximum consecutive skipped items tolerated; passed through to the unified reader.
        """
        # Emit deprecation warning
        warnings.warn(
            "JiraDocumentReader is deprecated. Use UnifiedJiraDocumentReader instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Determine auth type based on provided credentials
        if token:
            auth_type = JiraAuthType.SERVER_TOKEN
        elif login and password:
            auth_type = JiraAuthType.SERVER_CREDENTIALS
        else:
            # Let the unified reader handle validation
            auth_type = JiraAuthType.SERVER_TOKEN

        # Delegate to unified reader
        self._reader = UnifiedJiraDocumentReader(
            base_url=base_url,
            query=query,
            auth_type=auth_type,
            token=token,
            login=login,
            password=password,
            batch_size=batch_size,
            number_of_retries=number_of_retries,
            retry_delay=retry_delay,
            max_skipped_items_in_row=max_skipped_items_in_row,
            include_attachments=include_attachments,
            max_attachment_size_mb=max_attachment_size_mb,
        )

        # Expose attributes for compatibility
        self.base_url = self._reader.base_url
        self.query = self._reader.query
        self.token = self._reader.token
        self.login = self._reader.login
        self.password = self._reader.password
        self.batch_size = self._reader.batch_size
        self.number_of_retries = self._reader.number_of_retries
        self.retry_delay = self._reader.retry_delay
        self.max_skipped_items_in_row = self._reader.max_skipped_items_in_row
        self.fields = self._reader.fields
        self._client = self._reader._client

    def read_all_documents(self):
        """
        Return an iterator of documents that match the configured JQL query.

        Returns:
            iterator (Iterator[dict]): An iterator over document records (each record represented as a dict) that match the reader's JQL query.
        """
        return self._reader.read_all_documents()

    def get_number_of_documents(self):
        """
        Return the total number of documents that match the reader's query.

        Returns:
            int: Total matching document count.
        """
        return self._reader.get_number_of_documents()

    def get_reader_details(self) -> dict:
        """
        Retrieve reader configuration details.

        Returns:
            details (dict): Configuration values for the reader, such as connection and query parameters and runtime settings (for example base URL, query, authentication info, batch size, retry settings, and configured fields).
        """
        return self._reader.get_reader_details()
