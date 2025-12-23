"""Tests for performance utility module.

Tests the execution timing and measurement functions.
"""

import pytest
from unittest.mock import Mock
from utils.performance import execute_and_measure_duration, log_execution_duration


class TestExecuteAndMeasureDuration:
    """Test basic timing measurement."""

    def test_measures_successful_execution(self):
        """Should measure duration and return result."""

        def func():
            return "result"

        result, error, duration = execute_and_measure_duration(func)

        assert result == "result"
        assert error is None
        assert duration >= 0
        assert isinstance(duration, float)

    def test_captures_exception_and_measures(self):
        """Should capture exception, still measure duration."""

        def func():
            raise ValueError("Something went wrong")

        result, error, duration = execute_and_measure_duration(func)

        assert result is None
        assert isinstance(error, ValueError)
        assert str(error) == "Something went wrong"
        assert duration >= 0

    def test_duration_is_positive(self):
        """Should always return positive duration."""
        import time

        def func():
            time.sleep(0.01)  # Sleep for 10ms
            return "done"

        result, error, duration = execute_and_measure_duration(func)

        assert duration > 0.009  # Allow some variance
        assert result == "done"


class TestLogExecutionDuration:
    """Test logging wrapper with duration measurement."""

    def test_executes_and_returns_result(self):
        """Should execute function and return result."""
        func = Mock(return_value="success")

        result = log_execution_duration(func, "test_operation")

        assert result == "success"
        func.assert_called_once()

    def test_raises_exception_from_function(self):
        """Should re-raise exceptions after measuring."""

        def failing_func():
            raise RuntimeError("Operation failed")

        with pytest.raises(RuntimeError, match="Operation failed"):
            log_execution_duration(failing_func, "failing_op")

    def test_respects_enabled_flag(self):
        """Should work with logging disabled."""
        func = Mock(return_value="result")

        # Should still work when disabled
        result = log_execution_duration(func, "silent_op", enabled=False)

        assert result == "result"
        func.assert_called_once()

    def test_handles_none_return_value(self):
        """Should handle functions that return None."""
        func = Mock(return_value=None)

        result = log_execution_duration(func, "no_return")

        assert result is None
        func.assert_called_once()

    def test_preserves_complex_return_types(self):
        """Should preserve complex return values."""
        expected = {"data": [1, 2, 3], "nested": {"key": "value"}}
        func = Mock(return_value=expected)

        result = log_execution_duration(func, "complex")

        assert result == expected
        assert result is expected  # Same object reference
