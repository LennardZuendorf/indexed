"""Hook, upgrade and removal coverage for `indexed install claude-code`.

The install/remove cycle is the part a user cannot check by reading the diff:
they run the command, restart Claude Code, and either their own settings survive
or they do not. Every test below asserts on a *fixture config that already holds
foreign keys* — another MCP server, another PreToolUse hook, unrelated settings —
because "we preserved your config" is only a claim until something fails when a
foreign key disappears.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indexed.cli import install as install_module

runner = CliRunner()

pytestmark = pytest.mark.unit

# Present in both user files before any install, and asserted after every
# install, upgrade and removal below.
FOREIGN_SETTINGS = {
    "model": "opus",
    "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Read(./.env)"]},
    "enabledPlugins": {"superpowers@claude-plugins-official": True},
    "hooks": {
        "UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "user-prompt-hook.sh"}]}
        ],
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "bash-guard.sh"}],
            }
        ],
    },
}
FOREIGN_MCP = {
    "numStartups": 7,
    "oauthAccount": {"emailAddress": "someone@example.com"},
    "mcpServers": {
        "other": {"type": "stdio", "command": "other-server", "args": ["serve"]}
    },
}


def _get_app():
    from indexed.cli.app import app

    return app


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at a throwaway dir for one test."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def seeded_home(fake_home: Path) -> Path:
    """A HOME whose Claude files already hold another tool's configuration."""
    (fake_home / ".claude.json").write_text(json.dumps(FOREIGN_MCP), encoding="utf-8")
    settings_dir = fake_home / ".claude"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(
        json.dumps(FOREIGN_SETTINGS), encoding="utf-8"
    )
    return fake_home


def _settings(home: Path) -> dict:
    return json.loads((home / ".claude/settings.json").read_text(encoding="utf-8"))


def _config(home: Path) -> dict:
    return json.loads((home / ".claude.json").read_text(encoding="utf-8"))


def _our_groups(settings: dict) -> list:
    groups = settings.get("hooks", {}).get("PreToolUse", [])
    return [
        group
        for group in groups
        if install_module.HOOK_SCRIPT_NAME in json.dumps(group)
    ]


def _assert_foreign_settings_intact(home: Path) -> None:
    """Fail loudly, key by key, if anything that was not ours disappeared."""
    settings = _settings(home)
    assert settings["model"] == FOREIGN_SETTINGS["model"]
    assert settings["permissions"] == FOREIGN_SETTINGS["permissions"]
    assert settings["enabledPlugins"] == FOREIGN_SETTINGS["enabledPlugins"]
    assert (
        settings["hooks"]["UserPromptSubmit"]
        == FOREIGN_SETTINGS["hooks"]["UserPromptSubmit"]
    )
    assert (
        settings["hooks"]["PreToolUse"][0] == FOREIGN_SETTINGS["hooks"]["PreToolUse"][0]
    ), "the foreign PreToolUse group was dropped or reordered"


def _assert_foreign_mcp_intact(home: Path) -> None:
    config = _config(home)
    assert config["numStartups"] == FOREIGN_MCP["numStartups"]
    assert config["oauthAccount"] == FOREIGN_MCP["oauthAccount"]
    assert config["mcpServers"]["other"] == FOREIGN_MCP["mcpServers"]["other"]


