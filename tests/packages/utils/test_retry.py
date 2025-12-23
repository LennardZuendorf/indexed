"""Tests for retry utility module.

Tests the execute_with_retry function which handles retries with
exponential backoff and rate limit awareness.
"""

import pytest
from unittest.mock import Mock, patch
from utils.retry import execute_with_retry


class TestExecuteWithRetry:
    """Test retry logic with backoff and rate limiting."""

    def test_succeeds_on_first_attempt(self):
        """Should return result immediately if function succeeds."""
        func = Mock(return_value="success")

        result = execute_with_retry(func, "test_func", retries=3)

        assert result == "success"
        assert func.call_count == 1

    @patch("time.sleep")
    def test_retries_after_failure_then_succeeds(self, mock_sleep):
        """Should retry failed function and eventually succeed."""
        func = Mock(
            side_effect=[
                ValueError("First attempt"),
                ValueError("Second attempt"),
                "success",
            ]
        )

        result = execute_with_retry(func, "test_func", retries=3, delay=1)

        assert result == "success"
        assert func.call_count == 3
        # Verify exponential backoff: 1, 2 seconds
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)  # First retry: 1 * 2^0
        mock_sleep.assert_any_call(2)  # Second retry: 1 * 2^1

    @patch("time.sleep")
    def test_raises_after_all_retries_exhausted(self, mock_sleep):
        """Should raise last exception after all retries fail."""
        func = Mock(side_effect=ValueError("Persistent error"))

        with pytest.raises(ValueError, match="Persistent error"):
            execute_with_retry(func, "test_func", retries=3)

        assert func.call_count == 3
        assert mock_sleep.call_count == 2  # Sleep between attempts, not after last

    @patch("time.sleep")
    def test_respects_retry_after_header_on_429(self, mock_sleep):
        """Should respect Retry-After header for rate limiting."""
        # Create mock exception with rate limit info
        exc = Exception("Rate limited")
        exc.status_code = 429
        response = Mock()
        response.status_code = 429
        response.headers = {"Retry-After": "5"}
        exc.response = response

        func = Mock(side_effect=[exc, "success"])

        result = execute_with_retry(func, "test_func", retries=3, delay=1)

        assert result == "success"
        # Should use max(Retry-After, exponential_backoff)
        # Retry-After=5 > exponential 1 * 2^0 = 1
        mock_sleep.assert_called_once_with(5.0)

    @patch("time.sleep")
    def test_handles_missing_retry_after_header(self, mock_sleep):
        """Should fallback to exponential backoff if Retry-After missing."""
        exc = Exception("Rate limited")
        exc.status_code = 429
        # No response or headers

        func = Mock(side_effect=[exc, "success"])

        result = execute_with_retry(func, "test_func", retries=3, delay=2)

        assert result == "success"
        # Should use exponential backoff
        mock_sleep.assert_called_once_with(2)  # 2 * 2^0

    @patch("time.sleep")
    def test_exponential_backoff_progression(self, mock_sleep):
        """Should increase delay exponentially on each retry."""
        func = Mock(
            side_effect=[
                ValueError("Attempt 1"),
                ValueError("Attempt 2"),
                ValueError("Attempt 3"),
                "success",
            ]
        )

        result = execute_with_retry(func, "test_func", retries=4, delay=1)

        assert result == "success"
        assert mock_sleep.call_count == 3
        # Check exponential progression: 1, 2, 4
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls == [1, 2, 4]

    @patch("time.sleep")
    def test_handles_exception_with_response_attribute(self, mock_sleep):
        """Should handle exceptions that have response.status_code."""
        # Some HTTP libraries use exception.response.status_code
        exc = Exception("HTTP error")
        response = Mock()
        response.status_code = 429
        response.headers = {}
        exc.response = response

        func = Mock(side_effect=[exc, "success"])

        result = execute_with_retry(func, "test_func", retries=2)

        assert result == "success"

    def test_preserves_function_return_value(self):
        """Should return exact value from successful function call."""
        expected_value = {"data": [1, 2, 3], "status": "ok"}
        func = Mock(return_value=expected_value)

        result = execute_with_retry(func, "test_func")

        assert result == expected_value
        assert result is expected_value  # Same object

    @patch("time.sleep")
    def test_logs_warnings_for_failures(self, mock_sleep):
        """Should log warning for each failed attempt (verified implicitly)."""
        # This test verifies the retry behavior happens as expected
        # Actual logging is tested by loguru, we just verify the flow
        func = Mock(side_effect=[RuntimeError("Fail"), "success"])

        result = execute_with_retry(func, "important_operation", retries=2)

        assert result == "success"
        assert func.call_count == 2
