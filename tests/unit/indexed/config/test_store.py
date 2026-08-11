"""TomlStore — the one global config file (workspace-profile/1, R1/R7)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from indexed.config.errors import SchemaVersionError
from indexed.config.store import (
    CURRENT_SCHEMA_VERSION,
    TomlStore,
    enforce_schema_version,
    env_to_mapping,
)


def test_toml_store_init():
    """Test TomlStore initialization."""
    store = TomlStore()
    assert store.workspace == Path.cwd()


def test_toml_store_init_custom_workspace():
    """Test TomlStore initialization with custom workspace."""
    custom_path = Path("/custom/path")
    store = TomlStore(workspace=custom_path)
    assert store.workspace == custom_path


def test_toml_store_read_toml_file_not_found():
    """Test _read_toml_file returns empty dict when file doesn't exist."""
    store = TomlStore()
    result = store._read_toml_file(Path("/nonexistent/path.toml"))
    assert result == {}


def test_toml_store_read_toml_file_no_tomllib():
    """Test _read_toml_file raises RuntimeError when tomllib not available."""
    store = TomlStore()

    # Create a file path that exists but will trigger the tomllib check
    # We need to ensure the file exists so it doesn't return early
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".toml", delete=False) as f:
        fake_path = Path(f.name)

    try:
        # Mock the module-level tomllib to be None
        import indexed.config.store

        original_tomllib = indexed.config.store.tomllib
        indexed.config.store.tomllib = None

        try:
            with pytest.raises(RuntimeError, match="tomllib/tomli not available"):
                store._read_toml_file(fake_path)
        finally:
            indexed.config.store.tomllib = original_tomllib
    finally:
        # Clean up
        if fake_path.exists():
            fake_path.unlink()


def test_env_to_mapping():
    """Test env_to_mapping converts env vars correctly."""
    env_vars = {
        "INDEXED__section__key": "value",
        "INDEXED__a__b__c": "nested",
        "NOT_INDEXED__key": "ignored",
        "INDEXED__": "ignored_empty",
    }

    with patch.dict(os.environ, env_vars, clear=False):
        result = env_to_mapping()

    assert result == {
        "section": {"key": "value"},
        "a": {"b": {"c": "nested"}},
    }


def test_env_to_mapping_empty():
    """Test env_to_mapping with no matching env vars."""
    with patch.dict(os.environ, {}, clear=True):
        assert env_to_mapping() == {}


def test_env_to_mapping_final_key_conflict_raises():
    """R15: a scalar env var must not silently clobber a nested dict.

    INDEXED__A__B builds a nested dict at "a" ({"b": ...}); a later
    INDEXED__A (scalar) assigns straight into ``out["a"]`` at the final-key
    step, which had no type-conflict guard — unlike the intermediate-segment
    step just above it — so it silently dropped "a.b". The final-key
    assignment must be guarded the same way the intermediate segments are.
    """
    env_vars = {"INDEXED__A__B": "x", "INDEXED__A": "y"}

    with patch.dict(os.environ, env_vars, clear=False):
        with pytest.raises(ValueError, match="Environment variable conflict"):
            env_to_mapping()


def test_env_to_mapping_intermediate_key_conflict_raises():
    """R15: the intermediate-segment guard fires the other way round too."""
    env_vars = {"INDEXED__Z": "y", "INDEXED__Z__B": "x"}

    with patch.dict(os.environ, env_vars, clear=False):
        with pytest.raises(ValueError, match="Environment variable conflict"):
            env_to_mapping()


def test_write_targets_the_global_config(tmp_path: Path):
    """workspace-profile/1 R1: there is one write target — ~/.indexed/config.toml."""
    with patch.object(Path, "home", return_value=tmp_path):
        store = TomlStore(workspace=tmp_path)
        store.write({"section": {"key": "value"}})

        assert store.global_path == tmp_path / ".indexed" / "config.toml"
        assert store.global_path.exists()
        assert store.read()["section"]["key"] == "value"
        assert not (tmp_path / ".indexed" / "data").exists()


def test_read_integrates_env(tmp_path: Path):
    """read() applies INDEXED__* env overrides."""
    with patch.object(Path, "home", return_value=tmp_path):
        store = TomlStore(workspace=tmp_path)
        with patch.dict(os.environ, {"INDEXED__test__value": "from_env"}, clear=False):
            result = store.read()

    assert result.get("test", {}).get("value") == "from_env"


