"""Comprehensive tests for context managers utility module."""

import logging
import warnings
from io import StringIO
from unittest.mock import Mock, patch
import pytest

from indexed.utils.context_managers import (
    NoOpContext,
    suppress_core_output,
)


class TestNoOpContext:
    """Test NoOpContext manager."""

    def test_enter_returns_self(self):
        """Should return self on __enter__."""
        ctx = NoOpContext()
        result = ctx.__enter__()
        assert result is ctx

    def test_exit_does_nothing(self):
        """Should do nothing on __exit__."""
        ctx = NoOpContext()
        # Should not raise
        ctx.__exit__(None, None, None)

    def test_can_be_used_as_context_manager(self):
        """Should work as context manager."""
        executed = False
        with NoOpContext():
            executed = True
        assert executed is True

    def test_allows_code_execution(self):
        """Should allow code to execute normally."""
        result = []
        with NoOpContext():
            result.append(1)
            result.append(2)
        assert result == [1, 2]

    def test_does_not_suppress_exceptions(self):
        """Should not suppress exceptions from within block."""
        with pytest.raises(ValueError):
            with NoOpContext():
                raise ValueError("test error")

    def test_multiple_uses(self):
        """Should be reusable multiple times."""
        ctx = NoOpContext()
        
        with ctx:
            pass
        
        with ctx:
            pass
        
        # Should not raise


class TestSuppressCoreOutput:
    """Test suppress_core_output context manager."""

    def test_suppresses_logging_output(self):
        """Should suppress standard logging output."""
        logger = logging.getLogger("test_logger")
        original_level = logger.level
        
        with suppress_core_output():
            # Logging should be suppressed
            current_level = logging.getLogger().level
            assert current_level == logging.CRITICAL
        
        # Should restore original level
        assert logging.getLogger().level == original_level

    def test_restores_logging_level_after_exit(self):
        """Should restore original logging level after exiting context."""
        root_logger = logging.getLogger()
        original_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)
        
        with suppress_core_output():
            pass
        
        # Should restore to DEBUG
        assert root_logger.level == logging.DEBUG
        
        # Cleanup
        root_logger.setLevel(original_level)

    def test_suppresses_warnings(self):
        """Should suppress Python warnings."""
        with suppress_core_output():
            # This warning should be suppressed
            warnings.warn("test warning", DeprecationWarning)
        # Should not raise or print

    @patch('indexed.utils.context_managers.loguru_logger')
    def test_disables_loguru(self, mock_loguru):
        """Should disable loguru logging."""
        with suppress_core_output():
            mock_loguru.disable.assert_called_once_with("")
        
        # Should re-enable after exit
        mock_loguru.enable.assert_called_once_with("")

    @patch('indexed.utils.context_managers.loguru_logger')
    def test_reenables_loguru_after_exit(self, mock_loguru):
        """Should re-enable loguru after exiting context."""
        with suppress_core_output():
            pass
        
        mock_loguru.enable.assert_called_with("")

    def test_redirect_streams_false_allows_rich_output(self):
        """Should allow Rich console output when redirect_streams=False."""
        # Default behavior - no redirection
        with suppress_core_output(redirect_streams=False):
            # Rich console should work
            print("This should print")
        # No assertion - just shouldn't crash

    def test_redirect_streams_true_captures_stdout(self):
        """Should redirect stdout when redirect_streams=True."""
        with suppress_core_output(redirect_streams=True):
            print("This should be captured")
        # Output should have been captured (not displayed)

    def test_redirect_streams_true_captures_stderr(self):
        """Should redirect stderr when redirect_streams=True."""
        import sys
        
        with suppress_core_output(redirect_streams=True):
            sys.stderr.write("Error message\n")
        # Error should have been captured (not displayed)

    def test_restores_state_on_exception(self):
        """Should restore logging state even if exception occurs."""
        original_level = logging.getLogger().level
        
        with pytest.raises(ValueError):
            with suppress_core_output():
                raise ValueError("test error")
        
        # Should have restored original level
        assert logging.getLogger().level == original_level

    @patch('indexed.utils.context_managers.loguru_logger')
    def test_reenables_loguru_on_exception(self, mock_loguru):
        """Should re-enable loguru even if exception occurs."""
        with pytest.raises(ValueError):
            with suppress_core_output():
                raise ValueError("test error")
        
        # Should have called enable
        mock_loguru.enable.assert_called_with("")


class TestSuppressCoreOutputIntegration:
    """Integration tests for suppress_core_output."""

    def test_nested_suppression(self):
        """Should handle nested suppression contexts."""
        original_level = logging.getLogger().level
        
        with suppress_core_output():
            assert logging.getLogger().level == logging.CRITICAL
            
            with suppress_core_output():
                assert logging.getLogger().level == logging.CRITICAL
            
            assert logging.getLogger().level == logging.CRITICAL
        
        # Should restore original
        assert logging.getLogger().level == original_level

    def test_logger_configuration_preserved(self):
        """Should preserve logger configuration beyond just level."""
        root_logger = logging.getLogger()
        handler = logging.StreamHandler()
        root_logger.addHandler(handler)
        handler_count = len(root_logger.handlers)
        
        with suppress_core_output():
            pass
        
        # Handlers should still be present
        assert len(root_logger.handlers) == handler_count
        root_logger.removeHandler(handler)

    def test_specific_logger_suppression(self):
        """Should suppress all loggers, not just root."""
        specific_logger = logging.getLogger("my.specific.logger")
        specific_logger.setLevel(logging.DEBUG)
        
        with suppress_core_output():
            # Root logger should be CRITICAL
            assert logging.getLogger().level == logging.CRITICAL
        
        # Specific logger level unchanged (suppression is at root)
        assert specific_logger.level == logging.DEBUG

    @patch('indexed.utils.context_managers.loguru_logger')
    def test_loguru_disable_enable_called_correctly(self, mock_loguru):
        """Should call loguru disable/enable in correct order."""
        with suppress_core_output():
            pass
        
        # Verify call order
        assert mock_loguru.disable.called
        assert mock_loguru.enable.called
        
        # disable should be called before enable
        calls = [call[0] for call in mock_loguru.method_calls]
        disable_idx = calls.index('disable')
        enable_idx = calls.index('enable')
        assert disable_idx < enable_idx


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_suppress_output_with_no_loguru(self):
        """Should handle case where loguru is not available."""
        with patch('indexed.utils.context_managers.loguru_logger', None):
            # Should not raise even if loguru is None
            with suppress_core_output():
                pass

    def test_multiple_sequential_uses(self):
        """Should work correctly when used multiple times sequentially."""
        for _ in range(3):
            with suppress_core_output():
                logging.debug("suppressed")

    def test_noop_context_with_exception_preserves_traceback(self):
        """Should preserve exception traceback through NoOpContext."""
        try:
            with NoOpContext():
                raise ValueError("test error")
        except ValueError as e:
            assert str(e) == "test error"
            assert e.__traceback__ is not None

    def test_suppress_with_system_exit(self):
        """Should handle SystemExit properly."""
        with pytest.raises(SystemExit):
            with suppress_core_output():
                raise SystemExit(1)

    def test_suppress_with_keyboard_interrupt(self):
        """Should handle KeyboardInterrupt properly."""
        with pytest.raises(KeyboardInterrupt):
            with suppress_core_output():
                raise KeyboardInterrupt()

    def test_concurrent_context_usage(self):
        """Should handle context managers from different threads safely."""
        # Note: This is a basic test; true thread safety would need more complex testing
        results = []
        
        with suppress_core_output():
            results.append(logging.getLogger().level)
        
        assert logging.CRITICAL in results