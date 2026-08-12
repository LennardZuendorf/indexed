"""ConfigService against the ONE global store (workspace-profile/1, R1).

Replaces the storage-mode preference/resolution suite: there is no local root,
no ``mode_override``, no ``[workspace] mode`` preference. What remains worth
testing is that construction, the singleton, and set()/delete() all address the
single global ``~/.indexed/config.toml``.
"""

import inspect
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from indexed.config import ConfigService, get_config, reload


class TestConfigServiceInit:
    """Test ConfigService initialization."""

    def test_init_with_default_workspace(self):
        """ConfigService initializes with cwd as workspace."""
        reload()
        service = ConfigService()
        assert service.workspace == Path.cwd()

    def test_init_with_custom_workspace(self):
        """ConfigService accepts custom workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            reload()
            service = ConfigService(workspace=workspace)
            assert service.workspace == workspace

    def test_singleton_pattern(self):
        """get_config() returns the cached singleton."""
        reload()
        assert get_config() is get_config()

    def test_singleton_with_reset(self):
        """reload() forces get_config() to build a fresh instance."""
        reload()
        service1 = get_config()
        reload()
        assert get_config() is not service1


class TestStorageModeIsGone:
    """workspace-profile/1 R1: the local-vs-global axis is not reachable."""

    def test_get_config_takes_no_mode_override(self):
        """The parameter is deleted, not merely ignored."""
        params = inspect.signature(get_config).parameters
        assert list(params) == ["workspace"]

        with pytest.raises(TypeError):
            get_config(mode_override="local")  # ty: ignore[unknown-argument]

    def test_config_service_takes_no_mode_override(self):
        with pytest.raises(TypeError):
            ConfigService(mode_override="local")  # ty: ignore[unknown-argument]

    @pytest.mark.parametrize(
        "attr",
        [
            "resolver",
            "workspace_manager",
            "resolve_storage_mode",
            "get_workspace_preference",
            "get_workspace_config",
        ],
    )
    def test_storage_mode_accessors_are_gone(self, attr: str):
        reload()
        assert not hasattr(ConfigService(), attr)

    def test_a_local_dot_indexed_directory_is_ignored(self, tmp_path: Path):
        """A leftover ./.indexed/config.toml no longer diverts reads or writes."""
        workspace = tmp_path / "project"
        (workspace / ".indexed").mkdir(parents=True)
        (workspace / ".indexed" / "config.toml").write_text("[core]\nleftover = true\n")

        home = tmp_path / "home"
        (home / ".indexed").mkdir(parents=True)

        with patch.object(Path, "home", return_value=home):
            reload()
            service = ConfigService(workspace=workspace)
            service.set("core.v1.search.max_docs", 5)

            assert service.get("core.leftover") is None
            assert "max_docs" in (home / ".indexed" / "config.toml").read_text()
            # The stale local file is untouched — ignored, not migrated.
            assert (
                workspace / ".indexed" / "config.toml"
            ).read_text() == "[core]\nleftover = true\n"


class TestSetDeleteWriteTarget:
    """set()/delete() read and write the same single file (R1)."""

    def test_set_then_delete_round_trips_through_the_global_config(
        self, tmp_path: Path
    ):
        home = tmp_path / "home"
        (home / ".indexed").mkdir(parents=True)
        global_config = home / ".indexed" / "config.toml"

        with patch.object(Path, "home", return_value=home):
            reload()
            service = ConfigService(workspace=tmp_path)

            service.set("core.v1.search.max_docs", 5)
            service.set("mcp.port", 9000)
            assert "max_docs" in global_config.read_text()

            assert service.delete("core.v1.search.max_docs") is True

            text = global_config.read_text()
            assert "max_docs" not in text
            # A sibling key set earlier survives the delete's full-file replace.
            assert "9000" in text
