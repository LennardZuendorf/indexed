"""Tests for progress bar utilities."""

from indexed.utils.progress_bar import (
    RichPhasedProgress,
    PlainPhasedProgress,
    create_phased_progress,
)


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

    def test_rich_phased_no_op_before_enter(self):
        """RichPhasedProgress methods are no-ops before __enter__."""
        progress = RichPhasedProgress()

        # These should not raise
        progress.start_phase("Phase A")
        progress.advance("Phase A")
        progress.finish_phase("Phase A")
        assert len(progress._tasks) == 0

    def test_rich_phased_advance_unknown_phase(self):
        """Advance on unknown phase should be no-op."""
        progress = RichPhasedProgress()

        with progress:
            # Should not raise
            progress.advance("nonexistent")

    def test_rich_phased_finish_unknown_phase(self):
        """Finish on unknown phase should be no-op."""
        progress = RichPhasedProgress()

        with progress:
            # Should not raise
            progress.finish_phase("nonexistent")

    def test_rich_phased_restart_existing_phase(self):
        """Starting an existing phase should update it, not create a duplicate."""
        progress = RichPhasedProgress()

        with progress:
            progress.start_phase("Phase A")
            progress.start_phase("Phase A", total=10)
            # Should still be one task
            assert len(progress._tasks) == 1

    def test_plain_phased_tracks_order(self):
        """PlainPhasedProgress should track phase order."""
        progress = PlainPhasedProgress()

        with progress:
            progress.start_phase("First")
            progress.start_phase("Second")
            assert progress._phase_order == ["First", "Second"]

    def test_plain_phased_no_duplicate_order(self):
        """Restarting a phase should not duplicate it in order."""
        progress = PlainPhasedProgress()

        with progress:
            progress.start_phase("First")
            progress.start_phase("First")
            assert progress._phase_order == ["First"]

    def test_create_phased_progress_returns_instance(self):
        """create_phased_progress should return a valid context manager."""
        progress = create_phased_progress("Test Title")
        assert progress is not None
        assert hasattr(progress, "__enter__")
        assert hasattr(progress, "__exit__")

    def test_create_phased_progress_with_title(self):
        """RichPhasedProgress should store the title."""
        progress = RichPhasedProgress(title="My Title")
        assert progress._title == "My Title"

    def test_create_phased_progress_without_title(self):
        """RichPhasedProgress should work without a title."""
        progress = RichPhasedProgress()
        assert progress._title == ""
