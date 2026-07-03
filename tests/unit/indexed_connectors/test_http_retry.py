"""Tests for shared HTTP retry policy across connector readers."""

from unittest.mock import Mock, patch

import pytest
from requests.exceptions import HTTPError

from connectors.confluence.confluence_cloud_document_reader import (
    ConfluenceCloudDocumentReader,
)
from connectors.confluence.confluence_document_reader import (
    ConfluenceAPIError,
    ConfluenceDocumentReader,
)
from connectors.jira.async_jira_cloud_reader import (
    AsyncJiraCloudDocumentReader,
    JiraCloudAPIError,
)
from connectors.outline.outline_document_reader import (
    OutlineAPIError,
    OutlineDocumentReader,
)
from utils.retry import (
    TRANSIENT_HTTP_STATUS,
    execute_with_retry,
    is_transient_http_error,
)


def _http_error_response(status_code: int, url: str, message: str = "error") -> Mock:
    response = Mock()
    response.ok = False
    response.status_code = status_code
    response.reason = "Error"
    response.url = url
    response.text = message
    response.json.return_value = {"message": message}
    response.raise_for_status.side_effect = HTTPError(response=response)
    return response


class TestIsTransientHttpError:
    """Unit tests for transient HTTP error classification."""

    @pytest.mark.parametrize("status", sorted(TRANSIENT_HTTP_STATUS))
    def test_transient_status_codes(self, status: int) -> None:
        exc = Exception("transient")
        exc.status_code = status
        assert is_transient_http_error(exc) is True

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    def test_permanent_status_codes(self, status: int) -> None:
        exc = Exception("permanent")
        exc.status_code = status
        assert is_transient_http_error(exc) is False

    def test_status_from_response_attribute(self) -> None:
        exc = Exception("via response")
        exc.response = Mock(status_code=503)
        assert is_transient_http_error(exc) is True

    def test_network_errors_without_status(self) -> None:
        assert is_transient_http_error(ConnectionError("refused")) is True
        assert is_transient_http_error(TimeoutError()) is True
        assert is_transient_http_error(OSError("broken pipe")) is True

    def test_non_transient_exception_without_status(self) -> None:
        assert is_transient_http_error(ValueError("bad input")) is False


class TestExecuteWithRetryPolicy:
    """execute_with_retry fail-fast vs retry behavior."""

    @patch("time.sleep")
    def test_404_fails_fast_without_retry(self, mock_sleep: Mock) -> None:
        exc = Exception("Not found")
        exc.status_code = 404
        func = Mock(side_effect=exc)

        with pytest.raises(Exception, match="Not found"):
            execute_with_retry(func, "fetch", retries=3, delay=1)

        assert func.call_count == 1
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    def test_429_retries_then_succeeds(self, mock_sleep: Mock) -> None:
        exc = Exception("Rate limited")
        exc.status_code = 429
        func = Mock(side_effect=[exc, "success"])

        result = execute_with_retry(func, "fetch", retries=3, delay=1)

        assert result == "success"
        assert func.call_count == 2
        mock_sleep.assert_called_once_with(1)


class TestAsyncJiraCloudReaderRetry:
    """Async Jira reader uses shared transient retry policy."""

    @pytest.fixture
    def reader(self) -> AsyncJiraCloudDocumentReader:
        return AsyncJiraCloudDocumentReader(
            base_url="https://example.atlassian.net",
            query="project = TEST",
            email="user@example.com",
            api_token="token",
            number_of_retries=3,
            retry_delay=1,
        )

    @patch("connectors.jira.async_jira_cloud_reader.requests.post")
    @patch("time.sleep")
    def test_404_fails_fast(
        self, mock_sleep: Mock, mock_post: Mock, reader: AsyncJiraCloudDocumentReader
    ) -> None:
        response = Mock()
        response.ok = False
        response.status_code = 404
        response.url = "https://example.atlassian.net/rest/api/3/search"
        response.text = "Not found"
        response.json.return_value = {"errorMessages": ["Issue not found"]}
        mock_post.return_value = response

        with pytest.raises(JiraCloudAPIError) as exc_info:
            reader._post_with_retry(
                "https://example.atlassian.net/rest/api/3/search",
                {"jql": "project = TEST"},
            )

        assert exc_info.value.status_code == 404
        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()

    @patch("connectors.jira.async_jira_cloud_reader.requests.post")
    @patch("time.sleep")
    def test_429_retries(
        self, mock_sleep: Mock, mock_post: Mock, reader: AsyncJiraCloudDocumentReader
    ) -> None:
        rate_limited = Mock()
        rate_limited.ok = False
        rate_limited.status_code = 429
        rate_limited.url = "https://example.atlassian.net/rest/api/3/search"
        rate_limited.text = "Rate limited"
        rate_limited.json.return_value = {"errorMessages": ["Rate limited"]}

        success = Mock()
        success.ok = True
        success.status_code = 200
        success.json.return_value = {"issues": []}

        mock_post.side_effect = [rate_limited, success]

        result = reader._post_with_retry(
            "https://example.atlassian.net/rest/api/3/search",
            {"jql": "project = TEST"},
        )

        assert result == {"issues": []}
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once_with(1)


