"""Session-wide fixtures for isolated configuration.

This autouse fixture redirects global/workspace config paths used by
ConfigService so that tests cannot interact with real user or repository
configuration files. All tests run against temporary, empty TOML files
created inside a sandbox dir.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest import MonkeyPatch

from indexed_config import ConfigService


@pytest.fixture(scope="session", autouse=True)
def isolate_config_paths(tmp_path_factory: pytest.TempPathFactory):
    """Redirect config helper paths for the entire test session without using the
    function-scoped ``monkeypatch`` fixture (avoids ScopeMismatch errors).
    """

    mp = MonkeyPatch()

    sandbox_root = tmp_path_factory.mktemp("indexed_config_sandbox")

    # Create a fake HOME inside sandbox and point Path.home() to it
    sandbox_home = sandbox_root / "home"
    sandbox_home.mkdir(parents=True, exist_ok=True)

    # Create sandbox global root at ~/.indexed
    global_root = sandbox_home / ".indexed"
    global_root.mkdir(parents=True, exist_ok=True)
    (global_root / "config.toml").touch()

    # Also prepare a local root template (not overriding default behavior)
    local_template = sandbox_root / "local"
    local_template.mkdir(parents=True, exist_ok=True)
    (local_template / "config.toml").touch()

    # Patch Path.home to return sandbox_home so code using Path.home() is isolated
    mp.setattr(Path, "home", lambda: sandbox_home)

    # Reset ConfigService singleton for clean test state
    ConfigService.reset()

    yield  # run the test session

    # Teardown: undo monkeypatches and reset ConfigService singleton
    mp.undo()
    ConfigService.reset()


@pytest.fixture(autouse=True)
def reset_config_service():
    """Ensure ConfigService cache is cleared between individual tests."""
    yield
    ConfigService.reset()
