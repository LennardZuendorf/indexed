"""TomlStore paths, atomic writes, and the .env cascade.

Rewritten for the single global store (workspace-profile/1, R1): the
local-vs-global conflict detection, ``read_for_mode``, ``get_resolved_env_path``
and the write-target cascade are all gone. The ``.env`` cascade survives as
``os.environ`` → ``~/.indexed/.env`` → ``<workspace>/.env``.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from indexed.config.store import TomlStore


class TestTomlStorePaths:
    """Test TomlStore path properties."""

    def test_global_path_is_home_indexed(self):
        """Global path should be ~/.indexed/config.toml."""
        store = TomlStore()
        assert store.global_path == Path.home() / ".indexed" / "config.toml"

    def test_resolved_config_path_is_always_the_global_config(self):
        """workspace-profile/1 R1: one write target, whatever the workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TomlStore(workspace=Path(tmpdir))
            assert store.resolved_config_path() == store.global_path

    @pytest.mark.parametrize(
        "attr",
        [
            "workspace_path",
            "_local_root",
            "_local_env_path",
            "has_local_config",
            "configs_differ",
            "get_config_differences",
            "read_for_mode",
            "read_disk_only_for_mode",
            "get_resolved_env_path",
            "write_to_global",
        ],
    )
    def test_local_mode_api_is_gone(self, attr: str):
        """workspace-profile/1 R1: no local-store surface remains on the store."""
        assert not hasattr(TomlStore(), attr)


class TestTomlStoreEnvPaths:
    """Test .env path resolution — always the global one."""

    def test_global_env_path(self):
        """_global_env_path always returns global .env."""
        store = TomlStore()
        assert store._global_env_path == Path.home() / ".indexed" / ".env"

    def test_get_env_path_is_the_global_env(self):
        """Secrets are written to ~/.indexed/.env regardless of workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TomlStore(workspace=Path(tmpdir))
            assert store.get_env_path() == str(Path.home() / ".indexed" / ".env")


class TestTomlStoreWrite:
    """Test TomlStore write functionality."""

    def test_write_targets_the_global_config_even_with_a_local_dir_present(self):
        """workspace-profile/1 R1: a stale ./.indexed no longer diverts writes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            (workspace / ".indexed").mkdir(parents=True)
            (workspace / ".indexed" / "config.toml").write_text("[stale]\n")
            home = Path(tmpdir) / "home"
            (home / ".indexed").mkdir(parents=True)

            with patch.object(Path, "home", return_value=home):
                store = TomlStore(workspace=workspace)
                store.write({"core": {"chunk_size": 512}})

                assert "chunk_size" in store.global_path.read_text()
                assert (
                    workspace / ".indexed" / "config.toml"
                ).read_text() == "[stale]\n"


class TestTomlStoreAtomicWrite:
    """B3: write() must serialize + validate BEFORE touching the target file,
    then write atomically (tmp -> fsync -> os.replace)."""

    def test_write_rejects_unserializable_value_leaves_file_untouched(self):
        """An unserializable value (e.g. None) must raise before the existing
        config.toml is opened/truncated — the file stays byte-identical."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                store = TomlStore(workspace=Path(tmpdir))

                store.write({"core": {"chunk_size": 512}})
                config_path = store.global_path
                before = config_path.read_bytes()
                assert before

                with pytest.raises(Exception):
                    store.write({"core": {"chunk_size": None}})

                after = config_path.read_bytes()
                assert after == before, "a failed write must not touch the target file"

    def test_write_leaves_no_tmp_file_on_rejection(self):
        """The tmp file created for an unserializable value must be cleaned
        up (there is nothing to clean up here since serialization happens
        before the tmp file is ever opened, but no stray .tmp may remain)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                store = TomlStore(workspace=Path(tmpdir))

                with pytest.raises(Exception):
                    store.write({"core": {"chunk_size": None}})

                config_dir = store.global_path.parent
                assert not (config_dir.exists() and any(config_dir.glob("*.tmp"))), (
                    "no .tmp artifact may remain after a rejected write"
                )

    def test_write_is_atomic_no_tmp_file_remains(self):
        """A successful write leaves no .tmp file behind."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                store = TomlStore(workspace=Path(tmpdir))
                store.write({"core": {"chunk_size": 512}})

                assert not any(store.global_path.parent.glob("*.tmp"))

    def test_write_cleans_up_tmp_on_replace_failure(self):
        """When os.replace fails mid-write, the tmp file is removed and the
        prior config.toml (if any) is left untouched."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                store = TomlStore(workspace=Path(tmpdir))

                store.write({"core": {"chunk_size": 512}})
                config_path = store.global_path
                before = config_path.read_bytes()

                with patch(
                    "indexed.config.store.os.replace", side_effect=OSError("disk full")
                ):
                    with pytest.raises(OSError, match="disk full"):
                        store.write({"core": {"chunk_size": 999}})

                assert config_path.read_bytes() == before
                assert not any(config_path.parent.glob("*.tmp"))


