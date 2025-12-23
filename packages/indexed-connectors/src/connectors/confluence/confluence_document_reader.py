import re

import requests
from requests.exceptions import HTTPError

from utils.retry import execute_with_retry
from utils.batch import read_items_in_batches


class ConfluenceAPIError(Exception):
    """Custom exception for Confluence API errors with detailed information."""

    def __init__(self, status_code: int, reason: str, message: str, url: str):
        """
        Initialize the ConfluenceAPIError with HTTP response details and produce a formatted error message.

        Parameters:
            status_code (int): HTTP status code returned by the Confluence API.
            reason (str): Short HTTP reason phrase or error reason.
            message (str): Detailed error message extracted from the response body or response text.
            url (str): The request URL that produced the error.
        """
        self.status_code = status_code
        self.reason = reason
        self.message = message
        self.url = url
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """
        Format a detailed, human-readable message describing this Confluence API error.

        Returns:
            str: A multi-line string containing the HTTP status code and reason, the request URL, and the error message.
        """
        return (
            f"Confluence API Error ({self.status_code} {self.reason})\n"
            f"  URL: {self.url}\n"
            f"  Message: {self.message}"
        )


class ConfluenceDocumentReader:
    def __init__(
        self,
        base_url,
        query,
        token=None,
        login=None,
        password=None,
        batch_size=50,
        number_of_retries=3,
        retry_delay=1,
        max_skipped_items_in_row=5,
        read_all_comments=False,
    ):
        # "token" or "login" and "password" must be provided
        """
        Initialize the ConfluenceDocumentReader with connection, query, batching, retry, and comment-read configuration.

        Parameters:
            base_url (str): Base URL of the Confluence instance (e.g., "https://confluence.example.com").
            query (str): User CQL query used to find pages; will be normalized to include "type=page" when appropriate.
            token (str, optional): Bearer token for API authentication. Either this or both `login` and `password` must be provided.
            login (str, optional): Username for basic auth; required together with `password` if `token` is not provided.
            password (str, optional): Password for basic auth; required together with `login` if `token` is not provided.
            batch_size (int, optional): Number of items to request per API batch; defaults to 50.
            number_of_retries (int, optional): Number of retry attempts for transient request failures; defaults to 3.
            retry_delay (int|float, optional): Delay in seconds between retry attempts; defaults to 1.
            max_skipped_items_in_row (int, optional): Maximum consecutive skipped items tolerated when reading batches; defaults to 5.
            read_all_comments (bool, optional): If True, the reader will fetch all nested comments for a page (requires additional requests); if False, only the first-level comment bodies are expanded in the main page request.

        Raises:
            ValueError: If neither `token` nor both `login` and `password` are provided.
        """
        if not token and (not login or not password):
            raise ValueError(
                "Either 'token' or both 'login' and 'password' must be provided."
            )

        self.base_url = base_url
        self.query = ConfluenceDocumentReader.build_page_query(query)
        self.token = token
        self.login = login
        self.password = password
        self.batch_size = batch_size
        # Confluence has hierarchical comments, we can read first level by adding "children.comment.body.storage" to "expand" parameter
        # but to read all comments we need to make additional request with "depth=all" parameter
        self.expand = (
            "body.storage,ancestors,version,children.comment"
            if read_all_comments
            else "body.storage,ancestors,version,children.comment.body.storage"
        )
        self.number_of_retries = number_of_retries
        self.retry_delay = retry_delay
        self.max_skipped_items_in_row = max_skipped_items_in_row
        self.read_all_comments = read_all_comments

    def read_all_documents(self):
        for page in self.__read_items():
            yield {"page": page, "comments": self.__read_comments(page)}

    def get_number_of_documents(self):
        search_result = self.__request(
            self.__add_url_prefix("/rest/api/content/search"),
            {"cql": self.query, "limit": 1, "start": 0},
        )

        return search_result["totalSize"]

    def get_reader_details(self) -> dict:
        return {
            "type": "confluence",
            "baseUrl": self.base_url,
            "query": self.query,
            "expand": self.expand,
            "batchSize": self.batch_size,
            "readAllComments": self.read_all_comments,
        }

    @staticmethod
    def build_page_query(user_query):
        """
        Constructs a Confluence CQL query that ensures results are pages.

        If `user_query` is empty returns a query that selects pages only. If `user_query`
        already contains a `type=page` clause (case-insensitive, flexible spacing) it is
        returned unchanged; otherwise the function wraps the provided fragment with
        `type=page AND (...)`.

        Parameters:
            user_query (str): A CQL fragment provided by the user; may be empty or already
                include a `type=page` clause.

        Returns:
            str: A CQL query string that restricts results to pages according to
            `user_query`.
        """
        if not user_query:
            return "type=page"

        # Check if user query already contains type=page (with various spacing)
        if re.search(r"\btype\s*=\s*page\b", user_query, re.IGNORECASE):
            return user_query

        return f"type=page AND ({user_query})"

    def __add_url_prefix(self, relative_path):
        """
        Prepend the reader's base URL to a relative path.

        Parameters:
            relative_path (str): Relative URL path to append to the reader's base_url.

        Returns:
            full_url (str): Absolute URL formed by concatenating base_url and relative_path.
        """
        return self.base_url + relative_path

    def __read_comments(self, page):
        if page["children"]["comment"]["size"] == 0:
            return []

        if not self.read_all_comments:
            return page["children"]["comment"]["results"]

        def read_batch_func(start_at, batch_size):
            return self.__request(
                self.__add_url_prefix(f"/rest/api/content/{page['id']}/child/comment"),
                {
                    "limit": batch_size,
                    "start": start_at,
                    "expand": "body.storage",
                    "depth": "all",
                },
            )

        comments_generator = read_items_in_batches(
            read_batch_func,
            fetch_items_from_result_func=lambda result: result["results"],
            fetch_total_from_result_func=lambda result: result["size"],
            batch_size=self.batch_size,
            max_skipped_items_in_row=self.max_skipped_items_in_row,
            itemsName="comments",
        )

        return [comment for comment in comments_generator]

    def __read_items(self):
        def read_batch_func(start_at, batch_size):
            return self.__request(
                self.__add_url_prefix("/rest/api/content/search"),
                {
                    "cql": self.query,
                    "limit": batch_size,
                    "start": start_at,
                    "expand": self.expand,
                },
            )

        return read_items_in_batches(
            read_batch_func,
            fetch_items_from_result_func=lambda result: result["results"],
            fetch_total_from_result_func=lambda result: result["totalSize"],
            batch_size=self.batch_size,
            max_skipped_items_in_row=self.max_skipped_items_in_row,
            itemsName="pages",
        )

    def __request(self, url, params):
        """
        Perform an HTTP GET against the given Confluence API URL with the provided query parameters and return the parsed JSON response.

        Parameters:
            url (str): Full request URL to call.
            params (dict): Query parameters to include in the request.

        Returns:
            dict: The parsed JSON body of the successful response.

        Raises:
            ConfluenceAPIError: If the request fails (non-2xx status); error includes status code, reason, message, and URL.
        """

        def do_request():
            response = requests.get(
                url=url,
                headers={
                    "Accept": "application/json",
                    **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
                },
                params=params,
                auth=(
                    (self.login, self.password)
                    if self.login and self.password
                    else None
                ),
            )
            try:
                response.raise_for_status()
            except HTTPError:
                # Try to extract detailed error from JSON response
                error_message = "Unknown error"
                error_reason = response.reason
                try:
                    error_body = response.json()
                    error_message = error_body.get("message", error_message)
                    error_reason = error_body.get("reason", error_reason)
                except Exception:
                    # If JSON parsing fails, use the response text
                    error_message = (
                        response.text[:500] if response.text else error_message
                    )
                raise ConfluenceAPIError(
                    status_code=response.status_code,
                    reason=error_reason,
                    message=error_message,
                    url=response.url,
                )
            return response.json()

        return execute_with_retry(
            do_request,
            f"Requesting items with params: {params}",
            self.number_of_retries,
            self.retry_delay,
        )
