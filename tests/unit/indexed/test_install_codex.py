"""Fresh-install, upgrade and removal coverage for `indexed install codex`.

Same standard as the Claude Code lifecycle suite: every assertion about
"your config is preserved" runs against a fixture that already holds foreign
content — another server, another hook group, comments a human wrote — and the
test fails when a foreign byte disappears.

Two Codex-specific properties are load-bearing here:

* ``config.toml`` is hand-edited TOML, so the installer must edit *text*, not
  re-serialise the document (``codex mcp add`` drops comments inside
  ``[mcp_servers.*]``; this command must not).
* Codex does not run an untrusted hook, so trust is host state. The installer
  reads the hash back from Codex; the tests stub that one call.
"""

import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest
import tomllib
from typer.testing import CliRunner

from indexed.cli import install_codex as codex_module

runner = CliRunner()

pytestmark = pytest.mark.unit

# A config.toml a user would not want rewritten: comments, spacing, tables and
# a foreign MCP server that must survive install, upgrade and removal.
FOREIGN_CONFIG = """\
# ============================================================
# My hand-written Codex config. Please do not reformat me.
# ============================================================

model = "gpt-6"
approval_policy = "never"

# The TUI section
[tui]
screen_reader_detection_done = true

[projects."/home/someone/secret-project"]
trust_level = "trusted"

# A pre-existing unrelated MCP server, with a comment above it
[mcp_servers.other]
command = "/bin/echo"
args = ["keep-me"]

# Trailing comment at end of file
"""

FOREIGN_HOOKS = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": 'if [ -n "$SOME_RUNNER" ]; then some-runner hook; fi',
                        "timeout": 10,
                    }
                ],
            }
        ],
        "UserPromptSubmit": [
            {
                "matcher": "",
                "hooks": [{"type": "command", "command": "keep-this.sh"}],
            }
        ],
    }
}


def _get_app():
    from indexed.cli.app import app

    return app


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def _no_ambient_codex_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """`CODEX_HOME` would move every path; tests must own the home they assert on."""
    monkeypatch.delenv("CODEX_HOME", raising=False)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at a throwaway dir for one test."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def stub_trust(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Never spawn a real Codex app-server from a unit test; record the asks."""
    calls: list[str] = []

    def _harvest(hooks_path: Path, key: str, cwd: Path, timeout: float = 20.0):
        calls.append(key)
        return "sha256:" + "ab" * 32

    monkeypatch.setattr(codex_module, "harvest_hook_hash", _harvest)
    return calls


@pytest.fixture
def seeded_home(fake_home: Path) -> Path:
    """A HOME whose Codex files already hold another tool's configuration."""
    (fake_home / ".codex").mkdir()
    (fake_home / ".codex/config.toml").write_text(FOREIGN_CONFIG, encoding="utf-8")
    (fake_home / ".codex/hooks.json").write_text(
        json.dumps(FOREIGN_HOOKS, indent=2) + "\n", encoding="utf-8"
    )
    return fake_home


def _config_text(home: Path) -> str:
    return (home / ".codex/config.toml").read_text(encoding="utf-8")


def _hooks(home: Path) -> dict:
    return json.loads((home / ".codex/hooks.json").read_text(encoding="utf-8"))


def _our_groups(hooks: dict) -> list:
    groups = hooks.get("hooks", {}).get("PreToolUse", [])
    return [group for group in groups if codex_module.hook_group_is_ours(group)]


def _assert_foreign_config_intact(home: Path) -> None:
    """Fail loudly if anything that was not ours disappeared from config.toml."""
    text = _config_text(home)
    assert "# My hand-written Codex config. Please do not reformat me." in text
    assert "# The TUI section" in text
    assert "# A pre-existing unrelated MCP server, with a comment above it" in text
    assert "# Trailing comment at end of file" in text
    config = tomllib.loads(text)
    assert config["model"] == "gpt-6"
    assert config["approval_policy"] == "never"
    assert config["tui"]["screen_reader_detection_done"] is True
    assert (
        config["projects"]["/home/someone/secret-project"]["trust_level"] == "trusted"
    )
    assert config["mcp_servers"]["other"] == {
        "command": "/bin/echo",
        "args": ["keep-me"],
    }


