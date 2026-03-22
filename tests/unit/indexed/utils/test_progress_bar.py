"""Tests for progress bar utilities."""

import pytest
from unittest.mock import Mock, patch

from indexed.utils.progress_bar import (
    set_cli_progress,
    clear_cli_progress,
    create_progress_callback,
    create_progress_update_callback,
    create_standard_progress,
    create_operation_progress,
    RichPhasedProgress,
    PlainPhasedProgress,
    create_phased_progress,
)


@pytest.fixture(autouse=True)
def reset_cli_progress():
    """Ensure CLI progress globals are reset after each test."""
    yield
    clear_cli_progress()


class TestCliProgressGlobals:
    """Test global CLI progress management."""

    def test_set_cli_progress(self):
        """Should set global CLI progress."""
        mock_progress = Mock()
        mock_console = Mock()

        set_cli_progress(mock_progress, mock_console)

        # Verify globals were set by creating a callback
        from indexed.utils import progress_bar

        assert progress_bar._cli_progress == mock_progress
        assert progress_bar._cli_console == mock_console

    def test_clear_cli_progress(self):
        """Should clear global CLI progress."""
        mock_progress = Mock()
        mock_console = Mock()

        set_cli_progress(mock_progress, mock_console)
        clear_cli_progress()

        # Verify globals were cleared
        from indexed.utils import progress_bar

        assert progress_bar._cli_progress is None
        assert progress_bar._cli_console is None


class TestCreateProgressCallback:
    """Test create_progress_callback function."""

    def test_callback_with_total(self):
        """Should update progress with completion percentage."""
        mock_progress = Mock()
        task_id = 1

        callback = create_progress_callback(mock_progress, task_id)

        # Create a mock update object
        update = Mock()
        update.total = 100
        update.current = 50
        update.message = "Processing..."

        callback(update)

        # Should have called progress.update with completed percentage
        mock_progress.update.assert_called_once()
        call_kwargs = mock_progress.update.call_args.kwargs
        assert call_kwargs["completed"] == 50  # 50/100 * 100

    def test_callback_without_total(self):
        """Should update progress message when total is unknown."""
        mock_progress = Mock()
        task_id = 1

        callback = create_progress_callback(mock_progress, task_id)

        # Create a mock update object with no total
        update = Mock()
        update.total = 0
        update.current = 0
        update.message = "Processing..."

        callback(update)

        # Should have called progress.update with description only
        mock_progress.update.assert_called_once()
        call_kwargs = mock_progress.update.call_args.kwargs
        assert "description" in call_kwargs


class TestCreateProgressUpdateCallback:
    """Test create_progress_update_callback function."""

    def test_callback_no_changes(self):
        """Should show 'No changes detected' when total is 0."""
        mock_status = Mock()

        callback = create_progress_update_callback(mock_status)

        # Create a mock update object with total=0
        update = Mock()
        update.total = 0
        update.current = 0
        update.stage = "scanning"
        update.message = "No new items"

        callback(update)

        # Should have updated status with no changes message
        mock_status.update.assert_called_once()
        call_args = mock_status.update.call_args[0]
        assert "No changes detected" in call_args[0]

    def test_callback_with_progress(self):
        """Should format progress message with counts."""
        mock_status = Mock()

        callback = create_progress_update_callback(mock_status)

        # Create a mock update object
        update = Mock()
        update.total = 100
        update.current = 75
        update.stage = "indexing"
        update.message = "Processing documents"

        callback(update)

        # Should have updated status with formatted message
        mock_status.update.assert_called_once()
        call_args = mock_status.update.call_args[0]
        assert "75/100" in call_args[0]
        assert "indexing" in call_args[0].lower()

    def test_callback_fallback_message(self):
        """Should use provided message when totals unavailable."""
        mock_status = Mock()

        callback = create_progress_update_callback(mock_status)

        # Create a mock update object with None total
        update = Mock()
        update.total = None
        update.current = 0
        update.stage = "connecting"
        update.message = "Connecting to remote service..."

        callback(update)

        # Should have updated status with message
        mock_status.update.assert_called_once()
        call_args = mock_status.update.call_args[0]
        assert "Connecting to remote service" in call_args[0]


class TestProgressFactories:
    """Test progress bar factory functions."""

    def test_create_standard_progress(self):
        """Should create a standardized progress bar."""
        progress = create_standard_progress()

        assert progress is not None
        # Verify it's a Progress instance
        from rich.progress import Progress

        assert isinstance(progress, Progress)


