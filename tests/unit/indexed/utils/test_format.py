"""Tests for format utility functions."""

from datetime import datetime, timedelta, timezone


from indexed.utils.format import format_time, format_size, _try_parse_to_datetime


def _iso(dt: datetime) -> str:
    """Helper: convert datetime to ISO8601 string."""
    return dt.isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TestFormatTime:
    """Tests for format_time function."""

    def test_none_returns_unknown(self):
        assert format_time(None) == "unknown"

    def test_empty_string_returns_unknown(self):
        assert format_time("") == "unknown"

    def test_invalid_timestamp_returns_original(self):
        assert format_time("not-a-date") == "not-a-date"

    def test_just_now(self):
        ts = _iso(_utc_now() - timedelta(seconds=10))
        assert format_time(ts) == "just now"

    def test_exactly_at_boundary_just_now(self):
        ts = _iso(_utc_now() - timedelta(seconds=59))
        assert format_time(ts) == "just now"

    def test_minutes_ago_singular(self):
        ts = _iso(_utc_now() - timedelta(minutes=1))
        result = format_time(ts)
        assert result == "1 min ago"

    def test_minutes_ago_plural(self):
        ts = _iso(_utc_now() - timedelta(minutes=30))
        result = format_time(ts)
        assert "mins ago" in result

    def test_hours_ago_singular(self):
        ts = _iso(_utc_now() - timedelta(hours=1))
        result = format_time(ts)
        assert result == "1 hour ago"

    def test_hours_ago_plural(self):
        ts = _iso(_utc_now() - timedelta(hours=5))
        result = format_time(ts)
        assert "hours ago" in result

    def test_yesterday(self):
        ts = _iso(_utc_now() - timedelta(days=1, hours=1))
        result = format_time(ts)
        assert result.startswith("Yesterday at")

    def test_days_ago(self):
        ts = _iso(_utc_now() - timedelta(days=3))
        result = format_time(ts)
        assert "days ago" in result or "day ago" in result

    def test_old_date(self):
        ts = _iso(_utc_now() - timedelta(days=10))
        result = format_time(ts)
        # Should be formatted as YYYY-MM-DD HH:MM
        assert len(result) >= 10
        assert "-" in result

    def test_future_timestamp(self):
        ts = _iso(_utc_now() + timedelta(hours=1))
        result = format_time(ts)
        # Future timestamps are formatted as YYYY-MM-DD HH:MM:SS
        assert len(result) >= 10

    def test_zulu_timestamp(self):
        ts = (_utc_now() - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = format_time(ts)
        assert result == "just now"

    def test_no_timezone_assumes_utc(self):
        # Use UTC now then strip timezone to simulate a naive UTC timestamp
        dt_naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            seconds=30
        )
        ts = dt_naive.strftime("%Y-%m-%dT%H:%M:%S")
        result = format_time(ts)
        assert result == "just now"

    def test_unix_timestamp_string(self):
        unix_ts = str((_utc_now() - timedelta(seconds=5)).timestamp())
        result = format_time(unix_ts)
        assert result == "just now"


class TestFormatSize:
    """Tests for format_size function."""

    def test_none_returns_unknown(self):
        assert format_size(None) == "unknown"

    def test_bytes(self):
        assert format_size(512) == "512.0 B"

    def test_kilobytes(self):
        result = format_size(1024)
        assert "KB" in result

    def test_megabytes(self):
        result = format_size(1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self):
        result = format_size(1024 * 1024 * 1024)
        assert "GB" in result

    def test_terabytes(self):
        result = format_size(1024**4)
        assert "TB" in result

    def test_petabytes(self):
        result = format_size(1024**5)
        assert "PB" in result

    def test_zero_bytes(self):
        assert format_size(0) == "0.0 B"


class TestTryParseDatetime:
    """Tests for _try_parse_to_datetime helper."""

    def test_empty_string_returns_none(self):
        assert _try_parse_to_datetime("") is None

    def test_iso_with_timezone(self):
        ts = "2024-01-15T10:30:00+00:00"
        result = _try_parse_to_datetime(ts)
        assert result is not None
        assert result.year == 2024

    def test_zulu_timezone(self):
        ts = "2024-06-01T12:00:00Z"
        result = _try_parse_to_datetime(ts)
        assert result is not None
        assert result.tzinfo is not None

    def test_unix_timestamp_as_string(self):
        ts = "1700000000"
        result = _try_parse_to_datetime(ts)
        assert result is not None

    def test_invalid_returns_none(self):
        result = _try_parse_to_datetime("not-a-timestamp")
        assert result is None