class TestOutlineReaderRetry:
    """Outline reader uses shared transient retry policy."""

    @pytest.fixture
    def reader(self) -> OutlineDocumentReader:
        return OutlineDocumentReader(
            base_url="https://outline.example.com",
            api_token="token",
            number_of_retries=3,
            retry_delay=1,
        )

    @patch("requests.post")
    @patch("time.sleep")
    def test_404_fails_fast(
        self, mock_sleep: Mock, mock_post: Mock, reader: OutlineDocumentReader
    ) -> None:
        response = Mock()
        response.status_code = 404
        response.url = "https://outline.example.com/api/documents.list"
        response.text = "Not found"
        response.json.return_value = {"message": "Not found"}
        mock_post.return_value = response

        with pytest.raises(OutlineAPIError) as exc_info:
            reader._post_with_retry(
                "https://outline.example.com/api/documents.list",
                {"limit": 1},
            )

        assert exc_info.value.status_code == 404
        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()

    @patch("requests.post")
    @patch("time.sleep")
    def test_429_retries(
        self, mock_sleep: Mock, mock_post: Mock, reader: OutlineDocumentReader
    ) -> None:
        rate_limited = Mock()
        rate_limited.status_code = 429
        rate_limited.url = "https://outline.example.com/api/documents.list"
        rate_limited.text = "Rate limited"
        rate_limited.json.return_value = {"message": "Rate limited"}

        success = Mock()
        success.status_code = 200

        mock_post.side_effect = [rate_limited, success]

        result = reader._post_with_retry(
            "https://outline.example.com/api/documents.list",
            {"limit": 1},
        )

        assert result is success
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once_with(1)


class TestConfluenceReaderRetry:
    """Sync Confluence readers delegate to execute_with_retry."""

    @patch("connectors.confluence.confluence_document_reader.requests.get")
    @patch("time.sleep")
    def test_server_404_fails_fast(self, mock_sleep: Mock, mock_get: Mock) -> None:
        reader = ConfluenceDocumentReader(
            base_url="https://confluence.example.com",
            query="type=page",
            token="token",
            number_of_retries=3,
            retry_delay=1,
        )
        url = "https://confluence.example.com/rest/api/content/search"
        mock_get.return_value = _http_error_response(404, url, "Not found")

        with pytest.raises(ConfluenceAPIError) as exc_info:
            reader._ConfluenceDocumentReader__request(url, {"limit": 1})

        assert exc_info.value.status_code == 404
        assert mock_get.call_count == 1
        mock_sleep.assert_not_called()

    @patch("connectors.confluence.confluence_cloud_document_reader.requests.get")
    @patch("time.sleep")
    def test_cloud_429_retries(self, mock_sleep: Mock, mock_get: Mock) -> None:
        reader = ConfluenceCloudDocumentReader(
            base_url="https://example.atlassian.net",
            query="type=page",
            email="user@example.com",
            api_token="token",
            number_of_retries=3,
            retry_delay=1,
        )
        url = "https://example.atlassian.net/wiki/rest/api/search"
        rate_limited = _http_error_response(429, url, "Rate limited")

        success = Mock()
        success.ok = True
        success.status_code = 200
        success.raise_for_status.return_value = None
        success.json.return_value = {"results": [], "size": 0, "_links": {}}

        mock_get.side_effect = [rate_limited, success]

        result = reader._ConfluenceCloudDocumentReader__request(url, {"limit": 1})

        assert result == {"results": [], "size": 0, "_links": {}}
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once_with(1)
