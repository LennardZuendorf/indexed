"""Test configuration for main app tests."""

import pytest


@pytest.fixture
def mock_getenv_defaults(mocker):
    """Mock os.getenv with default test values."""

    def getenv_side_effect(key, default=None):
        if key == "INDEXED_LOG_LEVEL":
            return None
        elif key == "INDEXED_LOG_JSON":
            return default if default else "false"
        return default

    return mocker.patch("indexed.app.os.getenv", side_effect=getenv_side_effect)
