"""Tests for the `indexed install claude-code` CLI command."""

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indexed.cli import install as install_module

runner = CliRunner()


def _get_app():
    from indexed.cli.app import app

    return app


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at a throwaway dir for one test.

    The session-wide autouse fixture in ``tests/conftest.py`` already replaces
    ``Path.home``, so a ``HOME`` env var alone would not move ``~/.claude.json``
    — re-patch the method on top of it (function-scoped, auto-reverted).
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


class TestInstallCommandHelp:
    def test_appears_in_help(self):
        result = runner.invoke(_get_app(), ["--help"])
        assert result.exit_code == 0
        assert "install claude-code" in _strip_ansi(result.output)

    def test_has_own_help(self):
        result = runner.invoke(_get_app(), ["install", "claude-code", "--help"])
        assert result.exit_code == 0
        clean = _strip_ansi(result.output)
        assert "--dry-run" in clean
        assert "--home" in clean


class TestClaudeCodeInstall:
    def test_dry_run_writes_nothing(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "claude-code", "--dry-run"])

        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "Server (indexed)" in output
        assert "nothing was written" in output
        assert not (fake_home / ".claude.json").exists()
        assert not (fake_home / ".claude").exists()

    def test_dry_run_never_prints_the_rest_of_the_users_config(self, fake_home: Path):
        """--dry-run is a preview of the *change*, not a dump of the user's file.

        ~/.claude.json holds an oauth account block and per-project history; echoing
        the merged document to a terminal (or a CI log) leaks both.
        """
        (fake_home / ".claude.json").write_text(
            json.dumps(
                {
                    "oauthAccount": {"emailAddress": "secret@example.test"},
                    "projects": {
                        "/home/secret-project": {"history": ["private prompt"]}
                    },
                    "mcpServers": {"other": {"command": "keep-me"}},
                }
            )
        )

        result = runner.invoke(_get_app(), ["install", "claude-code", "--dry-run"])

        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "secret@example.test" not in output
        assert "private prompt" not in output
        assert "keep-me" not in output
        assert "Server (indexed)" in output
        # and nothing was written
        assert json.loads((fake_home / ".claude.json").read_text())["mcpServers"] == {
            "other": {"command": "keep-me"}
        }

    def test_registers_mcp_server(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 0
        config = json.loads((fake_home / ".claude.json").read_text())
        entry = config["mcpServers"]["indexed"]
        assert entry["type"] == "stdio"
        assert entry["args"] == ["mcp", "run"]
        assert Path(entry["command"]).is_absolute()
        assert "env" not in entry

    def test_refuses_to_replace_a_different_existing_entry(self, fake_home: Path):
        """A different mcpServers.indexed is someone else's config, not ours to clobber."""
        config_path = fake_home / ".claude.json"
        original = {
            "mcpServers": {"indexed": {"command": "/old/indexed", "args": ["mcp"]}}
        }
        config_path.write_text(json.dumps(original))

        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 1
        assert "--force" in _strip_ansi(result.output)
        assert json.loads(config_path.read_text()) == original
        assert not (fake_home / ".claude").exists()

    def test_force_replaces_the_entry_and_keeps_a_backup(self, fake_home: Path):
        config_path = fake_home / ".claude.json"
        original = {
            "mcpServers": {"indexed": {"command": "/old/indexed", "args": ["mcp"]}}
        }
        config_path.write_text(json.dumps(original))

        result = runner.invoke(_get_app(), ["install", "claude-code", "--force"])

        assert result.exit_code == 0
        entry = json.loads(config_path.read_text())["mcpServers"]["indexed"]
        assert entry["args"] == ["mcp", "run"]
        backup = config_path.with_name(config_path.name + ".bak")
        assert backup.is_file()
        assert json.loads(backup.read_text()) == original

    def test_installs_index_use_skill(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 0
        skill = fake_home / ".claude/skills/index-use/SKILL.md"
        assert skill.is_file()
        text = skill.read_text(encoding="utf-8")
        assert text.startswith("---\nname: index-use\n")
        # The installed copy is the shipped payload, not a paraphrase.
        assert text == install_module.read_skill_text()
        assert "indexed.search/1" in text

    def test_second_run_is_idempotent(self, fake_home: Path):
        first = runner.invoke(_get_app(), ["install", "claude-code"])
        assert first.exit_code == 0
        config_path = fake_home / ".claude.json"
        skill_path = fake_home / ".claude/skills/index-use/SKILL.md"
        config_bytes = config_path.read_bytes()
        skill_bytes = skill_path.read_bytes()

        second = runner.invoke(_get_app(), ["install", "claude-code"])

        assert second.exit_code == 0
        assert config_path.read_bytes() == config_bytes
        assert skill_path.read_bytes() == skill_bytes
        assert json.loads(config_path.read_text())["mcpServers"].keys() == {"indexed"}
        assert "already registered" in _strip_ansi(second.output)

    def test_preserves_unrelated_config(self, fake_home: Path):
        config_path = fake_home / ".claude.json"
        config_path.write_text(
            json.dumps(
                {
                    "numStartups": 7,
                    "oauthAccount": {"emailAddress": "someone@example.com"},
                    "mcpServers": {"other": {"type": "stdio", "command": "other"}},
                }
            )
        )

        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 0
        config = json.loads(config_path.read_text())
        assert config["numStartups"] == 7
        assert config["oauthAccount"]["emailAddress"] == "someone@example.com"
        assert config["mcpServers"]["other"] == {"type": "stdio", "command": "other"}
        assert config["mcpServers"]["indexed"]["args"] == ["mcp", "run"]

    def test_home_override_is_carried_to_the_server(self, fake_home: Path):
        override = fake_home / "elsewhere"

        result = runner.invoke(
            _get_app(),
            ["install", "claude-code", "--home", str(override)],
        )

        assert result.exit_code == 0
        config = json.loads((fake_home / ".claude.json").read_text())
        entry = config["mcpServers"]["indexed"]
        assert entry["env"] == {"HOME": str(override)}

    def test_invalid_existing_config_is_left_alone(self, fake_home: Path):
        config_path = fake_home / ".claude.json"
        config_path.write_text("{not json")

        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 1
        assert "not valid JSON" in _strip_ansi(result.output)
        assert config_path.read_text() == "{not json"
        assert not (fake_home / ".claude").exists()

    def test_missing_skill_payload_is_an_actionable_error(
        self, fake_home: Path, monkeypatch: pytest.MonkeyPatch
    ):
        def _missing():
            raise FileNotFoundError("index-use skill not found anywhere")

        monkeypatch.setattr(install_module, "read_skill_text", _missing)

        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 1
        assert "index-use skill not found" in _strip_ansi(result.output)
        assert not (fake_home / ".claude.json").exists()