def _assert_foreign_hooks_intact(home: Path) -> None:
    hooks = _hooks(home)
    groups = hooks["hooks"]["PreToolUse"]
    assert FOREIGN_HOOKS["hooks"]["PreToolUse"][0] in groups, (
        "the foreign PreToolUse group was dropped or rewritten"
    )
    assert (
        hooks["hooks"]["UserPromptSubmit"] == FOREIGN_HOOKS["hooks"]["UserPromptSubmit"]
    )


class TestInstall:
    def test_registers_the_server_in_toml(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "codex"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        config = tomllib.loads(_config_text(fake_home))
        entry = config["mcp_servers"]["indexed"]
        assert entry["args"] == ["mcp", "run"]
        assert Path(entry["command"]).name == "indexed"
        assert Path(entry["command"]).is_absolute()
        assert "env" not in entry

    def test_installs_the_skill(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "codex"])

        assert result.exit_code == 0
        skill = fake_home / ".codex/skills/index-use/SKILL.md"
        assert skill.is_file()
        text = skill.read_text(encoding="utf-8")
        assert text.startswith("---\nname: index-use\n")
        # The installed copy is the shipped payload, not a paraphrase.
        assert text == codex_module.read_skill_text()
        # Codex names MCP tools mcp__<server>__<tool>, like the skill says.
        assert "mcp__indexed__search" in text

    def test_installs_an_executable_hook_script(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "codex"])

        assert result.exit_code == 0
        hook = fake_home / ".codex/indexed/indexed-nudge.sh"
        assert hook.is_file()
        assert hook.stat().st_mode & 0o100, "Codex cannot run a hook without +x"
        text = hook.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env bash")
        assert codex_module.HOOK_MARKER in text
        assert text == codex_module.installed_hook_text(None)

    def test_registers_the_hook_and_keeps_foreign_groups(self, seeded_home: Path):
        result = runner.invoke(_get_app(), ["install", "codex"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        hooks = _hooks(seeded_home)
        ours = _our_groups(hooks)
        assert len(ours) == 1, "the hook must be registered exactly once"
        assert ours[0]["matcher"] == codex_module.HOOK_MATCHER
        command = ours[0]["hooks"][0]["command"]
        assert command == str(seeded_home / ".codex/indexed/indexed-nudge.sh")
        _assert_foreign_hooks_intact(seeded_home)

    def test_preserves_every_foreign_byte_of_config_toml(self, seeded_home: Path):
        result = runner.invoke(_get_app(), ["install", "codex"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        _assert_foreign_config_intact(seeded_home)

    def test_records_the_trust_codex_computed(self, seeded_home: Path, stub_trust):
        result = runner.invoke(_get_app(), ["install", "codex"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        config = tomllib.loads(_config_text(seeded_home))
        state = config["hooks"]["state"]
        assert len(state) == 1
        key, value = next(iter(state.items()))
        # The foreign group stays first, so ours is handler group 1.
        assert key == f"{seeded_home}/.codex/hooks.json:pre_tool_use:1:0"
        assert value == {"trusted_hash": "sha256:" + "ab" * 32}
        assert stub_trust == [key]
        manifest = json.loads(
            (seeded_home / ".codex/indexed-install.json").read_text(encoding="utf-8")
        )
        assert manifest["trust_state"] == key

    def test_second_run_is_idempotent(self, seeded_home: Path):
        first = runner.invoke(_get_app(), ["install", "codex"])
        assert first.exit_code == 0
        config_bytes = (seeded_home / ".codex/config.toml").read_bytes()
        hooks_bytes = (seeded_home / ".codex/hooks.json").read_bytes()

        second = runner.invoke(_get_app(), ["install", "codex"])

        assert second.exit_code == 0
        assert (seeded_home / ".codex/config.toml").read_bytes() == config_bytes
        assert (seeded_home / ".codex/hooks.json").read_bytes() == hooks_bytes
        assert "already registered" in _strip_ansi(second.output)
        assert len(_our_groups(_hooks(seeded_home))) == 1

    def test_home_override_reaches_the_server_and_the_hook(self, fake_home: Path):
        override = fake_home / "elsewhere"

        result = runner.invoke(
            _get_app(), ["install", "codex", "--home", str(override)]
        )

        assert result.exit_code == 0, _strip_ansi(result.output)
        entry = tomllib.loads(_config_text(fake_home))["mcp_servers"]["indexed"]
        assert entry["env"] == {"HOME": str(override)}
        hook = (fake_home / ".codex/indexed/indexed-nudge.sh").read_text(
            encoding="utf-8"
        )
        assert str(override / ".indexed/data/collections") in hook
        assert codex_module.COLLECTIONS_PLACEHOLDER not in hook

    def test_dry_run_writes_nothing(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "codex", "--dry-run"])

        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "nothing was written" in output
        assert not (fake_home / ".codex").exists()

    def test_dry_run_does_not_spawn_codex(self, fake_home: Path, stub_trust):
        runner.invoke(_get_app(), ["install", "codex", "--dry-run"])

        assert stub_trust == []


class TestForeignOwnership:
    def test_refuses_to_replace_a_foreign_server_named_indexed(self, fake_home: Path):
        (fake_home / ".codex").mkdir()
        original = '[mcp_servers.indexed]\ncommand = "/old/indexed"\nargs = ["mcp"]\n'
        (fake_home / ".codex/config.toml").write_text(original, encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "codex"])

        assert result.exit_code == 1
        assert "--force" in _strip_ansi(result.output)
        assert _config_text(fake_home) == original
        assert not (fake_home / ".codex/hooks.json").exists()

    def test_force_replaces_it_and_keeps_a_backup(self, fake_home: Path):
        (fake_home / ".codex").mkdir()
        original = '[mcp_servers.indexed]\ncommand = "/old/indexed"\nargs = ["mcp"]\n'
        (fake_home / ".codex/config.toml").write_text(original, encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "codex", "--force"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        entry = tomllib.loads(_config_text(fake_home))["mcp_servers"]["indexed"]
        assert entry["args"] == ["mcp", "run"]
        backup = fake_home / ".codex/config.toml.bak"
        assert backup.read_text(encoding="utf-8") == original

    def test_refuses_to_replace_a_hand_written_hook_script(self, fake_home: Path):
        hooks_dir = fake_home / ".codex/indexed"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "indexed-nudge.sh").write_text("#!/bin/sh\necho mine\n")

        result = runner.invoke(_get_app(), ["install", "codex"])

        assert result.exit_code == 1
        assert "--force" in _strip_ansi(result.output)
        assert (hooks_dir / "indexed-nudge.sh").read_text() == "#!/bin/sh\necho mine\n"

    def test_invalid_toml_is_left_alone(self, fake_home: Path):
        (fake_home / ".codex").mkdir()
        (fake_home / ".codex/config.toml").write_text("model = [", encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "codex"])

        assert result.exit_code == 1
        assert "not valid TOML" in _strip_ansi(result.output)
        assert _config_text(fake_home) == "model = ["
        assert not (fake_home / ".codex/hooks.json").exists()

    def test_refuses_to_replace_a_hand_written_skill(self, fake_home: Path):
        skill_dir = fake_home / ".codex/skills/index-use"
        skill_dir.mkdir(parents=True)
        mine = "---\nname: my-own-index-notes\ndescription: mine\n---\n"
        (skill_dir / "SKILL.md").write_text(mine, encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "codex"])

        assert result.exit_code == 1
        assert "--force" in _strip_ansi(result.output)
        assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == mine

    def test_force_replaces_a_hand_written_skill(self, fake_home: Path):
        skill_dir = fake_home / ".codex/skills/index-use"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: mine\n---\n", encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "codex", "--force"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert text == codex_module.read_skill_text()
        assert (skill_dir / "SKILL.md.bak").is_file()


class TestUpgradeAndRemove:
    def test_upgrade_rewrites_owned_artifacts_and_keeps_foreign_config(
        self, seeded_home: Path
    ):
        runner.invoke(_get_app(), ["install", "codex"])
        hook_path = seeded_home / ".codex/indexed/indexed-nudge.sh"
        # A stale payload that lost its executable bit, as an old version left it.
        hook_path.write_text(
            "#!/usr/bin/env bash\n# indexed-install-hook v0 (stale)\n", encoding="utf-8"
        )
        hook_path.chmod(0o644)

        result = runner.invoke(_get_app(), ["install", "codex"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        assert hook_path.read_text(
            encoding="utf-8"
        ) == codex_module.installed_hook_text(None)
        assert hook_path.stat().st_mode & 0o100
        assert hook_path.with_name("indexed-nudge.sh.bak").is_file()
        _assert_foreign_config_intact(seeded_home)
        _assert_foreign_hooks_intact(seeded_home)
        assert len(_our_groups(_hooks(seeded_home))) == 1, "upgrade duplicated the hook"

    def test_remove_leaves_every_foreign_key_and_byte(self, seeded_home: Path):
        runner.invoke(_get_app(), ["install", "codex"])
        assert (seeded_home / ".codex/indexed/indexed-nudge.sh").is_file()

        result = runner.invoke(_get_app(), ["install", "codex", "--remove"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        # Owned artifacts gone.
        assert not (seeded_home / ".codex/indexed").exists()
        assert not (seeded_home / ".codex/skills/index-use").exists()
        assert not (seeded_home / ".codex/indexed-install.json").exists()
        # And the user's configuration is exactly what it was: config.toml is
        # edited as text so it comes back byte for byte; hooks.json is a JSON
        # document we merge into, so the promise there is the same content.
        assert _config_text(seeded_home) == FOREIGN_CONFIG
        assert _hooks(seeded_home) == FOREIGN_HOOKS

    def test_remove_after_a_re_run_still_restores_the_file(self, seeded_home: Path):
        """The second install must not lose what the first recorded about EOF."""
        runner.invoke(_get_app(), ["install", "codex"])
        runner.invoke(_get_app(), ["install", "codex"])

        result = runner.invoke(_get_app(), ["install", "codex", "--remove"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        assert _config_text(seeded_home) == FOREIGN_CONFIG

    def test_second_remove_is_a_no_op(self, seeded_home: Path):
        runner.invoke(_get_app(), ["install", "codex"])
        runner.invoke(_get_app(), ["install", "codex", "--remove"])
        before = (seeded_home / ".codex/config.toml").read_bytes()

        result = runner.invoke(_get_app(), ["install", "codex", "--remove"])

        assert result.exit_code == 0
        assert "nothing to remove" in _strip_ansi(result.output)
        assert (seeded_home / ".codex/config.toml").read_bytes() == before

    def test_remove_skips_a_foreign_server_registered_as_indexed(self, fake_home: Path):
        (fake_home / ".codex").mkdir()
        original = '[mcp_servers.indexed]\ncommand = "/somebody/else"\nargs = ["mcp"]\n'
        (fake_home / ".codex/config.toml").write_text(original, encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "codex", "--remove"])

        assert result.exit_code == 0
        assert _config_text(fake_home) == original

    def test_remove_deletes_a_config_it_emptied(self, fake_home: Path):
        runner.invoke(_get_app(), ["install", "codex"])
        assert (fake_home / ".codex/config.toml").is_file()

        result = runner.invoke(_get_app(), ["install", "codex", "--remove"])

        assert result.exit_code == 0
        assert not (fake_home / ".codex/config.toml").exists()
        assert not (fake_home / ".codex/hooks.json").exists()

    def test_remove_keeps_a_comment_only_config(self, fake_home: Path):
        """A file that only holds the user's notes is not ours to delete."""
        (fake_home / ".codex").mkdir()
        (fake_home / ".codex/config.toml").write_text(
            "# my personal notes\n", encoding="utf-8"
        )
        runner.invoke(_get_app(), ["install", "codex"])

        result = runner.invoke(_get_app(), ["install", "codex", "--remove"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        assert _config_text(fake_home) == "# my personal notes\n"


class TestTomlEditing:
    """The text surgery the whole lifecycle rests on, without the CLI in the way."""

    ENTRY = {"command": "/usr/bin/indexed", "args": ["mcp", "run"]}
    PATH = Path("/home/x/.codex/config.toml")

    def _merge(self, text: str, entry: dict | None = None) -> str:
        return codex_module.merge_server_block(text, entry or self.ENTRY, self.PATH)

    def _remove(self, text: str, tail: dict | None = None) -> str:
        removed = codex_module.remove_server_block(text, self.PATH)
        return codex_module._restore_tail(removed, tail)

    def test_merge_appends_and_preserves_comments(self):
        merged = self._merge(FOREIGN_CONFIG)

        assert "# The TUI section" in merged
        assert "# Trailing comment at end of file" in merged
        assert "[mcp_servers.indexed]" in merged
        assert tomllib.loads(merged)["mcp_servers"]["other"]["args"] == ["keep-me"]

    def test_merge_replaces_only_our_block(self):
        once = self._merge(FOREIGN_CONFIG)
        twice = self._merge(once, {"command": "/other/indexed", "args": ["mcp", "run"]})

        assert twice.count("[mcp_servers.indexed]") == 1
        assert "/other/indexed" in twice
        assert "/usr/bin/indexed" not in twice
        assert "# The TUI section" in twice

    def test_merge_round_trips_through_removal(self):
        tail = codex_module._tail_state(FOREIGN_CONFIG)
        merged = self._merge(FOREIGN_CONFIG)

        assert self._remove(merged, tail) == FOREIGN_CONFIG

    def test_merge_writes_the_env_sub_table(self):
        merged = self._merge(
            "",
            {
                "command": "/usr/bin/indexed",
                "args": ["mcp", "run"],
                "env": {"HOME": "/data"},
            },
        )

        assert tomllib.loads(merged)["mcp_servers"]["indexed"]["env"] == {
            "HOME": "/data"
        }

    def test_remove_on_a_missing_block_changes_nothing(self):
        assert self._remove(FOREIGN_CONFIG) == FOREIGN_CONFIG

    def test_removal_keeps_a_comment_above_the_users_next_table(self):
        """A comment below our block belongs to whatever the user wrote next."""
        merged = self._merge(FOREIGN_CONFIG)
        with_foreign = merged + (
            "\n# my own server, added after indexed\n"
            '[mcp_servers.playwright]\ncommand = "npx"\nargs = ["-y", "mcp"]\n'
        )

        removed = self._remove(with_foreign)

        assert "# my own server, added after indexed" in removed
        assert "[mcp_servers.playwright]" in removed
        assert "[mcp_servers.indexed]" not in removed
        assert "# The TUI section" in removed

    def test_header_with_an_inline_comment_ends_our_block(self):
        """`[mcp_servers.other] # keep` is still a table header (TOML allows it)."""
        merged = self._merge(FOREIGN_CONFIG)
        with_foreign = merged + (
            '\n[mcp_servers.other2]  # keep this one\ncommand = "npx"\n'
        )

        removed = self._remove(with_foreign)

        assert "[mcp_servers.other2]  # keep this one" in removed
        assert 'command = "npx"' in removed
        assert "[mcp_servers.indexed]" not in removed

    def test_array_of_tables_ends_our_block(self):
        """`[[section]]` after our block is a boundary, not part of it."""
        merged = self._merge(FOREIGN_CONFIG)
        with_foreign = merged + '\n[[skills.config]]\nname = "x"\nenabled = false\n'

        removed = self._remove(with_foreign)

        assert "[[skills.config]]" in removed
        assert 'name = "x"' in removed
        assert "[mcp_servers.indexed]" not in removed

    def test_crlf_round_trips_byte_for_byte(self):
        original = FOREIGN_CONFIG.replace("\n", "\r\n")
        tail = codex_module._tail_state(original)

        merged = self._merge(original)
        removed = self._remove(merged, tail)

        assert "\r\n" in merged and "\n" not in merged.replace("\r\n", "")
        assert removed == original

    def test_a_file_without_a_final_newline_round_trips(self):
        original = 'model = "gpt-6"'  # no trailing newline
        tail = codex_module._tail_state(original)

        merged = self._merge(original)
        removed = self._remove(merged, tail)

        assert removed == original

    def test_trailing_blank_lines_round_trip(self):
        original = 'model = "gpt-6"\n\n\n'
        tail = codex_module._tail_state(original)

        merged = self._merge(original)
        removed = self._remove(merged, tail)

        assert removed == original

    def test_a_comment_only_file_is_not_mistaken_for_empty(self):
        original = "# my personal notes\n"

        merged = self._merge(original)
        removed = self._remove(merged, codex_module._tail_state(original))

        assert removed == original

    def test_trust_block_round_trips(self):
        key = "/home/x/.codex/hooks.json:pre_tool_use:1:0"
        once = codex_module.merge_trust_block(
            FOREIGN_CONFIG, key, "sha256:abc", self.PATH
        )
        twice = codex_module.merge_trust_block(once, key, "sha256:def", self.PATH)

        assert twice.count("[hooks.state.") == 1
        assert "sha256:def" in twice
        assert tomllib.loads(twice)["hooks"]["state"][key] == {
            "trusted_hash": "sha256:def"
        }
        removed = codex_module.remove_trust_block(twice, key, self.PATH)
        removed = codex_module._restore_tail(
            removed, codex_module._tail_state(FOREIGN_CONFIG)
        )
        assert removed == FOREIGN_CONFIG

    def test_trust_block_removal_keeps_other_trust_entries(self):
        ours = "/home/x/.codex/hooks.json:pre_tool_use:1:0"
        theirs = "/home/x/.codex/hooks.json:pre_tool_use:0:0"
        text = f'[hooks.state."{theirs}"]\ntrusted_hash = "sha256:keep"\n'

        merged = codex_module.merge_trust_block(text, ours, "sha256:abc", self.PATH)
        removed = codex_module.remove_trust_block(merged, ours, self.PATH)

        assert tomllib.loads(removed)["hooks"]["state"][theirs] == {
            "trusted_hash": "sha256:keep"
        }

    def test_trust_removal_keeps_a_comment_above_the_users_next_table(self):
        key = "/home/x/.codex/hooks.json:pre_tool_use:0:0"
        text = (
            f'[hooks.state."{key}"]\ntrusted_hash = "sha256:abc"\n'
            '\n# mine\n[mcp_servers.playwright]\ncommand = "npx"\n'
        )

        removed = codex_module.remove_trust_block(text, key, self.PATH)

        assert "# mine" in removed
        assert "[mcp_servers.playwright]" in removed
        assert "hooks.state" not in removed

    def test_an_edit_that_would_drop_a_foreign_key_is_refused(self, tmp_path: Path):
        """The independent guard: if the splice loses a key, stop, never delete."""
        broken = '[mcp_servers.indexed]\ncommand = "/usr/bin/indexed"\nargs = ["mcp", "run"]\n'
        foreign = '[mcp_servers.other]\ncommand = "/bin/echo"\n'
        path = tmp_path / "config.toml"

        with pytest.raises(codex_module.CodexConfigError) as excinfo:
            codex_module._guard_foreign_keys(
                broken + foreign, broken, ["mcp_servers.indexed"], path
            )

        assert "mcp_servers.other" in excinfo.value.reason


def _run_hook(home: Path, payload: dict, env_extra: dict | None = None) -> str:
    """Execute the installed hook script the way Codex does: payload on stdin."""
    hook = home / ".codex/indexed/indexed-nudge.sh"
    env = dict(os.environ)
    env.pop("INDEXED_COLLECTIONS_HOME", None)
    env.update(env_extra or {})
    proc = subprocess.run(
        [str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


class TestHookScript:
    def _payload(self, command: str, cwd: Path) -> dict:
        return {
            "hook_event_name": "PreToolUse",
            "cwd": str(cwd),
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }

    def _home_with_collections(self, fake_home: Path) -> Path:
        runner.invoke(_get_app(), ["install", "codex"])
        (fake_home / ".indexed/data/collections/demo").mkdir(parents=True)
        return fake_home

    def test_emits_context_for_a_shell_search(self, fake_home: Path):
        home = self._home_with_collections(fake_home)

        out = _run_hook(home, self._payload("rg -n retry src/", home))

        payload = json.loads(out)["hookSpecificOutput"]
        assert payload["hookEventName"] == "PreToolUse"
        assert "mcp__indexed__search" in payload["additionalContext"]
        # A nudge must never decide the user's permissions.
        assert "permissionDecision" not in payload

    def test_is_silent_for_a_non_search_command(self, fake_home: Path):
        home = self._home_with_collections(fake_home)

        assert _run_hook(home, self._payload("pytest -q tests/unit", home)) == ""

    def test_is_silent_when_the_command_already_uses_indexed(self, fake_home: Path):
        home = self._home_with_collections(fake_home)

        payload = self._payload("indexed index search 'retry logic'", home)
        assert _run_hook(home, payload) == ""

    def test_is_silent_when_nothing_is_indexed(self, fake_home: Path):
        runner.invoke(_get_app(), ["install", "codex"])

        assert _run_hook(fake_home, self._payload("grep -rn foo .", fake_home)) == ""

    def test_is_silent_for_a_grep_like_word_inside_another_word(self, fake_home: Path):
        home = self._home_with_collections(fake_home)

        assert _run_hook(home, self._payload("cat progress.txt", home)) == ""

    def test_traces_its_firing_when_asked(self, fake_home: Path, tmp_path: Path):
        home = self._home_with_collections(fake_home)
        log = tmp_path / "hook.log"

        _run_hook(
            home,
            self._payload("grep -rn foo .", home),
            {"INDEXED_HOOK_LOG": str(log)},
        )

        assert "grep -rn foo ." in log.read_text(encoding="utf-8")

    def test_a_home_with_shell_metacharacters_stays_literal(self, fake_home: Path):
        """`--home '/tmp/$data'` must be a path, not something the hook expands."""
        weird = fake_home / "$data`cmd`(1)"
        result = runner.invoke(_get_app(), ["install", "codex", "--home", str(weird)])
        assert result.exit_code == 0, _strip_ansi(result.output)
        # The collections root this install points at, created for the hook.
        (weird / ".indexed/data/collections/demo").mkdir(parents=True)

        hook = (fake_home / ".codex/indexed/indexed-nudge.sh").read_text(
            encoding="utf-8"
        )
        assert (
            f"INDEXED_COLLECTIONS_DEFAULT={shlex.quote(str(weird / '.indexed/data/collections'))}"
            in hook
        )

        out = _run_hook(fake_home, self._payload("rg -n retry src/", fake_home))

        assert "mcp__indexed__search" in out
