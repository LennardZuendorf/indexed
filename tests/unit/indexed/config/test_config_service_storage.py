"""Tests for ConfigService storage and workspace preferences.

Tests the workspace preference management and storage mode resolution.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from indexed.config import ConfigService, get_config, reload


class TestConfigServiceInit:
    """Test ConfigService initialization with storage options."""

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

    def test_init_with_mode_override(self):
        """ConfigService accepts mode_override."""
        reload()
        service = ConfigService(mode_override="local")
        # Mode is stored internally and affects path resolution
        assert service._mode_override == "local"

    def test_singleton_pattern(self):
        """get_config() returns the cached singleton."""
        reload()
        service1 = get_config()
        service2 = get_config()
        assert service1 is service2

    def test_singleton_with_reset(self):
        """reload() forces get_config() to build a fresh instance."""
        reload()
        service1 = get_config()
        reload()
        service2 = get_config()
        assert service1 is not service2


class TestConfigServiceProperties:
    """Test ConfigService property accessors."""

    def test_store_property(self):
        """ConfigService exposes TomlStore."""
        reload()
        service = ConfigService()
        assert service.store is not None

    def test_resolver_property(self):
        """ConfigService exposes StorageResolver."""
        reload()
        service = ConfigService()
        assert service.resolver is not None


class TestWorkspacePreferences:
    """Test workspace preference management."""

    def test_get_workspace_preference_returns_none_when_not_set(self):
        """get_workspace_preference returns None when no preference exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Mock home to avoid writing to real global config
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                reload()
                service = ConfigService(workspace=workspace)
                pref = service.get_workspace_preference()
                assert pref is None

    def test_get_workspace_config(self):
        """get_workspace_config returns workspace configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "project"
            workspace.mkdir()

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                reload()

                service = ConfigService(workspace=workspace)
                service.workspace_manager.set_preference("local")

                # Get workspace config
                config = service.get_workspace_config()

                assert config["mode"] == "local"
                assert config["local_path"] == str(workspace)
                assert config["global_path"] == "~/.indexed"

    def test_get_workspace_config_returns_empty_when_not_set(self):
        """get_workspace_config returns empty dict when no config exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "project"
            workspace.mkdir()

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                reload()

                service = ConfigService(workspace=workspace)
                config = service.get_workspace_config()

                assert config == {}


class TestStorageModeResolution:
    """Test storage mode resolution logic."""

    def test_resolve_storage_mode_defaults_to_global(self):
        """resolve_storage_mode returns 'global' by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                reload()
                service = ConfigService(workspace=workspace)
                mode = service.resolve_storage_mode()
                assert mode == "global"

    def test_resolve_storage_mode_respects_mode_override(self):
        """resolve_storage_mode returns mode_override when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                reload()
                service = ConfigService(workspace=workspace, mode_override="local")
                mode = service.resolve_storage_mode()
                assert mode == "local"

    def test_resolve_storage_mode_respects_workspace_preference(self):
        """resolve_storage_mode returns workspace preference when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                reload()
                service = ConfigService(workspace=workspace)
                service.workspace_manager.set_preference("local")

                mode = service.resolve_storage_mode()
                assert mode == "local"


class TestSetDeleteWriteTargetConsistency:
    """R1: set()/delete() must never let the write target diverge from the
    baseline read target.

    ``set_preference("local")`` persists ``[workspace] mode = "local"`` into
    the GLOBAL config.toml only — it never creates a local config.toml. The
    baseline read (``ConfigService._disk_baseline``) honors that stored
    preference and resolves "local". Before the fix, the write target
    (``TomlStore._resolve_write_target``) hardcoded
    ``workspace_preference=None`` and resolved "global" instead (no local
    config.toml exists yet, so the auto-detect cascade fell through to
    "global") — so ``TomlStore.write``'s full-file replace clobbered the
    global config.toml, destroying ``[workspace]`` and every other global
    key.
    """

    def test_set_with_local_preference_writes_local_not_global(self):
        """set() must target local config.toml and must not wipe [workspace]."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                reload()
                service = ConfigService(workspace=workspace)
                service.workspace_manager.set_preference("local")

                local_config = workspace / ".indexed" / "config.toml"
                global_config = global_dir / "config.toml"

                # Preconditions: no local config.toml yet, and the preference
                # really did land in the global file (per set_preference's
                # documented behavior).
                assert not local_config.exists()
                assert 'mode = "local"' in global_config.read_text()

                service.set("core.v1.search.max_docs", 5)

                # (a) the local config.toml now exists and holds the new key.
                assert local_config.exists()
                assert "max_docs" in local_config.read_text()

                # (b) the global config.toml still has [workspace] mode="local"
                # — set() must not have replaced it with just the new key.
                global_text = global_config.read_text()
                assert "[workspace]" in global_text
                assert 'mode = "local"' in global_text

    def test_delete_with_global_preference_targets_global_not_local(self):
        """delete() must honor an explicit "global" preference even when a
        local config.toml also happens to exist (which would otherwise win
        the write-side auto-detect fallback and mistarget the write).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("")

            with patch.object(Path, "home", return_value=global_home):
                reload()
                service = ConfigService(workspace=workspace)

                # Seed the key to delete into the GLOBAL file, and an
                # unrelated marker into a LOCAL file that merely exists on
                # disk (enough to win the write-side auto-detect fallback if
                # the preference is ignored) — BEFORE setting the preference,
                # since TomlStore.write() is a full-file replace: seeding
                # after set_preference() would itself wipe [workspace].
                from indexed.config.store import TomlStore

                TomlStore(workspace=workspace, mode_override="global").write(
                    {"core": {"v1": {"search": {"max_docs": 5}}}}
                )
                TomlStore(workspace=workspace, mode_override="local").write(
                    {"local_marker": "keep me"}
                )

                # set_preference() itself read-merges onto the existing
                # global disk content, so the "core" key seeded above
                # survives this call.
                service.workspace_manager.set_preference("global")

                local_config = workspace / ".indexed" / "config.toml"
                global_config = global_dir / "config.toml"

                changed = service.delete("core.v1.search.max_docs")
                assert changed is True

                # (a) the key is actually gone from the global file (its
                # true home per the stored preference) — not left behind
                # because delete() mistargeted the write elsewhere.
                assert "max_docs" not in global_config.read_text()

                # (b) the local file's own content survived — delete() must
                # not have full-file-replaced it with the global baseline.
                assert "local_marker" in local_config.read_text()

                global_text = global_config.read_text()
                assert "[workspace]" in global_text
                assert 'mode = "global"' in global_text