class TestRead:
    """Test TomlStore.read() — the one global source plus the .env cascade."""

    def test_read_returns_the_global_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            (workspace / ".indexed").mkdir(parents=True)
            (workspace / ".indexed" / "config.toml").write_text(
                '[test]\nkey = "local_value"'
            )
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "global_value"')

            with patch.object(Path, "home", return_value=global_home):
                result = TomlStore(workspace=workspace).read()

            assert result["test"]["key"] == "global_value"

    def test_read_loads_workspace_dotenv(self):
        """read() loads <workspace>/.env to fill gaps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("[test]")

            (workspace / ".env").write_text("MY_CWD_VAR=from_cwd\n")

            try:
                with patch.object(Path, "home", return_value=global_home):
                    TomlStore(workspace=workspace).read()
                assert os.environ.get("MY_CWD_VAR") == "from_cwd"
            finally:
                os.environ.pop("MY_CWD_VAR", None)

    def test_global_dotenv_overrides_workspace_dotenv(self):
        """~/.indexed/.env values take priority over <workspace>/.env values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("[test]")

            (global_dir / ".env").write_text("SHARED_VAR=from_indexed\n")
            (workspace / ".env").write_text("SHARED_VAR=from_cwd\n")
            os.environ.pop("SHARED_VAR", None)

            try:
                with patch.object(Path, "home", return_value=global_home):
                    TomlStore(workspace=workspace).read()
                # ~/.indexed/.env is loaded first, so its value wins.
                assert os.environ.get("SHARED_VAR") == "from_indexed"
            finally:
                os.environ.pop("SHARED_VAR", None)

    def test_real_env_overrides_both_dotenvs(self):
        """Real env vars already set override both .env files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text("[test]")

            (global_dir / ".env").write_text("REAL_ENV_TEST=from_indexed\n")
            (workspace / ".env").write_text("REAL_ENV_TEST=from_cwd\n")
            os.environ["REAL_ENV_TEST"] = "from_real_env"

            try:
                with patch.object(Path, "home", return_value=global_home):
                    TomlStore(workspace=workspace).read()
                # Real env var wins (override=False in load_dotenv).
                assert os.environ["REAL_ENV_TEST"] == "from_real_env"
            finally:
                os.environ.pop("REAL_ENV_TEST", None)

    def test_read_includes_schema_version(self):
        """read() injects _schema_version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                assert "_schema_version" in TomlStore(workspace=Path(tmpdir)).read()

    def test_env_vars_override_toml(self):
        """INDEXED__* env vars override TOML values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "toml_value"')

            os.environ["INDEXED__test__key"] = "env_value"
            try:
                with patch.object(Path, "home", return_value=Path(tmpdir)):
                    result = TomlStore(workspace=Path(tmpdir)).read()
                assert result["test"]["key"] == "env_value"
            finally:
                del os.environ["INDEXED__test__key"]
