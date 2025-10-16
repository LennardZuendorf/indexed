from atlassian import Jira

from utils.retry import execute_with_retry
from utils.batch import read_items_in_batches


class JiraCloudDocumentReader:
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
        # "email" and "api_token" must be provided for Cloud
        if not email or not api_token:
            raise ValueError(
                "Both 'email' and 'api_token' must be provided for Jira Cloud."
            )

        # Ensure base_url has the correct Cloud format
        if not base_url.endswith(".atlassian.net"):
            raise ValueError(
                "Base URL must be a Jira Cloud URL (ending with .atlassian.net)"
            )

        self.base_url = base_url
        self.query = query
        self.email = email
        self.api_token = api_token
        self.batch_size = batch_size
        self.number_of_retries = number_of_retries
        self.retry_delay = retry_delay
        self.max_skipped_items_in_row = max_skipped_items_in_row
        self.fields = "summary,description,comment,updated"

        # Initialize atlassian-python-api Jira client
        self._client = Jira(
            url=self.base_url, 
            username=self.email, 
            password=self.api_token,
            cloud=True
        )

    def read_all_documents(self):
        return self.__read_items()

    def get_number_of_documents(self):
        def do_request():
            # Use jql with limit=1 to get total count efficiently
            result = self._client.jql(
                self.query, 
                fields=self.fields,
                start=0,
                limit=1
            )
            return result.get("total", 0)

        return execute_with_retry(
            do_request,
            f"Getting document count for query: {self.query}",
            self.number_of_retries,
            self.retry_delay,
        )

    def get_reader_details(self) -> dict:
        return {
            "type": "jiraCloud",
            "baseUrl": self.base_url,
            "query": self.query,
            "batchSize": self.batch_size,
            "fields": self.fields,
        }

    def __read_items(self):
        def read_batch_func(start_at, batch_size):
            return self.__request_items(start_at=start_at, max_results=batch_size)

        return read_items_in_batches(
            read_batch_func,
            fetch_items_from_result_func=lambda result: result["issues"],
            fetch_total_from_result_func=lambda result: result["total"],
            batch_size=self.batch_size,
            max_skipped_items_in_row=self.max_skipped_items_in_row,
        )

    def __request_items(self, start_at: int, max_results: int):
        def do_request():
            result = self._client.jql(
                self.query,
                fields=self.fields,
                start=start_at,
                limit=max_results
            )
            return {
                "issues": result.get("issues", []),
                "total": result.get("total", 0),
            }

        return execute_with_retry(
            do_request,
            f"Requesting items at {start_at} with max {max_results}",
            self.number_of_retries,
            self.retry_delay,
        )
