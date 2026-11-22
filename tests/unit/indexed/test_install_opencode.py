"""Fresh-install, upgrade and removal coverage for `indexed install opencode`.

Same standard as the Claude Code and Codex lifecycle suites: every assertion
about "your config is preserved" runs against a fixture that already holds
foreign content — another server, a provider block, comments a human wrote — and
the test fails when a foreign byte disappears.

Three OpenCode-specific properties are load-bearing here:

* ``opencode.json`` is hand-edited JSONC and the host never rewrites it, so the
  installer must splice *text*: comments survive, key order survives, CRLF
  survives, and ``--remove`` puts the file back byte for byte.
* There is no hook-trust gate on this host, so the whole install is one write per
  artifact — the write counter below is the assertion for that.
* Code Mode is on by default, so the skill payload names
  ``tools.indexed.search`` inside ``execute``, not a flat tool.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from indexed.cli import install_opencode as opencode_module
from indexed.cli.install_opencode import (
    OpenCodeConfigError,
    delete_member,
    insert_member,
    merge_server_entry,
    remove_server_entry,
    scan_jsonc,
    server_entry_is_ours,
    strip_jsonc,
)

runner = CliRunner()

pytestmark = pytest.mark.unit

# A config a user would not want rewritten: a comment, unknown top-level keys, a
# foreign provider block, a foreign MCP server inside the same `mcp` object we
# add to, and a trailing key that pins key ordering. CRLF throughout, because a
# Windows editor is the common case and the one a text-mode write destroys.
CRLF_CONFIG = (
    "{\r\n"
    "  // hand-written, do not reformat\r\n"
    '  "customKey": {\r\n'
    '    "nested": [1, 2, 3],\r\n'
    '    "why": "unknown top-level key"\r\n'
    "  },\r\n"
    '  "zzz_last": "key ordering probe",\r\n'
    '  "provider": {\r\n'
    '    "ollama": {\r\n'
    '      "npm": "@ai-sdk/ollama",\r\n'
    '      "options": { "baseURL": "http://127.0.0.1:11434" }\r\n'
    "    }\r\n"
    "  },\r\n"
    '  "mcp": {\r\n'
    '    "playwright": {\r\n'
    '      "type": "local",\r\n'
    '      "command": ["npx", "-y", "@playwright/mcp"]\r\n'
    "    }\r\n"
    "  }\r\n"
    "}\r\n"
)

FOREIGN_SKILL = "---\nname: my-own-index-notes\ndescription: mine\n---\n# mine\n"
FOREIGN_PLUGIN = 'export default { id: "somebody-elses-plugin", setup() {} }\n'

ENTRY = {
    "type": "local",
    "command": ["/usr/bin/indexed", "mcp", "run"],
    "enabled": True,
}


def _get_app() -> Any:
    from indexed.cli.app import app

    return app


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the host's config dir at a throwaway HOME for every test.

    `$OPENCODE_CONFIG_DIR` is the host's own isolation lever, so it is deleted
    rather than set: the installer must resolve the XDG path itself.
    """
    monkeypatch.delenv("OPENCODE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def fake_home(_isolated_config: Path) -> Path:
    return _isolated_config


@pytest.fixture
def config_dir(fake_home: Path) -> Path:
    return fake_home / ".config" / "opencode"


@pytest.fixture
def seeded(fake_home: Path, config_dir: Path) -> Path:
    """A config dir that already holds another tool's files, all CRLF."""
    (config_dir / "skills" / "their-skill").mkdir(parents=True)
    (config_dir / "skills" / "their-skill" / "SKILL.md").write_text(
        FOREIGN_SKILL, encoding="utf-8"
    )
    (config_dir / "plugins").mkdir()
    (config_dir / "plugins" / "their-plugin.js").write_text(
        FOREIGN_PLUGIN, encoding="utf-8"
    )
    (config_dir / "opencode.json").write_bytes(CRLF_CONFIG.encode("utf-8"))
    return config_dir


def _config(config_dir: Path) -> Path:
    return config_dir / "opencode.json"


def _member_paths(text: str) -> set[tuple[str, ...]]:
    document = scan_jsonc(text)
    return {
        obj.path + (member.key,)
        for obj in document.objects.values()
        for member in obj.members
    }


def _assert_no_bare_lf(text: str) -> None:
    assert "\n" not in text.replace("\r\n", ""), "install introduced a bare LF"
    assert text.count("\n") == text.count("\r\n")


def _assert_foreign_config_intact(text: str) -> None:
    """Fail loudly if anything that was not ours disappeared or moved."""
    assert "// hand-written, do not reformat" in text
    assert '"baseURL": "http://127.0.0.1:11434"' in text, (
        "foreign nesting was rewritten"
    )
    assert text.index('"customKey"') < text.index('"zzz_last"')
    assert text.index('"zzz_last"') < text.index('"provider"')
    assert text.index('"provider"') < text.index('"mcp"'), "key order changed"
    data = json.loads(strip_jsonc(text))
    assert data["customKey"] == {"nested": [1, 2, 3], "why": "unknown top-level key"}
    assert data["provider"]["ollama"]["options"] == {
        "baseURL": "http://127.0.0.1:11434"
    }
    assert data["mcp"]["playwright"] == {
        "type": "local",
        "command": ["npx", "-y", "@playwright/mcp"],
    }


class TestJsonSplice:
    """The text surgery the whole lifecycle rests on, without the CLI in the way."""

    PATH = Path("/home/x/.config/opencode/opencode.json")

    def _merge(self, text: str, entry: dict[str, Any] | None = None) -> str:
        return merge_server_entry(text, entry or ENTRY, self.PATH)

    def _remove(self, text: str, *, prune: bool = False) -> str:
        return remove_server_entry(text, self.PATH, prune_container=prune)

    def test_insert_into_an_empty_object(self):
        merged = self._merge("{}")

        assert merged.startswith('{\n  "mcp":')
        data = json.loads(strip_jsonc(merged))
        assert data["mcp"]["indexed"]["command"] == ["/usr/bin/indexed", "mcp", "run"]

    def test_insert_into_a_file_without_mcp(self):
        merged = self._merge('{\n  "a": 1\n}\n')

        data = json.loads(strip_jsonc(merged))
        assert data["a"] == 1
        assert data["mcp"]["indexed"] == ENTRY

    def test_insert_into_an_existing_mcp_object(self):
        merged = self._merge('{\n  "mcp": {\n    "other": {"type": "local"}\n  }\n}\n')

        data = json.loads(strip_jsonc(merged))
        assert data["mcp"]["other"] == {"type": "local"}
        assert data["mcp"]["indexed"] == ENTRY

    def test_insert_uses_the_files_indent_and_newline(self):
        merged = self._merge('{\n    "a": 1\n}\n')

        assert '\n    "mcp": {\n        "indexed": {' in merged

    def test_a_second_merge_upgrades_rather_than_duplicating(self):
        once = self._merge(CRLF_CONFIG)
        twice = merge_server_entry(
            once, {**ENTRY, "command": ["/other/indexed", "mcp", "run"]}, self.PATH
        )

        assert twice.count('"indexed"') == 1
        assert "/other/indexed" in twice
        assert "/usr/bin/indexed" not in twice

    def test_insert_is_idempotent(self):
        once = self._merge(CRLF_CONFIG)

        assert self._merge(once) == once

    def test_delete_restores_the_original_bytes(self):
        merged = self._merge(CRLF_CONFIG)

        assert self._remove(merged) == CRLF_CONFIG

    def test_delete_of_a_created_container_restores_the_original_bytes(self):
        text = '{\n  "a": 1\n}\n'
        merged = self._merge(text)

        assert self._remove(merged, prune=True) == text

    def test_delete_of_the_only_member_leaves_an_empty_object(self):
        merged = self._merge("{}")

        assert self._remove(merged, prune=True) == "{}"

    def test_comments_are_preserved(self):
        merged = self._merge(CRLF_CONFIG)

        assert "// hand-written, do not reformat" in merged

    def test_insert_into_an_object_that_holds_only_a_comment(self):
        # A commented-out server is how people park an MCP entry. Rebuilding the
        # body as `{`+member+`}` would delete the user's note.
        original = '{\n  "mcp": {\n    // "old": {"type": "local"},\n  }\n}\n'
        updated = insert_member(
            original, scan_jsonc(original), ("mcp",), "indexed", ENTRY
        )

        assert '// "old": {"type": "local"},' in updated
        assert '"indexed"' in updated
        assert json.loads(strip_jsonc(updated))["mcp"]["indexed"]["type"] == "local"

    def test_deleting_the_only_member_keeps_a_comment_in_the_body(self):
        original = (
            '{\n  "mcp": {\n    // my note\n    "indexed": {"type": "local"}\n  }\n}\n'
        )
        updated = delete_member(original, scan_jsonc(original), ("mcp",), "indexed")

        assert "// my note" in updated
        assert '"indexed"' not in updated
        assert not json.loads(strip_jsonc(updated))["mcp"]

    def test_deleting_the_only_member_still_collapses_a_bare_object(self):
        original = '{\n  "mcp": {\n    "indexed": {"type": "local"}\n  }\n}\n'

        assert delete_member(original, scan_jsonc(original), ("mcp",), "indexed") == (
            '{\n  "mcp": {}\n}\n'
        )

    def test_deleting_the_only_member_of_a_trailing_comma_object_still_collapses(
        self,
    ):
        original = '{\n  "mcp": {\n    "indexed": {"type": "local"},\n  }\n}\n'

        assert delete_member(original, scan_jsonc(original), ("mcp",), "indexed") == (
            '{\n  "mcp": {}\n}\n'
        )

    def test_crlf_is_preserved(self):
        merged = self._merge(CRLF_CONFIG)

        _assert_no_bare_lf(merged)
        assert merged.count("\r\n") > CRLF_CONFIG.count("\r\n")

    def test_foreign_keys_and_their_order_are_preserved(self):
        merged = self._merge(CRLF_CONFIG)

        _assert_foreign_config_intact(merged)

    def test_deep_foreign_nesting_is_untouched(self):
        merged = self._merge(CRLF_CONFIG)

        # The nested array and the inline options object are byte-identical:
        # the splice only ever touches our own span.
        assert '"nested": [1, 2, 3]' in merged
        assert '{ "baseURL": "http://127.0.0.1:11434" }' in merged

    def test_a_single_line_document_stays_single_line(self):
        merged = self._merge('{"a": 1}')

        assert "\n" not in merged
        assert json.loads(strip_jsonc(merged))["mcp"]["indexed"] == ENTRY

    def test_a_single_line_document_survives_an_upgrade(self):
        """An inline entry must stay inline, or a re-run would rewrite the file."""
        once = self._merge('{"a": 1}')

        twice = merge_server_entry(
            once, {**ENTRY, "command": ["/other/indexed", "mcp", "run"]}, self.PATH
        )

        assert "\n" not in twice
        assert twice.count('"indexed"') == 1
        assert "/other/indexed" in twice

    def test_a_trailing_comma_is_tolerated(self):
        merged = self._merge('{\n  "a": 1,\n}\n')

        assert json.loads(strip_jsonc(merged))["mcp"]["indexed"] == ENTRY

    def test_removal_after_a_trailing_comma_keeps_the_content(self):
        """A JSONC trailing comma is legal input, and it comes back too.

        Insertion keeps the user's comma as a separator and carries its own, so
        removal can take exactly what it added and leave the original bytes.
        """
        original = '{\n  "a": 1,\n}\n'
        merged = self._merge(original)

        removed = self._remove(merged, prune=True)

        assert removed == original
        assert json.loads(strip_jsonc(removed)) == {"a": 1}

    def test_malformed_json_is_refused(self):
        with pytest.raises(OpenCodeConfigError) as excinfo:
            self._merge('{\n  "a": \n')

        assert excinfo.value.headline == "is not valid JSON"
        assert "character" in excinfo.value.reason

    def test_a_top_level_array_is_refused(self):
        with pytest.raises(OpenCodeConfigError) as excinfo:
            self._merge("[]")

        assert excinfo.value.headline == "does not hold a JSON object"

    def test_mcp_that_is_not_an_object_is_refused(self):
        with pytest.raises(OpenCodeConfigError) as excinfo:
            self._merge('{\n  "mcp": ["a", "b"]\n}\n')

        assert "not an object" in excinfo.value.reason

    def test_duplicate_keys_are_refused(self):
        with pytest.raises(OpenCodeConfigError) as excinfo:
            self._merge('{\n  "mcp": {},\n  "mcp": {}\n}\n')

        assert "duplicate key" in excinfo.value.reason

    def test_insert_into_a_nested_object(self):
        document = scan_jsonc('{\n  "mcp": {}\n}\n')

        merged = insert_member('{\n  "mcp": {}\n}\n', document, ("mcp",), "x", {"y": 1})

        assert json.loads(strip_jsonc(merged))["mcp"] == {"x": {"y": 1}}
        assert '\n    "x": {\n      "y": 1\n    }\n' in merged


class TestOwnership:
    def test_recognises_both_shapes_resolve_cli_command_produces(self):
        assert server_entry_is_ours(
            {"type": "local", "command": ["/usr/local/bin/indexed", "mcp", "run"]}
        )
        assert server_entry_is_ours(
            {
                "type": "local",
                "command": [
                    "/usr/bin/python3",
                    "-m",
                    "indexed.cli.app",
                    "mcp",
                    "run",
                ],
            }
        )

    def test_rejects_anything_else(self):
        assert not server_entry_is_ours({"type": "local", "command": ["/x/other"]})
        assert not server_entry_is_ours(
            {"type": "local", "command": "/usr/bin/indexed mcp run"}
        )
        assert not server_entry_is_ours({"type": "remote", "url": "http://x"})
        assert not server_entry_is_ours("not a dict")

    def test_refuses_a_foreign_entry_named_indexed(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        original = (
            "{\n"
            '  "mcp": {\n'
            '    "indexed": {"type": "local", "command": ["/usr/bin/other", "serve"]}\n'
            "  }\n"
            "}\n"
        )
        (_config(config_dir)).write_text(original, encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "opencode"])

        assert result.exit_code == 1
        output = _strip_ansi(result.output)
        assert "--force" in output
        assert "mcp.indexed" in output
        assert _config(config_dir).read_text(encoding="utf-8") == original
        assert not (config_dir / "skills/index-use/SKILL.md").exists()

    def test_force_replaces_a_foreign_entry_and_loses_nothing_else(
        self, config_dir: Path
    ):
        config_dir.mkdir(parents=True)
        original = (
            "{\n"
            '  "keep": {"a": 1},\n'
            '  "mcp": {\n'
            '    "indexed": {"type": "local", "command": ["/usr/bin/other", "serve"]}\n'
            "  }\n"
            "}\n"
        )
        (_config(config_dir)).write_text(original, encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "opencode", "--force"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        data = json.loads(_config(config_dir).read_text(encoding="utf-8"))
        assert data["keep"] == {"a": 1}
        assert data["mcp"]["indexed"]["command"][-2:] == ["mcp", "run"]
        backup = _config(config_dir).with_name("opencode.json.bak")
        assert backup.read_text(encoding="utf-8") == original

    def test_refuses_a_hand_written_skill_even_with_force(self, config_dir: Path):
        skill = config_dir / "skills/index-use/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(FOREIGN_SKILL, encoding="utf-8")

        for args in (["install", "opencode"], ["install", "opencode", "--force"]):
            result = runner.invoke(_get_app(), args)

            assert result.exit_code == 1, args
            assert "move it aside" in _strip_ansi(result.output).lower()
            assert skill.read_text(encoding="utf-8") == FOREIGN_SKILL

    def test_refuses_a_hand_written_plugin_even_with_force(self, config_dir: Path):
        plugin = config_dir / "plugins/indexed-nudge.js"
        plugin.parent.mkdir(parents=True)
        plugin.write_text(FOREIGN_PLUGIN, encoding="utf-8")

        for args in (["install", "opencode"], ["install", "opencode", "--force"]):
            result = runner.invoke(_get_app(), args)

            assert result.exit_code == 1, args
            assert plugin.read_text(encoding="utf-8") == FOREIGN_PLUGIN

    def test_remove_never_deletes_a_foreign_skill_or_plugin(self, config_dir: Path):
        skill = config_dir / "skills/index-use/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(FOREIGN_SKILL, encoding="utf-8")
        plugin = config_dir / "plugins/indexed-nudge.js"
        plugin.parent.mkdir(parents=True)
        plugin.write_text(FOREIGN_PLUGIN, encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        assert skill.read_text(encoding="utf-8") == FOREIGN_SKILL
        assert plugin.read_text(encoding="utf-8") == FOREIGN_PLUGIN

    def test_remove_leaves_a_foreign_entry_named_indexed(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        original = (
            '{\n  "mcp": {\n    "indexed": {"type": "local", '
            '"command": ["/somebody/else", "mcp"]}\n  }\n}\n'
        )
        (_config(config_dir)).write_text(original, encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert result.exit_code == 0
        assert _config(config_dir).read_text(encoding="utf-8") == original


class TestCrlfLifecycle:
    """A Windows-editor CRLF config must come back byte for byte.

    These run the command end to end: install, upgrade, remove, with foreign
    files in the same config dir, because that is the invariant that failed
    review on the Codex installer.
    """

    ORIGINAL = CRLF_CONFIG.encode("utf-8")

    def test_install_keeps_every_crlf_and_every_foreign_path(self, seeded: Path):
        result = runner.invoke(_get_app(), ["install", "opencode"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        text = _config(seeded).read_bytes().decode("utf-8")
        _assert_no_bare_lf(text)
        _assert_foreign_config_intact(text)
        data = json.loads(strip_jsonc(text))
        assert data["mcp"]["indexed"]["type"] == "local"
        assert data["mcp"]["indexed"]["enabled"] is True
        # Foreign files in the same config dir are still there.
        assert (seeded / "skills/their-skill/SKILL.md").read_text() == FOREIGN_SKILL
        assert (seeded / "plugins/their-plugin.js").read_text() == FOREIGN_PLUGIN

    def test_upgrade_keeps_crlf_and_adds_no_second_entry(self, seeded: Path):
        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0
        after_first = _config(seeded).read_bytes()

        second = runner.invoke(_get_app(), ["install", "opencode"])

        assert second.exit_code == 0, _strip_ansi(second.output)
        # Nothing changed, so nothing was written: the second run is a no-op.
        assert _config(seeded).read_bytes() == after_first
        text = after_first.decode("utf-8")
        _assert_no_bare_lf(text)
        assert text.count('"indexed"') == 1
        _assert_foreign_config_intact(text)

    def test_remove_restores_the_original_bytes(self, seeded: Path):
        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0
        installed = _config(seeded).read_bytes()
        assert b'"indexed"' in installed, (
            "install wrote nothing to assert removal against"
        )
        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0

        result = runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        assert _config(seeded).read_bytes() == self.ORIGINAL
        # Ours gone, theirs untouched.
        assert not (seeded / "skills/index-use").exists()
        assert not (seeded / "plugins/indexed-nudge.js").exists()
        assert not (seeded / "indexed-install.json").exists()
        assert (seeded / "skills/their-skill/SKILL.md").read_text() == FOREIGN_SKILL
        assert (seeded / "plugins/their-plugin.js").read_text() == FOREIGN_PLUGIN

    def test_remove_keeps_a_config_it_did_not_create(self, seeded: Path):
        runner.invoke(_get_app(), ["install", "opencode"])

        runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert _config(seeded).is_file()

    def test_a_created_config_is_deleted_again(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0
        assert _config(config_dir).is_file()

        result = runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        assert not _config(config_dir).exists()

    def test_the_config_is_written_exactly_once_per_run(
        self, seeded: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """The host has no trust step, so no second pass may touch the file."""
        writes: list[Path] = []
        original = opencode_module.write_text_raw_atomic

        def _counting_write(path: Path, text: str) -> None:
            writes.append(path)
            original(path, text)

        monkeypatch.setattr(opencode_module, "write_text_raw_atomic", _counting_write)

        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0
        assert writes == [_config(seeded)], "install wrote the config more than once"

        writes.clear()
        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0
        assert writes == [], "an unchanged upgrade rewrote the config"

        writes.clear()
        assert (
            runner.invoke(_get_app(), ["install", "opencode", "--remove"]).exit_code
            == 0
        )
        assert writes == [_config(seeded)], "removal wrote the config more than once"

    def test_jsonc_config_file_is_edited_in_place(self, config_dir: Path):
        """Only `opencode.jsonc` exists: that is the document to edit."""
        config_dir.mkdir(parents=True)
        jsonc = config_dir / "opencode.jsonc"
        jsonc.write_bytes(CRLF_CONFIG.encode("utf-8"))

        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0
        assert not _config(config_dir).exists(), "a second config document was created"
        assert json.loads(strip_jsonc(jsonc.read_text(encoding="utf-8")))["mcp"][
            "indexed"
        ]


class TestCommentedConfigLifecycle:
    """A comment in `mcp` is the user's text: install must not eat it, and
    `--remove` must not delete the file that still holds it.
    """

    COMMENTED_MCP = (
        "{\r\n"
        "  // my own note\r\n"
        '  "mcp": {\r\n'
        '    // "parked": {"type": "local", "command": ["/bin/true"]},\r\n'
        "  }\r\n"
        "}\r\n"
    )

    def test_install_and_remove_keep_the_comment_and_the_file(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        config = _config(config_dir)
        config.write_bytes(self.COMMENTED_MCP.encode("utf-8"))

        installed = runner.invoke(_get_app(), ["install", "opencode"])

        assert installed.exit_code == 0, _strip_ansi(installed.output)
        after_install = config.read_bytes().decode("utf-8")
        assert "// my own note" in after_install
        assert '// "parked": {"type": "local", "command": ["/bin/true"]},' in (
            after_install
        )
        assert '"indexed"' in after_install
        _assert_no_bare_lf(after_install)

        removed = runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert removed.exit_code == 0, _strip_ansi(removed.output)
        assert config.is_file(), "--remove deleted a file that still had a comment"
        after_remove = config.read_bytes().decode("utf-8")
        assert "// my own note" in after_remove
        assert '// "parked"' in after_remove
        assert '"indexed"' not in after_remove


class TestRefusalsAreMessages:
    """Every refusal exits 1 with a readable reason, never a traceback."""

    def _write(self, config_dir: Path, body: str) -> None:
        config_dir.mkdir(parents=True)
        _config(config_dir).write_bytes(body.encode("utf-8"))

    def test_mcp_that_is_not_an_object(self, config_dir: Path):
        self._write(config_dir, '{\n  "mcp": ["a", "b"]\n}\n')

        result = runner.invoke(_get_app(), ["install", "opencode"])

        assert result.exit_code == 1
        assert "OpenCode config" in _strip_ansi(result.output)
        assert "not an object" in _strip_ansi(result.output)

    def test_a_duplicate_key(self, config_dir: Path):
        self._write(config_dir, '{\n  "mcp": {},\n  "mcp": {}\n}\n')

        result = runner.invoke(_get_app(), ["install", "opencode"])

        assert result.exit_code == 1
        assert "duplicate key" in _strip_ansi(result.output)

    def test_an_unescaped_windows_path(self, config_dir: Path):
        # A hand-written `C:\Users\me` is invalid JSON and the scanner sees it
        # before `json.loads` does; it must still report, not raise.
        self._write(config_dir, '{\n  "cwd": "C:\\Users\\me"\n}\n')

        result = runner.invoke(_get_app(), ["install", "opencode"])

        assert result.exit_code == 1
        assert "is not valid JSON" in _strip_ansi(result.output)


class TestReviewRegressions:
    """Findings from review that were real bugs in an earlier revision."""

    ENTRY_TEXT = (
        '{"type": "local", "command": ["/usr/bin/indexed", "mcp", "run"], '
        '"enabled": true}'
    )

    def test_a_comment_inside_a_created_mcp_object_keeps_the_file(
        self, config_dir: Path
    ):
        config_dir.mkdir(parents=True)
        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0
        config = _config(config_dir)
        text = config.read_text(encoding="utf-8").replace(
            '"mcp": {', '"mcp": {\n    // keep: local venv'
        )
        config.write_text(text, encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        assert config.is_file(), "--remove deleted a file that still had a comment"
        assert "// keep: local venv" in config.read_text(encoding="utf-8")

    def test_removal_never_deletes_a_config_file_it_did_not_create(
        self, config_dir: Path
    ):
        config_dir.mkdir(parents=True)
        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0
        _config(config_dir).unlink()
        user_config = config_dir / "opencode.jsonc"
        user_config.write_text("{}\n", encoding="utf-8")
        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0

        result = runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        assert user_config.is_file(), "--remove deleted the user's own config"

    def test_a_duplicate_key_of_any_type_is_refused(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        body = '{\n  "mcp": {"indexed": ' + self.ENTRY_TEXT + '},\n  "mcp": null\n}\n'
        config = _config(config_dir)
        config.write_text(body, encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "opencode", "--force"])

        assert result.exit_code == 1
        assert "duplicate key" in _strip_ansi(result.output)
        assert config.read_text(encoding="utf-8") == body

    def test_an_explicit_null_entry_is_not_a_missing_entry(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        config = _config(config_dir)
        original = '{\n  "mcp": {"indexed": null}\n}\n'
        config.write_text(original, encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "opencode"])

        assert result.exit_code == 1
        # Refused, not silently replaced: the user's null is still there.
        assert config.read_text(encoding="utf-8") == original

    def test_removal_keeps_a_comment_between_servers(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        config = _config(config_dir)
        config.write_text(
            "{\n"
            '  "mcp": {\n'
            f'    "indexed": {self.ENTRY_TEXT},\n'
            "    // keep me\n"
            '    "z": {}\n'
            "  }\n"
            "}\n",
            encoding="utf-8",
        )

        result = runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        text = config.read_text(encoding="utf-8")
        assert "// keep me" in text
        assert '"z"' in text
        assert '"indexed"' not in text

    def test_a_trailing_comma_object_round_trips_byte_for_byte(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        config = _config(config_dir)
        original = b'{\n  "mcp": {\n    "a": {},\n  }\n}\n'
        config.write_bytes(original)
        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0

        result = runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        assert config.read_bytes() == original

    def test_blank_config_bytes_are_restored(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        config = _config(config_dir)
        config.write_bytes(b" \r\n")
        assert runner.invoke(_get_app(), ["install", "opencode"]).exit_code == 0

        result = runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert result.exit_code == 0, _strip_ansi(result.output)
        assert config.read_bytes() == b" \r\n"

    def test_the_windows_launcher_is_recognised_as_ours(self):
        assert server_entry_is_ours(
            {
                "type": "local",
                "command": ["C:\\Python\\Scripts\\indexed.exe", "mcp", "run"],
            }
        )

    def test_a_foreign_v2_nested_entry_is_refused(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        config = _config(config_dir)
        config.write_text(
            '{\n  "mcp": {"servers": {"indexed": {"type": "local", '
            '"command": ["/opt/other-agent/bin/serve", "--mcp"]}}}\n}\n',
            encoding="utf-8",
        )

        result = runner.invoke(_get_app(), ["install", "opencode"])

        assert result.exit_code == 1
        output = _strip_ansi(result.output)
        assert "mcp.servers.indexed" in output
        assert config.read_text(encoding="utf-8").startswith('{\n  "mcp": {"servers"')

    def test_an_unreadable_config_is_a_message_not_a_traceback(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        _config(config_dir).write_bytes(b'{"mcp": {"x": "\xff\xfe"}}')

        result = runner.invoke(_get_app(), ["install", "opencode"])

        assert result.exit_code == 1
        output = _strip_ansi(result.output)
        assert "OpenCode config" in output
        assert "not valid UTF-8" in output


class TestPayloadAssets:
    def test_the_installed_skill_carries_both_markers(self, seeded: Path):
        runner.invoke(_get_app(), ["install", "opencode"])
        text = (seeded / "skills/index-use/SKILL.md").read_text(encoding="utf-8")

        assert text.startswith("---\nname: index-use\n")
        assert "indexed/managed" in text
        assert opencode_module.frontmatter_metadata(text)["indexed/managed"] == "1"
        # A description is what makes the host advertise the skill at all.
        assert "description:" in text
        assert "tools.indexed.search" in text
        assert "indexed_search" in text

    def test_the_installed_plugin_is_a_nudge_and_nothing_else(self, seeded: Path):
        runner.invoke(_get_app(), ["install", "opencode"])
        text = (seeded / "plugins/indexed-nudge.js").read_text(encoding="utf-8")

        assert opencode_module.PLUGIN_MARKER in text
        assert 'id: "indexed-nudge"' in text
        assert 'ctx.session.hook("context"' in text
        # A nudge must never be able to allow or deny a tool call. The header
        # comment says so in words, so the check runs on the code lines only.
        code = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("//")
        )
        assert "permission" not in code
        assert "ctx.permission" not in text
        assert "execute.before" not in code
        assert opencode_module.COLLECTIONS_PLACEHOLDER not in text

    def test_a_home_with_a_quote_and_a_backslash_is_baked_literally(
        self, seeded: Path, tmp_path: Path
    ):
        weird = tmp_path / 'weird"path\\x'
        result = runner.invoke(
            _get_app(), ["install", "opencode", "--home", str(weird)]
        )

        assert result.exit_code == 0, _strip_ansi(result.output)
        plugin = (seeded / "plugins/indexed-nudge.js").read_text(encoding="utf-8")
        literal = next(
            line.split("=", 1)[1].strip()
            for line in plugin.splitlines()
            if line.startswith("const COLLECTIONS_ROOT")
        )
        # JSON string literal rules are JS string literal rules, so the baked
        # value parses back to the exact path.
        assert json.loads(literal) == str(weird / ".indexed/data/collections")
        assert '"' not in literal[1:-1].replace('\\"', "")
        entry = json.loads(strip_jsonc(_config(seeded).read_text(encoding="utf-8")))
        assert entry["mcp"]["indexed"]["environment"] == {"HOME": str(weird)}

    def test_home_does_not_move_the_config_dir(self, seeded: Path, tmp_path: Path):
        elsewhere = tmp_path / "elsewhere"

        result = runner.invoke(
            _get_app(), ["install", "opencode", "--home", str(elsewhere)]
        )

        assert result.exit_code == 0, _strip_ansi(result.output)
        assert _config(seeded).is_file()
        assert not (elsewhere / ".config" / "opencode").exists()


class TestDryRun:
    def test_dry_run_writes_nothing(self, fake_home: Path):
        result = runner.invoke(_get_app(), ["install", "opencode", "--dry-run"])

        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "nothing was written" in output
        assert "Would write:" in output
        assert not (fake_home / ".config" / "opencode").exists()

    def test_dry_run_remove_writes_nothing(self, seeded: Path):
        runner.invoke(_get_app(), ["install", "opencode"])
        before = _config(seeded).read_bytes()

        result = runner.invoke(
            _get_app(), ["install", "opencode", "--remove", "--dry-run"]
        )

        assert result.exit_code == 0
        assert "Would remove:" in _strip_ansi(result.output)
        assert _config(seeded).read_bytes() == before
        assert (seeded / "skills/index-use/SKILL.md").is_file()
        assert (seeded / "plugins/indexed-nudge.js").is_file()

    def test_a_second_remove_is_a_no_op(self, seeded: Path):
        runner.invoke(_get_app(), ["install", "opencode"])
        runner.invoke(_get_app(), ["install", "opencode", "--remove"])
        before = _config(seeded).read_bytes()

        result = runner.invoke(_get_app(), ["install", "opencode", "--remove"])

        assert result.exit_code == 0
        assert "nothing to remove" in _strip_ansi(result.output)
        assert _config(seeded).read_bytes() == before


class TestConfigResolution:
    def test_opencode_config_dir_honours_the_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path / "alt"))

        assert opencode_module.opencode_config_dir() == tmp_path / "alt"

    def test_opencode_config_dir_honours_xdg(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        assert opencode_module.opencode_config_dir() == tmp_path / "xdg" / "opencode"

    def test_opencode_config_dir_falls_back_to_dot_config(self, fake_home: Path):
        assert opencode_module.opencode_config_dir() == fake_home / ".config/opencode"

    def test_an_invalid_config_is_left_alone(self, config_dir: Path):
        config_dir.mkdir(parents=True)
        (_config(config_dir)).write_text('{\n  "mcp": \n', encoding="utf-8")

        result = runner.invoke(_get_app(), ["install", "opencode"])

        assert result.exit_code == 1
        assert "is not valid JSON" in _strip_ansi(result.output)
        assert _config(config_dir).read_text(encoding="utf-8") == '{\n  "mcp": \n'
