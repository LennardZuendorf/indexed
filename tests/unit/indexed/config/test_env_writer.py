"""Tests for EnvFileWriter (C4: dotenv-safe quoting)."""

import os
import stat
from pathlib import Path
from unittest import mock

from dotenv import dotenv_values

from indexed.config.env_writer import EnvFileWriter, _dotenv_quote


class TestDotenvQuote:
    def test_quotes_plain_value(self):
        assert _dotenv_quote("hello") == '"hello"'

    def test_escapes_double_quote(self):
        assert _dotenv_quote('a"b') == '"a\\"b"'

    def test_escapes_backslash(self):
        assert _dotenv_quote("a\\b") == '"a\\\\b"'


class TestEnvFileWriterWrite:
    def test_write_new_key_round_trips_hash_and_space(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        secret = "abc #x def"

        EnvFileWriter(lambda: str(env_path)).write("JIRA_TOKEN", secret)

        assert dotenv_values(str(env_path)).get("JIRA_TOKEN") == secret

    def test_write_round_trips_embedded_quote(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        secret = 'has "quotes" inside'

        EnvFileWriter(lambda: str(env_path)).write("JIRA_TOKEN", secret)

        assert dotenv_values(str(env_path)).get("JIRA_TOKEN") == secret

    def test_write_updates_existing_key_in_place(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        writer = EnvFileWriter(lambda: str(env_path))

        writer.write("OTHER_KEY", "keep me")
        writer.write("JIRA_TOKEN", "first #value")
        writer.write("JIRA_TOKEN", "second #value")

        values = dotenv_values(str(env_path))
        assert values.get("JIRA_TOKEN") == "second #value"
        assert values.get("OTHER_KEY") == "keep me"
        # Updated in place, not duplicated.
        assert env_path.read_text().count("JIRA_TOKEN=") == 1

    def test_write_creates_parent_directory(self, tmp_path: Path):
        env_path = tmp_path / "nested" / ".env"
        EnvFileWriter(lambda: str(env_path)).write("KEY", "value")

        assert env_path.exists()
        assert dotenv_values(str(env_path)).get("KEY") == "value"

    def test_write_updates_existing_export_key_in_place(self, tmp_path: Path):
        """Test that export-prefixed keys are updated in place, not duplicated."""
        env_path = tmp_path / ".env"
        # Seed with an export-prefixed key
        env_path.write_text("export JIRA_TOKEN=old_secret\n")

        writer = EnvFileWriter(lambda: str(env_path))
        writer.write("JIRA_TOKEN", "new_secret")

        # Should have exactly one JIRA_TOKEN entry (updated in place)
        text = env_path.read_text()
        assert text.count("JIRA_TOKEN") == 1
        # Verify the new value is present and correctly quoted
        values = dotenv_values(str(env_path))
        assert values.get("JIRA_TOKEN") == "new_secret"

    def test_write_is_atomic_on_failure(self, tmp_path: Path):
        """Test that a crash during write doesn't truncate the original file."""
        env_path = tmp_path / ".env"
        original_content = "OTHER_KEY=keep_me\n"
        env_path.write_text(original_content)

        writer = EnvFileWriter(lambda: str(env_path))

        # Mock os.replace to simulate a crash mid-write
        with mock.patch("os.replace", side_effect=RuntimeError("Simulated crash")):
            try:
                writer.write("JIRA_TOKEN", "new_value")
            except RuntimeError:
                pass  # Expected

        # Original file should be intact, not truncated/empty
        text = env_path.read_text()
        assert text == original_content
        assert "OTHER_KEY" in text
        assert "JIRA_TOKEN" not in text

    def test_write_is_atomic_on_mid_write_failure(self, tmp_path: Path):
        """A crash while writing the temp file must not touch the original
        .env or leave a leftover temp file behind."""
        env_path = tmp_path / ".env"
        original_content = "OTHER_KEY=keep_me\n"
        env_path.write_text(original_content)

        writer = EnvFileWriter(lambda: str(env_path))

        # Inject the failure inside the temp-write block itself (not just at
        # os.replace) to exercise the actually-vulnerable window.
        with mock.patch("os.fsync", side_effect=RuntimeError("Simulated crash")):
            try:
                writer.write("JIRA_TOKEN", "new_value")
            except RuntimeError:
                pass  # Expected

        # Original file survives byte-for-byte.
        text = env_path.read_text()
        assert text == original_content
        assert "OTHER_KEY" in text
        assert "JIRA_TOKEN" not in text

        # No leftover temp file.
        leftovers = list(tmp_path.glob(".env*.tmp")) + list(tmp_path.glob(".env.tmp"))
        assert leftovers == []

    def test_write_preserves_0600_permissions(self, tmp_path: Path):
        """A pre-existing .env at 0600 stays 0600 after write()."""
        env_path = tmp_path / ".env"
        env_path.write_text("OTHER_KEY=keep_me\n")
        os.chmod(env_path, 0o600)

        EnvFileWriter(lambda: str(env_path)).write("JIRA_TOKEN", "secret")

        mode = stat.S_IMODE(os.stat(env_path).st_mode)
        assert mode == 0o600

    def test_write_hardens_0644_permissions_to_0600(self, tmp_path: Path):
        """A pre-existing .env at 0644 is HARDENED to 0600 after write()."""
        env_path = tmp_path / ".env"
        env_path.write_text("OTHER_KEY=keep_me\n")
        os.chmod(env_path, 0o644)

        EnvFileWriter(lambda: str(env_path)).write("JIRA_TOKEN", "secret")

        mode = stat.S_IMODE(os.stat(env_path).st_mode)
        assert mode == 0o600

    def test_write_creates_new_env_at_0600(self, tmp_path: Path):
        """A first-ever-created .env (no prior file) is 0600."""
        env_path = tmp_path / ".env"
        assert not env_path.exists()

        EnvFileWriter(lambda: str(env_path)).write("JIRA_TOKEN", "secret")

        mode = stat.S_IMODE(os.stat(env_path).st_mode)
        assert mode == 0o600

    def test_tmp_file_is_never_group_or_world_readable(
        self, tmp_path: Path, monkeypatch
    ):
        """The secrets must not sit at umask perms mid-write.

        Snapshots the temp file's mode at fsync — while the secrets are on
        disk and the file is still open — so a chmod-after-write regression
        (readable to other local users for the duration) fails here.
        """
        env_path = tmp_path / ".env"
        seen: dict[str, int] = {}
        real_fsync = os.fsync

        def spy(fd):
            tmp = str(env_path) + ".tmp"
            if os.path.exists(tmp):
                seen["mode"] = stat.S_IMODE(os.stat(tmp).st_mode)
            return real_fsync(fd)

        monkeypatch.setattr(os, "fsync", spy)
        monkeypatch.setattr(os, "umask", lambda _: 0)

        EnvFileWriter(lambda: str(env_path)).write("JIRA_TOKEN", "secret")

        assert seen["mode"] == 0o600
        assert not seen["mode"] & (stat.S_IRGRP | stat.S_IROTH)


class TestIsSensitiveField:
    def test_detects_sensitive_names(self):
        assert EnvFileWriter.is_sensitive_field("api_token") is True
        assert EnvFileWriter.is_sensitive_field("password") is True

    def test_non_sensitive_name(self):
        assert EnvFileWriter.is_sensitive_field("url") is False