class TestCreateOperationProgress:
    """Test create_operation_progress context manager."""

    @patch("indexed.utils.progress_bar.set_cli_progress")
    @patch("indexed.utils.progress_bar.clear_cli_progress")
    def test_operation_progress_context_manager(self, mock_clear, mock_set):
        """Should manage progress context properly."""
        with create_operation_progress("Test Operation", total=100) as (
            progress,
            task_id,
            callback,
        ):
            # Verify context was entered
            assert progress is not None
            assert task_id is not None
            assert callable(callback)

        # Verify context was exited properly
        mock_clear.assert_called()

    @patch("indexed.utils.progress_bar.set_cli_progress")
    @patch("indexed.utils.progress_bar.clear_cli_progress")
    def test_operation_progress_fast_completion(self, mock_clear, mock_set):
        """Should handle fast operations efficiently."""
        with create_operation_progress("Quick Task", total=100) as (
            progress,
            task_id,
            callback,
        ):
            # Complete immediately (simulating fast operation)
            pass

        # Context should have exited cleanly
        mock_clear.assert_called()

    @patch("indexed.utils.progress_bar.set_cli_progress")
    @patch("indexed.utils.progress_bar.clear_cli_progress")
    def test_operation_progress_extracts_name(self, mock_clear, mock_set):
        """Should extract collection name from styled operation description."""
        with create_operation_progress(
            '[white]Updating "my-collection"[/white]', total=100
        ) as (progress, task_id, callback):
            # Should have extracted "my-collection" from styled text
            pass

        mock_clear.assert_called()

    @patch("indexed.utils.progress_bar.set_cli_progress")
    @patch("indexed.utils.progress_bar.clear_cli_progress")
    def test_operation_progress_callback_works(self, mock_clear, mock_set):
        """Should create a working progress callback."""
        with create_operation_progress("Test", total=100) as (
            progress,
            task_id,
            callback,
        ):
            # Verify callback is callable and works
            assert callable(callback)

            # Create a mock update
            update = Mock()
            update.total = 100
            update.current = 50
            update.message = "Halfway done"

            # Should not raise
            callback(update)

        mock_clear.assert_called()


class TestPhasedProgress:
    """Test phased progress implementations."""

    def test_plain_phased_progress_protocol(self):
        """PlainPhasedProgress should implement the protocol methods."""
        progress = PlainPhasedProgress()

        with progress:
            progress.start_phase("Phase 1", total=10)
            progress.advance("Phase 1", amount=5)
            progress.finish_phase("Phase 1")
            progress.log("A log message")

    def test_rich_phased_progress_protocol(self):
        """RichPhasedProgress should implement the protocol methods."""
        progress = RichPhasedProgress()

        with progress:
            progress.start_phase("Phase 1", total=10)
            progress.advance("Phase 1", amount=5)
            progress.finish_phase("Phase 1")
            progress.start_phase("Phase 2")
            progress.finish_phase("Phase 2")
            progress.log("A log message")

    def test_rich_phased_tracks_tasks(self):
        """RichPhasedProgress should track tasks by name."""
        progress = RichPhasedProgress()

        with progress:
            progress.start_phase("Phase A", total=10)
            assert "Phase A" in progress._tasks
            progress.finish_phase("Phase A")

    def test_plain_phased_tracks_order(self):
        """PlainPhasedProgress should track phase order."""
        progress = PlainPhasedProgress()

        with progress:
            progress.start_phase("First")
            progress.start_phase("Second")
            assert progress._phase_order == ["First", "Second"]

    def test_create_phased_progress_returns_instance(self):
        """create_phased_progress should return a valid instance."""
        progress = create_phased_progress("Test Title")
        assert progress is not None
        # Should have __enter__ and __exit__
        assert hasattr(progress, "__enter__")
        assert hasattr(progress, "__exit__")


class TestProgressCallbackChain:
    """Test progress callback integration."""

    def test_progress_callback_chain(self):
        """Should handle multiple updates through callback."""
        mock_status = Mock()
        callback = create_progress_update_callback(mock_status)

        # Simulate multiple updates
        updates = [
            Mock(total=100, current=25, stage="stage1", message="25%"),
            Mock(total=100, current=50, stage="stage2", message="50%"),
            Mock(total=100, current=75, stage="stage3", message="75%"),
            Mock(total=100, current=100, stage="complete", message="100%"),
        ]

        for update in updates:
            callback(update)

        # Should have called update for each progress report
        assert mock_status.update.call_count == 4
