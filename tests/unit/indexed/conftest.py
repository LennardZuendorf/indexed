"""Test configuration for main app tests."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

TEST_COLLECTIONS_PATH = Path("/tmp/test-collections")
TEST_CACHES_PATH = Path("/tmp/test-caches")


def make_cli_context(config_service: MagicMock | None = None):
    """Build a CliContext stand-in for resolve_collections_context patches."""
    mock_config = config_service or MagicMock()
    mock_config.resolve_storage_mode.return_value = "global"
    mock_config.get_workspace_preference.return_value = None
    mock_config.store.read.return_value = {}
    return type(
        "MockCliContext",
        (),
        {
            "collections_path": TEST_COLLECTIONS_PATH,
            "caches_path": TEST_CACHES_PATH,
            "mode": "global",
            "config_service": mock_config,
            "connector_registry": {},
        },
    )()


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