class TestHookInstall:
    def test_installs_an_executable_hook_script(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 0
        hook = fake_home / f".claude/hooks/{install_module.HOOK_SCRIPT_NAME}"
        assert hook.is_file()
        assert hook.stat().st_mode & 0o100, "Claude Code cannot run a hook without +x"
        text = hook.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env bash")
        assert install_module.HOOK_MARKER in text
        # The installed copy is the shipped payload with this install's
        # collections root baked in, not a paraphrase.
        assert text == install_module.installed_hook_text(None)

    def test_registers_the_hook_in_settings(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 0
        settings = _settings(fake_home)
        groups = _our_groups(settings)
        assert len(groups) == 1
        hook_path = fake_home / f".claude/hooks/{install_module.HOOK_SCRIPT_NAME}"
        assert groups[0]["matcher"] == "Grep|Glob"
        assert groups[0]["hooks"][0]["type"] == "command"
        assert Path(groups[0]["hooks"][0]["command"]) == hook_path

    def test_installing_reports_the_hook(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "claude-code"])

        output = _strip_ansi(result.output)
        assert "Installed the PreToolUse search hook" in output
        assert "Hook" in output

    def test_preserves_foreign_settings(self, seeded_home: Path):
        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 0
        _assert_foreign_settings_intact(seeded_home)
        _assert_foreign_mcp_intact(seeded_home)
        # and ours landed alongside them
        assert len(_our_groups(_settings(seeded_home))) == 1

    def test_refuses_to_write_into_an_invalid_settings_file(self, fake_home: Path):
        (fake_home / ".claude").mkdir()
        (fake_home / ".claude/settings.json").write_text("{not json", encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 1
        assert "not valid JSON" in _strip_ansi(result.output)
        assert (fake_home / ".claude/settings.json").read_text() == "{not json"
        assert not (fake_home / ".claude/hooks").exists()

    def test_dry_run_writes_no_hook(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "claude-code", "--dry-run"])

        assert result.exit_code == 0
        clean = _strip_ansi(result.output)
        assert "Hook script" in clean
        assert not (fake_home / ".claude").exists()


class TestInstalledHookBehaviour:
    """Run the installed script the way Claude Code does: stdin JSON, stdout JSON."""

    def _run_hook(self, home: Path, payload: dict, project: Path) -> str:
        hook = home / f".claude/hooks/{install_module.HOOK_SCRIPT_NAME}"
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home),
            "CLAUDE_PROJECT_DIR": str(project),
        }
        completed = subprocess.run(
            [str(hook)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        return completed.stdout

    def _indexed_home(self, home: Path) -> None:
        """Give the sandbox HOME one collection in the global store."""
        (home / ".indexed/data/collections/demo-repo").mkdir(parents=True)

    def test_nudges_when_the_global_store_has_collections(
        self, fake_home: Path, tmp_path: Path
    ):
        runner.invoke(_get_app(), ["install", "claude-code"])
        self._indexed_home(fake_home)
        project = tmp_path / "project"
        project.mkdir()

        stdout = self._run_hook(
            fake_home,
            {"tool_name": "Grep", "tool_input": {"pattern": "retry logic"}},
            project,
        )

        payload = json.loads(stdout)  # the hook's stdout must stay valid JSON
        output = payload["hookSpecificOutput"]
        assert output["hookEventName"] == "PreToolUse"
        # Context only: the hook must never decide permissions for a user-scope
        # tool, or every Grep/Glob (including one outside the project) is
        # auto-approved.
        assert "permissionDecision" not in output
        assert "mcp__indexed__search" in output["additionalContext"]
        assert "Grep" in output["additionalContext"]

    def test_nudges_when_the_workspace_has_a_pointer(
        self, fake_home: Path, tmp_path: Path
    ):
        """`indexed storage migrate` points a workspace at a shared root."""
        runner.invoke(_get_app(), ["install", "claude-code"])
        project = tmp_path / "project"
        (project / ".indexed").mkdir(parents=True)
        (project / ".indexed/collections.json").write_text("{}", encoding="utf-8")

        stdout = self._run_hook(fake_home, {"tool_name": "Glob"}, project)

        output = json.loads(stdout)["hookSpecificOutput"]
        assert "mcp__indexed__search" in output["additionalContext"]

    def test_silent_when_nothing_is_indexed(self, fake_home: Path, tmp_path: Path):
        runner.invoke(_get_app(), ["install", "claude-code"])
        project = tmp_path / "plain-repo"
        project.mkdir()

        stdout = self._run_hook(fake_home, {"tool_name": "Glob"}, project)

        assert stdout.strip() == "", (
            "the hook must cost nothing when nothing is indexed"
        )

    def test_jq_absent_still_emits_valid_json(self, fake_home: Path, tmp_path: Path):
        """Claude Code users do not all have jq; the fallback must stay parseable."""
        runner.invoke(_get_app(), ["install", "claude-code"])
        self._indexed_home(fake_home)
        project = tmp_path / "project"
        project.mkdir()
        hook = fake_home / f".claude/hooks/{install_module.HOOK_SCRIPT_NAME}"
        # A PATH with everything the hook legitimately needs and no jq.
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for tool in ("cat", "date", "bash"):
            resolved = shutil.which(tool)
            assert resolved is not None
            (bin_dir / tool).symlink_to(resolved)

        completed = subprocess.run(
            [str(hook)],
            input='{"tool_name": "Grep"}',
            capture_output=True,
            text=True,
            env={
                "PATH": str(bin_dir),
                "HOME": str(fake_home),
                "CLAUDE_PROJECT_DIR": str(project),
            },
            timeout=30,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
        output = json.loads(completed.stdout)["hookSpecificOutput"]
        assert "mcp__indexed__search" in output["additionalContext"]


class TestUpgrade:
    def test_second_run_writes_nothing(self, fake_home: Path):
        assert runner.invoke(_get_app(), ["install", "claude-code"]).exit_code == 0
        paths = [
            fake_home / ".claude.json",
            fake_home / ".claude/settings.json",
            fake_home / f".claude/hooks/{install_module.HOOK_SCRIPT_NAME}",
            fake_home / ".claude/skills/index-use/SKILL.md",
            fake_home / ".claude/indexed-install.json",
        ]
        before = {path: path.read_bytes() for path in paths}

        second = runner.invoke(_get_app(), ["install", "claude-code"])

        assert second.exit_code == 0
        for path, content in before.items():
            assert path.read_bytes() == content, f"{path.name} churned on a re-run"

    def test_upgrade_replaces_owned_payloads_and_keeps_foreign_keys(
        self, seeded_home: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A new release rewrites what it owns; everything else is untouched."""
        assert runner.invoke(_get_app(), ["install", "claude-code"]).exit_code == 0
        _assert_foreign_settings_intact(seeded_home)

        monkeypatch.setattr(
            install_module, "read_hook_text", lambda: "#!/usr/bin/env bash\n# v2\n"
        )
        monkeypatch.setattr(
            install_module, "read_skill_text", lambda: "---\nname: index-use\n# v2\n"
        )
        monkeypatch.setattr(install_module, "installed_version", lambda: "9.9.9")

        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 0
        hook = seeded_home / f".claude/hooks/{install_module.HOOK_SCRIPT_NAME}"
        assert "# v2" in hook.read_text(encoding="utf-8")
        # A rewritten script keeps its executable bit.
        assert hook.stat().st_mode & 0o100
        assert hook.with_name(hook.name + ".bak").is_file()
        assert "v2" in (seeded_home / ".claude/skills/index-use/SKILL.md").read_text()
        manifest = json.loads(
            (seeded_home / ".claude/indexed-install.json").read_text(encoding="utf-8")
        )
        assert manifest["package_version"] == "9.9.9"
        _assert_foreign_settings_intact(seeded_home)
        _assert_foreign_mcp_intact(seeded_home)
        assert len(_our_groups(_settings(seeded_home))) == 1, (
            "upgrade duplicated the hook"
        )


class TestRemoval:
    def test_remove_deletes_owned_artifacts_and_keeps_foreign_config(
        self, seeded_home: Path
    ):
        assert runner.invoke(_get_app(), ["install", "claude-code"]).exit_code == 0

        result = runner.invoke(_get_app(), ["install", "claude-code", "--remove"])

        assert result.exit_code == 0
        # ours are gone
        assert "indexed" not in _config(seeded_home)["mcpServers"]
        assert _our_groups(_settings(seeded_home)) == []
        assert not (
            seeded_home / f".claude/hooks/{install_module.HOOK_SCRIPT_NAME}"
        ).exists()
        assert not (seeded_home / ".claude/skills/index-use").exists()
        assert not (seeded_home / ".claude/indexed-install.json").exists()
        # theirs survived, key by key
        _assert_foreign_mcp_intact(seeded_home)
        _assert_foreign_settings_intact(seeded_home)

    def test_remove_deletes_files_that_held_only_our_configuration(
        self, fake_home: Path
    ):
        assert runner.invoke(_get_app(), ["install", "claude-code"]).exit_code == 0

        assert (
            runner.invoke(_get_app(), ["install", "claude-code", "--remove"]).exit_code
            == 0
        )

        assert not (fake_home / ".claude.json").exists()
        assert not (fake_home / ".claude/settings.json").exists()
        # the directories we created are pruned too
        assert not (fake_home / ".claude/hooks").exists()
        assert not (fake_home / ".claude/skills/index-use").exists()

    def test_remove_is_idempotent(self, fake_home: Path):
        runner.invoke(_get_app(), ["install", "claude-code"])
        assert (
            runner.invoke(_get_app(), ["install", "claude-code", "--remove"]).exit_code
            == 0
        )

        second = runner.invoke(_get_app(), ["install", "claude-code", "--remove"])

        assert second.exit_code == 0
        assert "nothing to remove" in _strip_ansi(second.output)

    def test_remove_on_a_clean_home_says_so(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "claude-code", "--remove"])

        assert result.exit_code == 0
        assert "nothing to remove" in _strip_ansi(result.output)
        assert not (fake_home / ".claude.json").exists()
        assert not (fake_home / ".claude").exists()

    def test_remove_keeps_an_indexed_server_it_did_not_install(self, fake_home: Path):
        """`mcpServers.indexed` pointing somewhere else is someone else's, even now."""
        config_path = fake_home / ".claude.json"
        original = {"mcpServers": {"indexed": {"command": "/usr/local/bin/my-indexed"}}}
        config_path.write_text(json.dumps(original), encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "claude-code", "--remove"])

        assert result.exit_code == 0
        assert (
            json.loads(config_path.read_text())["mcpServers"] == original["mcpServers"]
        )
        assert "not ours" in _strip_ansi(result.output)

    def test_remove_keeps_a_hook_file_it_did_not_install(self, fake_home: Path):
        hook = fake_home / f".claude/hooks/{install_module.HOOK_SCRIPT_NAME}"
        hook.parent.mkdir(parents=True)
        hook.write_text("#!/bin/sh\necho hand-written\n", encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "claude-code", "--remove"])

        assert result.exit_code == 0
        assert hook.read_text() == "#!/bin/sh\necho hand-written\n"

    def test_remove_dry_run_changes_nothing(self, seeded_home: Path):
        assert runner.invoke(_get_app(), ["install", "claude-code"]).exit_code == 0
        before = (seeded_home / ".claude.json").read_bytes()

        result = runner.invoke(
            _get_app(), ["install", "claude-code", "--remove", "--dry-run"]
        )

        assert result.exit_code == 0
        assert "nothing was written" in _strip_ansi(result.output)
        assert (seeded_home / ".claude.json").read_bytes() == before
        assert (seeded_home / ".claude/settings.json").is_file()

    def test_remove_keeps_a_skill_it_did_not_install(self, fake_home: Path):
        skill = fake_home / ".claude/skills/index-use/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: something-else\n---\n", encoding="utf-8")

        runner.invoke(_get_app(), ["install", "claude-code", "--remove"])

        assert skill.is_file()

    def test_remove_keeps_a_skill_whose_name_only_starts_the_same(
        self, fake_home: Path
    ):
        """`index-use-custom` is a different skill, not a prefix of ours."""
        skill = fake_home / ".claude/skills/index-use/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: index-use-custom\n---\n", encoding="utf-8")

        runner.invoke(_get_app(), ["install", "claude-code", "--remove"])

        assert skill.is_file(), "a substring match deleted someone else's skill"

    def test_remove_keeps_a_server_that_merely_ends_in_indexed(self, fake_home: Path):
        """`my-indexed mcp run` is a different program with the same tail."""
        config_path = fake_home / ".claude.json"
        original = {
            "mcpServers": {
                "indexed": {
                    "type": "stdio",
                    "command": "/usr/local/bin/my-indexed",
                    "args": ["mcp", "run"],
                }
            }
        }
        config_path.write_text(json.dumps(original), encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "claude-code", "--remove"])

        assert result.exit_code == 0
        assert (
            json.loads(config_path.read_text())["mcpServers"]
            == (original["mcpServers"])
        )

    def test_remove_cleans_up_the_python_module_fallback(self, fake_home: Path):
        """`resolve_cli_command` can register `python -m indexed.cli.app mcp run`."""
        config_path = fake_home / ".claude.json"
        config_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "indexed": {
                            "type": "stdio",
                            "command": "/usr/bin/python3",
                            "args": ["-m", "indexed.cli.app", "mcp", "run"],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        result = runner.invoke(_get_app(), ["install", "claude-code", "--remove"])

        assert result.exit_code == 0
        # The entry was ours, so it is gone (and with it the file that held
        # nothing else).
        if config_path.exists():
            assert "indexed" not in json.loads(config_path.read_text()).get(
                "mcpServers", {}
            )
        assert "not ours" not in _strip_ansi(result.output)

    def test_remove_keeps_a_hook_group_pointing_at_another_script(
        self, fake_home: Path
    ):
        """Same basename, different location: a team install, not ours."""
        settings_path = fake_home / ".claude/settings.json"
        settings_path.parent.mkdir(parents=True)
        foreign_group = {
            "matcher": "Grep|Glob",
            "hooks": [
                {
                    "type": "command",
                    "command": f"/opt/team/bin/{install_module.HOOK_SCRIPT_NAME}",
                }
            ],
        }
        settings_path.write_text(
            json.dumps({"hooks": {"PreToolUse": [foreign_group]}}), encoding="utf-8"
        )

        result = runner.invoke(_get_app(), ["install", "claude-code", "--remove"])

        assert result.exit_code == 0
        assert json.loads(settings_path.read_text())["hooks"]["PreToolUse"] == [
            foreign_group
        ]


class TestOwnershipEdges:
    def test_refuses_to_replace_a_hand_written_hook_script(self, fake_home: Path):
        hook = fake_home / f".claude/hooks/{install_module.HOOK_SCRIPT_NAME}"
        hook.parent.mkdir(parents=True)
        hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "claude-code"])

        assert result.exit_code == 1
        assert "--force" in _strip_ansi(result.output)
        assert hook.read_text() == "#!/bin/sh\necho mine\n"
        assert not (fake_home / ".claude.json").exists()

    def test_force_replaces_a_hand_written_hook_script(self, fake_home: Path):
        hook = fake_home / f".claude/hooks/{install_module.HOOK_SCRIPT_NAME}"
        hook.parent.mkdir(parents=True)
        hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "claude-code", "--force"])

        assert result.exit_code == 0
        assert install_module.HOOK_MARKER in hook.read_text(encoding="utf-8")
        backup = hook.with_name(hook.name + ".bak")
        assert backup.read_text() == "#!/bin/sh\necho mine\n"

    def test_home_override_reaches_the_hook(self, fake_home: Path):
        """`--home` moves the collections; the hook has to look there."""
        override = fake_home / "elsewhere"

        result = runner.invoke(
            _get_app(), ["install", "claude-code", "--home", str(override)]
        )

        assert result.exit_code == 0
        hook = fake_home / f".claude/hooks/{install_module.HOOK_SCRIPT_NAME}"
        text = hook.read_text(encoding="utf-8")
        assert str(override / ".indexed/data/collections") in text
        assert install_module.COLLECTIONS_PLACEHOLDER not in text

    def test_hook_and_removal_survive_a_home_with_a_space(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A space in the home directory must not break the shell command."""
        home = tmp_path / "Jane Doe"
        home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: home)

        first = runner.invoke(_get_app(), ["install", "claude-code"])
        assert first.exit_code == 0
        group = _settings(home)["hooks"]["PreToolUse"][0]
        assert group["hooks"][0]["command"].startswith("'"), (
            "the command was not shell-quoted"
        )

        second = runner.invoke(_get_app(), ["install", "claude-code"])
        assert second.exit_code == 0
        assert len(_settings(home)["hooks"]["PreToolUse"]) == 1, (
            "the hook was re-added because its quoted command was not recognised"
        )

        removed = runner.invoke(_get_app(), ["install", "claude-code", "--remove"])
        assert removed.exit_code == 0
        assert not (home / ".claude/settings.json").exists()
