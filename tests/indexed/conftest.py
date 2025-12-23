"""Test configuration for main app tests."""

import pytest


def pytest_collection_modifyitems(items):
    """Add 'indexed' marker to all tests in this directory."""
    for item in items:
        item.add_marker(pytest.mark.indexed)
