"""Tests for batch utility module.

Tests the read_items_in_batches function which handles paginated reading
with retry logic for individual items.
"""

import pytest
from utils.batch import read_items_in_batches


class TestReadItemsInBatches:
    """Test batch reading with pagination and error recovery."""

    def test_reads_all_items_in_batches(self):
        """Should read all items across multiple batches."""
        # Simulate paginated API with 25 items, batch size 10
        all_items = list(range(25))

        def read_batch(start, size, cursor=None):
            return {"items": all_items[start : start + size], "total": len(all_items)}

        def get_items(result):
            return result["items"]

        def get_total(result):
            return result["total"]

        # Read all items
        result = list(
            read_items_in_batches(read_batch, get_items, get_total, batch_size=10)
        )

        assert result == all_items
        assert len(result) == 25

    def test_handles_empty_result(self):
        """Should handle empty result set gracefully."""

        def read_batch(start, size, cursor=None):
            return {"items": [], "total": 0}

        result = list(
            read_items_in_batches(
                read_batch, lambda r: r["items"], lambda r: r["total"], batch_size=10
            )
        )

        assert result == []

    def test_recovers_from_batch_error_with_single_items(self):
        """Should recover from batch errors by reading items individually."""
        all_items = list(range(10))

        def read_batch(start, size, cursor=None):
            # Simulate batch error that triggers single-item retry
            if start == 3 and size == 3:
                raise ValueError("Batch 3-5 temporarily fails")
            # But individual items succeed
            return {"items": all_items[start : start + size], "total": len(all_items)}

        result = list(
            read_items_in_batches(
                read_batch,
                lambda r: r["items"],
                lambda r: r["total"],
                batch_size=3,
                max_skipped_items_in_row=3,
            )
        )

        # All items should be read successfully after retry
        assert len(result) == 10
        assert result == all_items

    def test_stops_after_max_consecutive_failures(self):
        """Should stop when too many consecutive items fail."""
        all_items = list(range(20))

        def read_batch(start, size, cursor=None):
            # First trigger batch error to switch to single-item mode
            if start == 10 and size == 5:
                raise ValueError("Batch failed")
            # Then simulate 4 consecutive single-item failures (exceeds max of 3)
            if 10 <= start < 14 and size == 1:
                raise ValueError(f"Item {start} failed")
            return {"items": all_items[start : start + size], "total": len(all_items)}

        # Should fail when 4th consecutive failure exceeds max_skipped_items_in_row=3
        with pytest.raises(ValueError, match="Item (13|10|11|12) failed"):
            list(
                read_items_in_batches(
                    read_batch,
                    lambda r: r["items"],
                    lambda r: r["total"],
                    batch_size=5,
                    max_skipped_items_in_row=3,
                )
            )

    def test_uses_cursor_based_pagination(self):
        """Should support cursor-based pagination."""
        # Simulate cursor-based API (like many modern APIs)
        pages = [
            {"items": [1, 2, 3], "total": 7, "cursor": "page2"},
            {"items": [4, 5], "total": 7, "cursor": "page3"},
            {"items": [6, 7], "total": 7, "cursor": None},
        ]
        call_count = [0]

        def read_batch(start, size, cursor=None):
            result = pages[call_count[0]]
            call_count[0] += 1
            return result

        def parse_cursor(result):
            return result.get("cursor")

        result = list(
            read_items_in_batches(
                read_batch,
                lambda r: r["items"],
                lambda r: r["total"],
                batch_size=3,
                cursor_parser=parse_cursor,
            )
        )

        assert result == [1, 2, 3, 4, 5, 6, 7]

    def test_batch_error_triggers_single_item_retry(self):
        """Should retry batch errors by reading items one by one."""
        all_items = list(range(15))
        calls = []

        def read_batch(start, size, cursor=None):
            calls.append((start, size))
            # Batch at position 6 fails, then succeed with individual items
            if start == 6 and size == 3:
                raise ValueError("Batch 6-8 failed")
            return {"items": all_items[start : start + size], "total": len(all_items)}

        result = list(
            read_items_in_batches(
                read_batch, lambda r: r["items"], lambda r: r["total"], batch_size=3
            )
        )

        # Should have read all items
        assert len(result) == 15
        # Verify fallback to size=1 happened after batch failure
        assert (6, 3) in calls  # Initial batch attempt that failed
        # After batch fails, it retries with size=1 for items 6, 7, 8
        assert (6, 1) in calls
        assert (7, 1) in calls
        assert (8, 1) in calls
