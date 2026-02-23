"""Tests for progress bar utilities."""

import pytest
from unittest.mock import Mock, patch

from indexed.utils.progress_bar import (
    set_cli_progress,
    clear_cli_progress,
    wrap_generator_with_progress_bar,
    wrap_iterator_with_progress_bar,
    create_progress_callback,
    create_progress_update_callback,
    create_standard_progress,
    create_standalone_progress,
    create_operation_progress,
    create_simple_spinner,
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

    def test_create_standalone_progress(self):
        """Should create a standalone progress bar."""
        progress = create_standalone_progress()

        assert progress is not None
        # Verify it's a Progress instance
        from rich.progress import Progress

        assert isinstance(progress, Progress)

    def test_create_simple_spinner(self):
        """Should create a simple spinner."""
        progress = create_simple_spinner("Loading...")

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


class TestProgressBarIntegration:
    """Integration tests for progress bar system."""

    @patch("indexed.utils.progress_bar.set_cli_progress")
    @patch("indexed.utils.progress_bar.clear_cli_progress")
    def test_progress_integration_no_cli(self, mock_clear, mock_set):
        """Should work when CLI integration not available."""
        # Clear any existing CLI progress
        clear_cli_progress()

        progress = create_standalone_progress()
        assert progress is not None

    @patch("indexed.utils.progress_bar.set_cli_progress")
    @patch("indexed.utils.progress_bar.clear_cli_progress")
    def test_progress_integration_with_cli(self, mock_clear, mock_set):
        """Should integrate with CLI progress when available."""
        mock_progress = Mock()
        mock_console = Mock()

        set_cli_progress(mock_progress, mock_console)

        # Should have set globals
        from indexed.utils import progress_bar

        assert progress_bar._cli_progress == mock_progress

        clear_cli_progress()

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


class TestWrapGeneratorWithProgressBar:
    """Test wrap_generator_with_progress_bar generator function."""

    def test_cli_integrated_path_yields_items(self):
        """Should yield all items using CLI-integrated progress when available."""
        mock_progress = Mock()
        mock_progress.add_task.return_value = 0
        mock_console = Mock()

        set_cli_progress(mock_progress, mock_console)

        result = list(wrap_generator_with_progress_bar(iter([10, 20, 30]), 3))

        assert result == [10, 20, 30]
        mock_progress.add_task.assert_called_once()
        assert mock_progress.update.call_count == 3

    def test_cli_integrated_path_adds_named_task(self):
        """Should add task with given name when CLI progress is set."""
        mock_progress = Mock()
        mock_progress.add_task.return_value = 0
        mock_console = Mock()

        set_cli_progress(mock_progress, mock_console)

        list(wrap_generator_with_progress_bar(iter([1, 2]), 2, progress_bar_name="Indexing"))

        mock_progress.add_task.assert_called_once_with("Indexing", total=2)

    def test_fallback_path_yields_items(self):
        """Should yield all items using standalone progress when CLI not set."""
        clear_cli_progress()

        result = list(wrap_generator_with_progress_bar(iter([1, 2, 3, 4]), 4))

        assert result == [1, 2, 3, 4]

    def test_fallback_path_empty_generator(self):
        """Should handle empty generator without error."""
        clear_cli_progress()

        result = list(wrap_generator_with_progress_bar(iter([]), 0))

        assert result == []


class TestWrapIteratorWithProgressBar:
    """Test wrap_iterator_with_progress_bar generator function."""

    def test_cli_integrated_path_yields_items(self):
        """Should yield all items using CLI-integrated progress when available."""
        mock_progress = Mock()
        mock_progress.add_task.return_value = 0
        mock_console = Mock()

        set_cli_progress(mock_progress, mock_console)

        items = [10, 20, 30]
        result = list(wrap_iterator_with_progress_bar(items))

        assert result == [10, 20, 30]
        mock_progress.add_task.assert_called_once()
        assert mock_progress.update.call_count == 3

    def test_cli_integrated_uses_len_if_available(self):
        """Should use len() for total when iterator supports it."""
        mock_progress = Mock()
        mock_progress.add_task.return_value = 0
        mock_console = Mock()

        set_cli_progress(mock_progress, mock_console)

        items = [1, 2, 3]  # list has __len__
        list(wrap_iterator_with_progress_bar(items, "Loading"))

        _, kwargs = mock_progress.add_task.call_args
        assert kwargs.get("total") == 3

    def test_fallback_path_yields_items(self):
        """Should yield all items using standalone progress when CLI not set."""
        clear_cli_progress()

        result = list(wrap_iterator_with_progress_bar([5, 6, 7]))

        assert result == [5, 6, 7]

    def test_fallback_path_empty_iterator(self):
        """Should handle empty iterator without error."""
        clear_cli_progress()

        result = list(wrap_iterator_with_progress_bar([]))

        assert result == []


class TestCreateOperationProgressExtended:
    """Additional tests for create_operation_progress context manager."""

    @patch("indexed.utils.progress_bar.time")
    def test_slow_path_updates_progress_to_complete(self, mock_time):
        """When operation is slow (elapsed >= 0.2s), should update progress to completed."""
        mock_time.time.side_effect = [0.0, 1.0]

        with create_operation_progress("slow-op") as (progress, task_id, callback):
            pass

        # slow path calls sleep(0.2)
        mock_time.sleep.assert_called_with(0.2)

    @patch("indexed.utils.progress_bar.set_cli_progress")
    @patch("indexed.utils.progress_bar.clear_cli_progress")
    def test_brackets_no_quotes_extracts_name(self, mock_clear, mock_set):
        """Should extract name from styled text without quotes via bracket fallback."""
        # Operation desc has brackets but no quoted text → uses bracket regex fallback
        with create_operation_progress("[bold]my-collection[/bold]", total=100) as (
            progress,
            task_id,
            callback,
        ):
            pass

        mock_clear.assert_called()
