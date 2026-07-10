"""Tests for EnvFileWriter (C4: dotenv-safe quoting)."""

from pathlib import Path

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


class TestIsSensitiveField:
    def test_detects_sensitive_names(self):
        assert EnvFileWriter.is_sensitive_field("api_token") is True
        assert EnvFileWriter.is_sensitive_field("password") is True

    def test_non_sensitive_name(self):
        assert EnvFileWriter.is_sensitive_field("url") is False