def test_read_disk_only_ignores_env(tmp_path: Path):
    """C2: read_disk_only() must NOT merge INDEXED__* env vars — it's the
    baseline set()/delete() persist so env-supplied secrets never get baked
    into config.toml."""
    with patch.object(Path, "home", return_value=tmp_path):
        store = TomlStore(workspace=tmp_path)
        store.write({"test": {"value": "on_disk"}})

        env_vars = {
            "INDEXED__test__value": "from_env",
            "INDEXED__test__other": "secret",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            disk_only = store.read_disk_only()
            merged = store.read()

    assert disk_only["test"]["value"] == "on_disk"
    assert "other" not in disk_only["test"]
    # Sanity: the merged (env-overlaid) view DOES pick up the env value —
    # confirms disk_only is genuinely bypassing the overlay, not just broken.
    assert merged["test"]["value"] == "from_env"
    assert merged["test"]["other"] == "secret"


def test_write_stamps_the_current_schema_version(tmp_path: Path):
    """workspace-profile/1 R7: new files declare version 2."""
    with patch.object(Path, "home", return_value=tmp_path):
        store = TomlStore(workspace=tmp_path)
        store.write({"section": {"key": "value"}})

        assert 'schema_version = "2"' in store.global_path.read_text()
        assert store.read()["_schema_version"] == CURRENT_SCHEMA_VERSION


# ── Schema version enforcement (R7) ─────────────────────────────────────────


def _write_global(tmp_path: Path, body: str) -> Path:
    root = tmp_path / ".indexed"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "config.toml"
    path.write_text(body)
    return path


def test_version_two_config_loads(tmp_path: Path):
    """workspace-profile/1 R7: the current version passes."""
    _write_global(tmp_path, '[_meta]\nschema_version = "2"\n\n[core]\nx = 1\n')
    with patch.object(Path, "home", return_value=tmp_path):
        assert TomlStore(workspace=tmp_path).read()["core"]["x"] == 1


def test_clean_version_one_config_still_loads_as_version_two(tmp_path: Path):
    """workspace-profile/1 R7: a clean v1 file is accepted, treated as v2."""
    _write_global(tmp_path, '[_meta]\nschema_version = "1"\n\n[core]\nx = 1\n')
    with patch.object(Path, "home", return_value=tmp_path):
        raw = TomlStore(workspace=tmp_path).read()

    assert raw["core"]["x"] == 1
    assert raw["_schema_version"] == "2"


def test_config_with_no_meta_section_loads(tmp_path: Path):
    """workspace-profile/1 R7: an absent version behaves like version 1."""
    _write_global(tmp_path, "[core]\nx = 1\n")
    with patch.object(Path, "home", return_value=tmp_path):
        assert TomlStore(workspace=tmp_path).read()["_schema_version"] == "2"


@pytest.mark.parametrize("key", ["mode", "local_path", "global_path"])
def test_pre_collapse_config_is_rejected_naming_the_key(tmp_path: Path, key: str):
    """workspace-profile/1 R7: name the removed key and say modes are gone."""
    _write_global(
        tmp_path,
        f'[_meta]\nschema_version = "1"\n\n[workspace]\n{key} = "local"\n',
    )
    with patch.object(Path, "home", return_value=tmp_path):
        with pytest.raises(SchemaVersionError) as exc:
            TomlStore(workspace=tmp_path).read()

    message = str(exc.value)
    assert f"[workspace].{key}" in message
    assert "storage modes no longer exist" in message


def test_unrecognised_schema_version_is_rejected(tmp_path: Path):
    """workspace-profile/1 R7: an unknown version fails rather than guessing."""
    _write_global(tmp_path, '[_meta]\nschema_version = "99"\n')
    with patch.object(Path, "home", return_value=tmp_path):
        with pytest.raises(SchemaVersionError, match="unrecognised schema_version"):
            TomlStore(workspace=tmp_path).read()


def test_version_two_ignores_a_workspace_section(tmp_path: Path):
    """workspace-profile/1 R7: the removed-key check is a v1 migration aid only."""
    assert (
        enforce_schema_version(
            {"_meta": {"schema_version": "2"}, "workspace": {"collections": {}}},
            tmp_path / "indexed.config.toml",
        )
        == "2"
    )


def test_disk_only_read_enforces_the_schema_too(tmp_path: Path):
    """workspace-profile/1 R7: the set()/delete() baseline is guarded as well.

    Without this a `config set` would round-trip a rejected pre-collapse file
    straight back to disk, laundering it past the read-side check.
    """
    _write_global(
        tmp_path, '[_meta]\nschema_version = "1"\n\n[workspace]\nmode = "local"\n'
    )
    with patch.object(Path, "home", return_value=tmp_path):
        with pytest.raises(SchemaVersionError):
            TomlStore(workspace=tmp_path).read_disk_only()
