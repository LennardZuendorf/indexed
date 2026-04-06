from datetime import datetime, timezone
from typing import Optional


def format_source_type(source_type: Optional[str]) -> str:
    """Convert an internal source type identifier to a human-readable display name."""
    if not source_type:
        return "Unknown"

    type_map = {
        "jira": "Jira",
        "jiraCloud": "Jira Cloud",
        "confluence": "Confluence",
        "confluenceCloud": "Confluence Cloud",
        "localFiles": "Local Files",
    }
    return type_map.get(source_type, source_type.capitalize())


def format_time(timestamp: Optional[str]) -> str:
    """Format timestamp as nicely human-readable (e.g., '5 mins ago', 'Yesterday at 13:23', etc).

    Handles ISO8601 timestamps. If parsing fails, falls back to the raw string or 'unknown'.
    """
    if not timestamp:
        return "unknown"

    dt = _try_parse_to_datetime(timestamp)
    if not dt:
        return timestamp

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        # Assume UTC if tz not present
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt

    total_seconds = int(diff.total_seconds())
    minutes = total_seconds // 60
    hours = total_seconds // 3600
    days = diff.days

    if total_seconds < 0:
        # Future time
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    if total_seconds < 60:
        return "just now"
    elif total_seconds < 3600:
        return f"{minutes} min{'s' if minutes != 1 else ''} ago"
    elif total_seconds < 86400:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif days == 1:
        return f"Yesterday at {dt.strftime('%H:%M')}"
    elif days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    else:
        return dt.strftime("%Y-%m-%d %H:%M")


def _try_parse_to_datetime(timestamp: str) -> Optional[datetime]:
    """Parse string to datetime object, handling common timestamp formats."""
    if not timestamp:
        return None
    try:
        # Handle Zulu time
        ts = timestamp.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except Exception:
        try:
            # Try Unix timestamp (as string/int)
            return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
        except Exception:
            return None


def format_size(bytes: Optional[int]) -> str:
    """Format bytes to human-readable size."""
    if bytes is None:
        return "unknown"
    return _human_readable_size(float(bytes))


def _human_readable_size(size: float) -> str:
    """
    Converts size in bytes to a human readable string with appropriate unit.
    """
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"
