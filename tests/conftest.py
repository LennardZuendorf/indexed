"""Session-wide fixtures for isolated configuration.

This autouse fixture redirects global/workspace config paths used by
ConfigService *and* legacy `indexed.toml` loading so that tests cannot
interact with real user or repository configuration files. All tests
run against temporary, empty TOML files created inside a sandbox dir.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest import MonkeyPatch

import core.v1.config.store as store_module
import core.v1.engine.services.config_service as cs_module


@pytest.fixture(scope="session", autouse=True)
def isolate_config_paths(tmp_path_factory: pytest.TempPathFactory):
    """Redirect config helper paths for the entire test session without using the
    function-scoped ``monkeypatch`` fixture (avoids ScopeMismatch errors).
    """

    mp = MonkeyPatch()

    sandbox_root = tmp_path_factory.mktemp("indexed_config_sandbox")

    # Global config (~/.config/indexed/config.toml)
    global_path = sandbox_root / "global.toml"
    global_path.touch()

    # Workspace config (<ws>/.indexed/config.toml)
    workspace_path = sandbox_root / ".indexed" / "config.toml"
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    workspace_path.touch()

    # Apply patches
    mp.setattr(
        store_module, "get_global_config_path", lambda: global_path, raising=False
    )
    mp.setattr(cs_module, "get_global_config_path", lambda: global_path, raising=False)

    # Preserve original implementations for delegated calls
    _orig_get_ws = store_module.get_workspace_config_path  # type: ignore[attr-defined]

    def _patched_get_ws(wp: Path | None = None):  # type: ignore[override]
        if wp is None:
            return workspace_path
        return _orig_get_ws(wp)

    mp.setattr(
        store_module, "get_workspace_config_path", _patched_get_ws, raising=False
    )

    # Do NOT patch get_config_path so tests manipulating root-level indexed.toml still work

    yield  # run the test session

    # Teardown: undo monkeypatches and reset ConfigService singleton/cache
    mp.undo()
    cs_module.ConfigService._instance = None
    cs_module.ConfigService._settings_cache = None


@pytest.fixture(autouse=True)
def reset_config_service():
    """Ensure ConfigService cache is cleared between individual tests."""
    yield
    cs_module.ConfigService._instance = None
    cs_module.ConfigService._settings_cache = None
