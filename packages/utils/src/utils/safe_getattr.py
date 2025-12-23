"""Safe attribute access utilities for handling MagicMock in tests."""

from typing import Any


def safe_str_attr(obj: Any, name: str, default: str) -> str:
    """Safely get string attribute, handling MagicMock in tests.

    This utility safely retrieves a string attribute from an object,
    returning a default value if the attribute is missing or not a string.
    This is particularly useful when working with mocked objects in tests.

    Args:
        obj: Object to get attribute from
        name: Attribute name
        default: Default value if attribute missing or not a string

    Returns:
        String attribute value or default

    Examples:
        >>> class Config:
        ...     url = "https://example.com"
        >>> safe_str_attr(Config(), "url", "default")
        'https://example.com'
        >>> safe_str_attr(Config(), "missing", "default")
        'default'
    """
    val = getattr(obj, name, default)
    return val if isinstance(val, str) else default
