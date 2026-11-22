"""`indexed install codex` — wire indexed into the Codex CLI, and take it out.

Codex differs from Claude Code in three ways that shape this module: its
configuration is **TOML** (``~/.codex/config.toml``), its hooks live in a
separate ``~/.codex/hooks.json``, and it has no Grep/Glob tool — an agent
searches through the ``Bash`` tool, so the nudge hook reads the command line
instead of matching a tool name.

Installs five owned artifacts into the user's Codex home, and removes exactly
those again on ``--remove``:

=============================================  ==============================
``config.toml`` (``mcp_servers.indexed``)      the stdio MCP server entry
``skills/index-use/SKILL.md``                  the ``index-use`` skill
``hooks.json`` (``PreToolUse`` group)          registers the nudge hook
``indexed/indexed-nudge.sh``                   the nudge hook script
``indexed-install.json``                       what was installed, by version
=============================================  ==============================

Two rules keep this safe on a file the user hand-edits:

* ``codex mcp add`` is **not** byte-preserving inside ``[mcp_servers.*]`` — it
  re-serialises that region, dropping comments. So this command edits the TOML
  text itself: only our table block is ever replaced or deleted, every other
  byte of the user's file (comments, spacing, other tables) survives verbatim.
* Codex refuses to run a hook until it is trusted. Rather than forge a hash, the
  installer asks Codex for the hash it computed (``codex app-server`` →
  ``hooks/list``) and records that key in ``hooks.state`` — the same write the
  Codex TUI makes when a user approves a hook. Without the Codex binary the
  install still completes and says the hook needs one-time approval.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import threading
import tomllib
from pathlib import Path
from typing import Any, Optional, Sequence

import typer

from indexed.cli import install as base
from indexed.cli.utils.components import (
    get_dim_style,
    get_heading_style,
    get_label_style,
    print_error,
    print_success,
    print_warning,
)
from indexed.cli.utils.console import console, render_user_text
from indexed.utils.version import installed_version

# Must stay "indexed": Codex names MCP tools mcp__<server>__<tool>, and the
# index-use skill documents mcp__indexed__search.
SERVER_NAME = "indexed"
SKILL_NAME = "index-use"
SKILL_PAYLOAD = "installers/codex/index-use.SKILL.md"
HOOK_SCRIPT_NAME = "indexed-nudge.sh"
HOOK_PAYLOAD = f"installers/codex/{HOOK_SCRIPT_NAME}"
INSTALL_SCHEMA = 1
# Written into the hook script's first line and matched on removal, so a file a
# user put there by hand is never deleted by `--remove`.
HOOK_MARKER = "indexed-install-hook"
# Codex's shell tool arrives as `Bash` (or the platform equivalent); the matcher
# is a full-string regex over the tool name.
HOOK_MATCHER = "Bash|Zsh|PowerShell|ShCmd"
HOOK_EVENT = "PreToolUse"
# Codex spells events snake_case inside a hooks.state key.
HOOK_EVENT_KEY = "pre_tool_use"
MANIFEST_NAME = "indexed-install.json"
# Replaced with the collections root at install time, so `--home` reaches the
# hook as well as the MCP server entry.
COLLECTIONS_PLACEHOLDER = "{{COLLECTIONS_ROOT}}"
# One line above the table so a human reading config.toml knows where it came
# from; removal deletes it with the table.
SERVER_MARKER = "# indexed: registered by `indexed install codex`"
SERVER_TABLE = f"mcp_servers.{SERVER_NAME}"
TRUST_PREFIX = "hooks.state."

app = typer.Typer(help="Install indexed integrations for coding agents")


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def codex_dir() -> Path:
    """The Codex home this install writes to (``$CODEX_HOME`` or ``~/.codex``)."""
    override = os.environ.get("CODEX_HOME")
    return Path(override).expanduser() if override else Path.home() / ".codex"


def codex_config_path() -> Path:
    """`config.toml` — the file Codex reads servers and hook trust from."""
    return codex_dir() / "config.toml"


def codex_hooks_path() -> Path:
    """`hooks.json` — the only place Codex reads hook definitions from."""
    return codex_dir() / "hooks.json"


def codex_skill_path() -> Path:
    """Where Codex reads a personal skill (same root as Claude Code's)."""
    return codex_dir() / "skills" / SKILL_NAME / "SKILL.md"


def codex_hook_path() -> Path:
    """The nudge hook script this installer owns and Codex executes."""
    return codex_dir() / "indexed" / HOOK_SCRIPT_NAME


def codex_manifest_path() -> Path:
    """Record of what this installer owns in the user's Codex home."""
    return codex_dir() / MANIFEST_NAME


# --------------------------------------------------------------------------- #
# Payloads (shipped in the wheel, readable from a source checkout)
# --------------------------------------------------------------------------- #
def read_skill_text() -> str:
    """The `index-use` skill payload, written for Codex's tool names."""
    return base.read_payload(SKILL_PAYLOAD)


def installed_hook_text(home_override: Optional[Path]) -> str:
    """The hook script as installed, with its collections root baked in."""
    root = base.collections_root(home_override)
    return base.read_payload(HOOK_PAYLOAD).replace(COLLECTIONS_PLACEHOLDER, str(root))


def build_server_entry(command: list[str], home: Optional[Path]) -> dict[str, Any]:
    """One stdio server entry in Codex's TOML schema (no ``type`` key)."""
    entry: dict[str, Any] = {"command": command[0], "args": list(command[1:])}
    # indexed resolves collections from HOME; an override is carried to the
    # server process through the env sub-table.
    if home is not None:
        entry["env"] = {"HOME": str(home)}
    return entry


# --------------------------------------------------------------------------- #
# TOML: surgical block edits that leave every other byte alone
# --------------------------------------------------------------------------- #
class CodexConfigError(ValueError):
    """An unreadable `config.toml`, with the path and the reason kept apart."""

    def __init__(self, path: Path, headline: str, reason: str) -> None:
        super().__init__(f"{path} {headline}: {reason}")
        self.path = path
        self.headline = headline
        self.reason = reason


def read_toml(path: Path) -> dict[str, Any]:
    """Parse an existing TOML file, or return an empty document."""
    if not path.exists():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CodexConfigError(path, "is not valid TOML", str(exc)) from exc
    return data


def _toml_string(value: str) -> str:
    """A double-quoted TOML basic string (JSON quoting is a valid subset)."""
    return json.dumps(value, ensure_ascii=False)


def render_server_table(entry: dict[str, Any]) -> list[str]:
    """The lines of our `[mcp_servers.indexed]` block, marker first."""
    args = ", ".join(_toml_string(str(part)) for part in entry.get("args") or [])
    lines = [
        SERVER_MARKER,
        f"[{SERVER_TABLE}]",
        f"command = {_toml_string(str(entry['command']))}",
        f"args = [{args}]",
    ]
    env = entry.get("env")
    if isinstance(env, dict) and env:
        lines.append("")
        lines.append(f"[{SERVER_TABLE}.env]")
        for key in sorted(env):
            lines.append(f"{key} = {_toml_string(str(env[key]))}")
    return lines


def render_trust_table(key: str, trusted_hash: str) -> list[str]:
    """The lines of a `[hooks.state."<key>"]` block recording one approval."""
    return [
        f"[{TRUST_PREFIX}{_toml_string(key)}]",
        f"trusted_hash = {_toml_string(trusted_hash)}",
    ]


def _table_key(line: str) -> Optional[str]:
    """The key of a ``[table]`` header line, or None for anything else."""
    stripped = line.strip()
    if not stripped.startswith("[") or stripped.startswith("[["):
        return None
    if not stripped.endswith("]"):
        return None
    return re.sub(r"\s+", "", stripped[1:-1])


def _in_table(key: str, target: str) -> bool:
    return key == target or key.startswith(target + ".")


def _block_bounds(lines: Sequence[str], target: str) -> Optional[tuple[int, int]]:
    """Line range ``[start, end)`` covering `target` and its sub-tables.

    The range ends after the last table header or key/value line, never at the
    next header: a comment a user left directly above *their* next table belongs
    to them, and deleting our block must not take it along.
    """
    start = None
    for index, line in enumerate(lines):
        key = _table_key(line)
        if key is None:
            continue
        if _in_table(key, target):
            if start is None:
                start = index
        elif start is not None:
            return start, _last_meaningful(lines, start, index)
    if start is None:
        return None
    return start, _last_meaningful(lines, start, len(lines))


def _last_meaningful(lines: Sequence[str], start: int, end: int) -> int:
    """`end` trimmed back over trailing blank and comment-only lines."""
    while end > start + 1 and (
        not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")
    ):
        end -= 1
    return end


def _block_start_with_marker(lines: Sequence[str], start: int) -> int:
    """Include the marker comment line directly above a block, if present."""
    if start > 0 and lines[start - 1].strip().startswith(SERVER_MARKER):
        return start - 1
    return start


def _trim_trailing_blanks(lines: list[str], start: int, end: int) -> int:
    while end > start and not lines[end - 1].strip():
        end -= 1
    return end


def _collapse_seam(lines: list[str], index: int) -> list[str]:
    """Remove one of two blank lines meeting where a block was deleted."""
    if (
        0 < index < len(lines)
        and not lines[index - 1].strip()
        and not lines[index].strip()
    ):
        return lines[:index] + lines[index + 1 :]
    return lines


def merge_server_block(text: str, entry: dict[str, Any]) -> str:
    """`text` with our server table set, every other byte preserved."""
    lines = text.splitlines()
    bounds = _block_bounds(lines, SERVER_TABLE)
    rendered = render_server_table(entry)
    if bounds is None:
        body = text.rstrip("\n")
        separator = "\n\n" if body else ""
        return f"{body}{separator}" + "\n".join(rendered) + "\n"
    start, end = bounds
    start = _block_start_with_marker(lines, start)
    end = _trim_trailing_blanks(lines, start, end)
    out = lines[:start] + rendered + lines[end:]
    return "\n".join(out).rstrip("\n") + "\n"


def remove_server_block(text: str) -> str:
    """`text` without our server table (marker included), nothing else lost."""
    lines = text.splitlines()
    bounds = _block_bounds(lines, SERVER_TABLE)
    if bounds is None:
        return text
    start, end = bounds
    start = _block_start_with_marker(lines, start)
    end = _trim_trailing_blanks(lines, start, end)
    out = _collapse_seam(lines[:start] + lines[end:], start)
    body = "\n".join(out).strip("\n")
    return f"{body}\n" if body else ""


def merge_trust_block(text: str, key: str, trusted_hash: str) -> str:
    """`text` with one `hooks.state` entry for our hook, nothing else touched."""
    lines = text.splitlines()
    target = re.sub(r"\s+", "", f"{TRUST_PREFIX}{_toml_string(key)}")
    rendered = render_trust_table(key, trusted_hash)
    bounds = _block_bounds(lines, target)
    if bounds is None:
        body = text.rstrip("\n")
        separator = "\n\n" if body else ""
        return f"{body}{separator}" + "\n".join(rendered) + "\n"
    start, end = bounds
    out = lines[:start] + rendered + lines[end:]
    return "\n".join(out).rstrip("\n") + "\n"


def remove_trust_block(text: str, key: str) -> str:
    """`text` without the `hooks.state` entry for `key`, nothing else lost."""
    lines = text.splitlines()
    target = re.sub(r"\s+", "", f"{TRUST_PREFIX}{_toml_string(key)}")
    bounds = _block_bounds(lines, target)
    if bounds is None:
        return text
    start, end = bounds
    out = _collapse_seam(lines[:start] + lines[end:], start)
    body = "\n".join(out).strip("\n")
    return f"{body}\n" if body else ""


# --------------------------------------------------------------------------- #
# hooks.json — a JSON file this installer shares with the user
# --------------------------------------------------------------------------- #
def build_hook_group(hook_path: Path) -> dict[str, Any]:
    """The PreToolUse group that runs our nudge hook for shell tools."""
    return {
        "matcher": HOOK_MATCHER,
        "hooks": [
            {"type": "command", "command": shlex.quote(str(hook_path)), "timeout": 10}
        ],
    }


def _hook_command(group: object) -> str:
    """The single command a hook group runs, or "" for anything else."""
    if not isinstance(group, dict):
        return ""
    hooks = group.get("hooks")
    if not isinstance(hooks, list) or len(hooks) != 1:
        return ""
    hook = hooks[0]
    if not isinstance(hook, dict):
        return ""
    command = hook.get("command")
    return command if isinstance(command, str) else ""


def hook_group_is_ours(group: object) -> bool:
    """True when a PreToolUse group runs the script *this* install owns.

    Matched on the full installed path (after unquoting) plus our matcher, so a
    same-named script somewhere else, or a group the user re-pointed, survives.
    """
    if not isinstance(group, dict) or group.get("matcher") != HOOK_MATCHER:
        return False
    command = _hook_command(group)
    if not command:
        return False
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if len(parts) != 1:
        return False
    return Path(parts[0]).expanduser() == codex_hook_path()


def merge_hook_group(existing: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    """Return `existing` hooks with our group set in place, nothing else lost."""
    merged = dict(existing)
    hooks = merged.get("hooks")
    hooks = dict(hooks) if isinstance(hooks, dict) else {}
    groups = hooks.get(HOOK_EVENT)
    groups = list(groups) if isinstance(groups, list) else []
    out: list[Any] = []
    replaced = False
    for candidate in groups:
        if hook_group_is_ours(candidate):
            if not replaced:
                out.append(group)
                replaced = True
            continue
        out.append(candidate)
    if not replaced:
        out.append(group)
    hooks[HOOK_EVENT] = out
    merged["hooks"] = hooks
    return merged


def remove_hook_group(existing: dict[str, Any]) -> dict[str, Any]:
    """Return `existing` hooks without our group; empty containers go."""
    merged = dict(existing)
    hooks = merged.get("hooks")
    if not isinstance(hooks, dict):
        return merged
    hooks = dict(hooks)
    groups = hooks.get(HOOK_EVENT)
    if isinstance(groups, list):
        kept = [group for group in groups if not hook_group_is_ours(group)]
        if kept:
            hooks[HOOK_EVENT] = kept
        else:
            hooks.pop(HOOK_EVENT, None)
    if hooks:
        merged["hooks"] = hooks
    else:
        merged.pop("hooks", None)
    return merged


def our_group_index(hooks_doc: dict[str, Any]) -> Optional[int]:
    """Position of our group among all PreToolUse groups (Codex's trust key)."""
    groups = hooks_doc.get("hooks", {})
    groups = groups.get(HOOK_EVENT) if isinstance(groups, dict) else None
    if not isinstance(groups, list):
        return None
    for index, group in enumerate(groups):
        if hook_group_is_ours(group):
            return index
    return None


def trust_key(hooks_path: Path, group_index: int) -> str:
    """The `hooks.state` key Codex computes for our group and handler."""
    return f"{hooks_path}:{HOOK_EVENT_KEY}:{group_index}:0"


# --------------------------------------------------------------------------- #
# Trust: ask Codex for the hash it computed, never invent one
# --------------------------------------------------------------------------- #
def codex_binary() -> Optional[str]:
    return shutil.which("codex")


def _read_result(messages: queue.Queue, request_id: int, deadline: float) -> Any:
    """Read stdout lines until the response with `request_id` arrives."""
    import time

    while time.monotonic() < deadline:
        try:
            line = messages.get(timeout=max(0.05, deadline - time.monotonic()))
        except queue.Empty:
            return None
        if line is None:
            return None
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("id") == request_id:
            return message.get("result")
    return None


def harvest_hook_hash(
    hooks_path: Path, key: str, cwd: Path, timeout: float = 20.0
) -> Optional[str]:
    """The ``currentHash`` Codex reports for *our* hook, or None if unavailable.

    Trust is host state, not ours: a hash this installer made up would be
    rejected on the next start, so the value is read back from the host's own
    ``hooks/list`` (the same call its TUI makes before writing trust). Matched
    on the hook key, not just the file — every hook in ``hooks.json`` shares
    that path, and recording another group's hash would leave ours modified.
    """
    binary = codex_binary()
    if binary is None or not hooks_path.is_file():
        return None
    env = dict(os.environ)
    env["CODEX_HOME"] = str(hooks_path.parent)
    env.pop("OPENAI_API_KEY", None)
    try:
        proc = subprocess.Popen(
            [binary, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            cwd=str(cwd),
            env=env,
        )
    except OSError:
        return None
    messages: queue.Queue = queue.Queue()

    def _pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            messages.put(line)
        messages.put(None)

    thread = threading.Thread(target=_pump, daemon=True)
    thread.start()

    def send(payload: dict[str, Any]) -> None:
        if proc.stdin is None:
            return
        with contextlib.suppress(OSError, ValueError):
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()

    import time

    deadline = time.monotonic() + timeout
    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "indexed-install", "version": "1"}},
            }
        )
        if _read_result(messages, 1, deadline) is None:
            return None
        send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "hooks/list",
                "params": {"cwds": [str(cwd)]},
            }
        )
        result = _read_result(messages, 2, deadline)
    finally:
        with contextlib.suppress(OSError):
            proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)
        with contextlib.suppress(OSError):
            proc.kill()
    if not isinstance(result, dict):
        return None
    for entry in result.get("data") or []:
        for hook in entry.get("hooks") or []:
            if not isinstance(hook, dict):
                continue
            if hook.get("key") != key:
                continue
            current = hook.get("currentHash")
            if isinstance(current, str) and current.startswith("sha256:"):
                return current
    return None


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _print_path(label: str, value: object) -> None:
    label_style = get_label_style()
    dim = get_dim_style()
    console.print(f"  [{label_style}]{label}[/{label_style}]")
    console.print(render_user_text(value, style=dim), soft_wrap=True)


def _print_plan(changes: Sequence[base.Change]) -> None:
    """Print one line per artifact the command will touch."""
    for change in changes:
        if change.action == "unchanged":
            _print_path(change.label, f"{change.path} (already current)")
        elif change.action == "skipped":
            _print_path(change.label, f"{change.path} (not ours - left alone)")
        else:
            _print_path(change.label, f"{change.path} ({change.action})")


def _prune_emptied(path: Path) -> None:
    """Remove the directories a removal emptied, never past the Codex home.

    `base.apply_changes` prunes up to the *Claude* dir; the Codex home is a
    different tree, so removal would otherwise leave `~/.codex/indexed/` behind.
    """
    stop = codex_dir()
    current = path
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
def _json_change(
    label: str, path: Path, data: dict[str, Any], existed: bool
) -> base.Change:
    text = base.dump_config(data)
    if existed and path.is_file():
        try:
            if base.read_config(path) == data:
                return base.Change(label, path, "unchanged", text)
        except base.ConfigFileError:
            pass
    return base.Change(label, path, "created" if not existed else "updated", text)


def _manifest(
    config_path: Path,
    hooks_path: Path,
    skill_path: Path,
    hook_path: Path,
    trust: Optional[str],
) -> dict[str, Any]:
    return {
        "schema": INSTALL_SCHEMA,
        "package_version": installed_version(),
        "server": {"file": str(config_path), "key": SERVER_TABLE},
        "skill": str(skill_path),
        "hook": {
            "file": str(hook_path),
            "registry": str(hooks_path),
            "event": HOOK_EVENT,
            "matcher": HOOK_MATCHER,
        },
        "trust_state": trust,
    }


def _plan_install(
    *,
    config_text: str,
    config_path: Path,
    hooks_doc: dict[str, Any],
    hooks_existed: bool,
    hooks_path: Path,
    hook_path: Path,
    skill_path: Path,
    manifest_path: Path,
    hook_text: str,
    skill_text: str,
    entry: dict[str, Any],
) -> list[base.Change]:
    """Every artifact an install writes, with what would change about each."""
    merged_hooks = merge_hook_group(hooks_doc, build_hook_group(hook_path))
    merged_config = merge_server_block(config_text, entry)
    manifest = _manifest(config_path, hooks_path, skill_path, hook_path, None)
    if not config_path.is_file():
        config_action = "created"
    elif merged_config != config_text:
        config_action = "updated"
    else:
        config_action = "unchanged"
    return [
        base.Change("Config", config_path, config_action, merged_config),
        _json_change("Hook registry", hooks_path, merged_hooks, hooks_existed),
        base._file_change("Hook script", hook_path, hook_text, executable=True),
        base._file_change("Skill", skill_path, skill_text),
        base._file_change("Manifest", manifest_path, base.dump_config(manifest)),
    ]


def _plan_removal(
    *,
    config_text: str,
    config_path: Path,
    hooks_doc: dict[str, Any],
    hooks_path: Path,
    hook_path: Path,
    skill_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> list[base.Change]:
    """Every artifact a removal touches, with what would change about each."""
    changes: list[base.Change] = []

    servers = read_toml(config_path).get("mcp_servers")
    ours_server = servers.get(SERVER_NAME) if isinstance(servers, dict) else None
    if ours_server is None:
        changes.append(base.Change("Config", config_path, "unchanged"))
    elif not base.server_entry_is_ours(ours_server):
        changes.append(base.Change("Config", config_path, "skipped"))
    else:
        remaining = remove_server_block(config_text)
        trust_values = _trust_keys_to_remove(hooks_doc, hooks_path, manifest)
        for key in trust_values:
            remaining = remove_trust_block(remaining, key)
        if not remaining.strip() or read_toml_text(remaining) == {}:
            changes.append(base._deletion("Config", config_path))
        else:
            changes.append(
                base.Change(
                    "Config",
                    config_path,
                    "updated" if remaining != config_text else "unchanged",
                    remaining,
                )
            )

    merged_hooks = remove_hook_group(hooks_doc)
    if merged_hooks == hooks_doc:
        changes.append(base.Change("Hook registry", hooks_path, "unchanged"))
    elif not merged_hooks:
        changes.append(base._deletion("Hook registry", hooks_path))
    else:
        changes.append(_json_change("Hook registry", hooks_path, merged_hooks, True))

    changes.append(
        base._owned_file_removal(
            "Hook script",
            hook_path,
            lambda text: HOOK_MARKER in text,
            keep_backup=False,
        )
    )
    changes.append(
        base._owned_file_removal(
            "Skill",
            skill_path,
            lambda text: base._frontmatter_name(text) == SKILL_NAME,
            keep_backup=False,
        )
    )
    changes.append(
        base._deletion("Manifest", manifest_path, keep_backup=False)
        if manifest_path.is_file()
        else base.Change("Manifest", manifest_path, "unchanged")
    )
    return changes


def read_toml_text(text: str) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}


def _trust_keys_to_remove(
    hooks_doc: dict[str, Any], hooks_path: Path, manifest: dict[str, Any]
) -> list[str]:
    """Every `hooks.state` key this install could have written, deduped."""
    keys: list[str] = []
    recorded = manifest.get("trust_state")
    if isinstance(recorded, str) and recorded:
        keys.append(recorded)
    index = our_group_index(hooks_doc)
    if index is not None:
        candidate = trust_key(hooks_path, index)
        if candidate not in keys:
            keys.append(candidate)
    # A stale key from an earlier layout still points at our registry.
    prefix = f"{hooks_path}:{HOOK_EVENT_KEY}:"
    return [key for key in keys if key.startswith(prefix)]


# --------------------------------------------------------------------------- #
# The command
# --------------------------------------------------------------------------- #
@base.app.command("codex")
def codex(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print what would be written and change nothing.",
    ),
    home: Optional[str] = typer.Option(
        None,
        "--home",
        help="HOME the MCP server runs with; collections live in HOME/.indexed "
        "(default: your HOME).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Replace an existing mcp_servers.indexed entry that points elsewhere.",
    ),
    remove: bool = typer.Option(
        False,
        "--remove",
        help="Remove everything this installer added, leaving the rest of your "
        "configuration untouched.",
    ),
) -> None:
    """Register the indexed MCP server, skill and search hook with Codex.

    Writes the user-scope MCP registration into ~/.codex/config.toml, the
    index-use skill into ~/.codex/skills, and a PreToolUse nudge hook into
    ~/.codex/hooks.json (other servers, hooks and comments are preserved).
    Safe to run again: an existing install is upgraded in place, never
    duplicated. --remove undoes exactly what was installed.

    \b
    Examples:
        indexed install codex            # Register server + skill + hook
        indexed install codex --dry-run  # Show the plan first
        indexed install codex --remove   # Undo, keep everything else
        indexed install codex --home /data --dry-run
    """
    heading = get_heading_style()
    console.print()
    console.print(f"[{heading}]Codex Setup[/{heading}]")
    console.print()

    command = base.resolve_cli_command()
    home_override = Path(home).expanduser().resolve() if home else None
    entry = build_server_entry(command, home_override)
    config_path = codex_config_path()
    hooks_path = codex_hooks_path()
    skill_path = codex_skill_path()
    hook_path = codex_hook_path()
    manifest_path = codex_manifest_path()

    try:
        config_text = (
            config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
        )
        existing = read_toml(config_path)
        hooks_existed = hooks_path.is_file()
        hooks_doc = base.read_config(hooks_path)
        manifest = base.read_config(manifest_path)
        skill_text = "" if remove else read_skill_text()
        hook_text = "" if remove else installed_hook_text(home_override)
        foreign_hook = base.foreign_hook_script(hook_path, hook_text)
    except CodexConfigError as exc:
        print_error(f"Codex config {exc.headline}")
        _print_path("File", exc.path)
        _print_path("Reason", exc.reason)
        raise typer.Exit(1) from exc
    except base.ConfigFileError as exc:
        print_error(f"Codex hooks {exc.headline}")
        _print_path("File", exc.path)
        _print_path("Reason", exc.reason)
        raise typer.Exit(1) from exc
    except (FileNotFoundError, OSError) as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    servers = existing.get("mcp_servers")
    existing_server = servers.get(SERVER_NAME) if isinstance(servers, dict) else None

    if remove:
        changes = _plan_removal(
            config_text=config_text,
            config_path=config_path,
            hooks_doc=hooks_doc,
            hooks_path=hooks_path,
            hook_path=hook_path,
            skill_path=skill_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )
        if not any(change.action != "unchanged" for change in changes):
            print_success("indexed is not installed in Codex - nothing to remove")
            return
        if dry_run:
            console.print(f"[{get_dim_style()}]Would remove:[/{get_dim_style()}]")
            _print_plan(changes)
            console.print(
                f"[{get_dim_style()}]Preview only - nothing was written "
                f"(drop --dry-run to apply).[/{get_dim_style()}]"
            )
            return
        try:
            base.apply_changes(changes)
        except OSError as exc:
            print_error(f"Could not update Codex configuration: {exc}")
            raise typer.Exit(1) from exc
        for change in changes:
            if change.action == "removed":
                _prune_emptied(change.path.parent)
        print_success("Removed indexed from Codex")
        console.print()
        _print_plan(changes)
        console.print()
        console.print(
            f"[{get_dim_style()}]Kept everything else in config.toml and "
            f"hooks.json (a .bak copy of each written file is beside it).[/{get_dim_style()}]"
        )
        return

    if existing_server is not None and existing_server != entry and not force:
        print_error(
            f"{config_path} already registers an {SERVER_TABLE} entry "
            "that points somewhere else."
        )
        _print_path("Existing", json.dumps(existing_server))
        _print_path("Wanted", json.dumps(entry))
        print_warning(
            "Refusing to overwrite it. Re-run with --force to replace it "
            "(a .bak copy of the file is kept)."
        )
        raise typer.Exit(1)

    if foreign_hook is not None and not force:
        print_error(f"{hook_path} already exists and was not written by indexed.")
        _print_path("First line", foreign_hook.splitlines()[0] if foreign_hook else "")
        print_warning(
            "Refusing to replace it. Re-run with --force to install over it "
            "(a .bak copy of the file is kept)."
        )
        raise typer.Exit(1)

    changes = _plan_install(
        config_text=config_text,
        config_path=config_path,
        hooks_doc=hooks_doc,
        hooks_existed=hooks_existed,
        hooks_path=hooks_path,
        hook_path=hook_path,
        skill_path=skill_path,
        manifest_path=manifest_path,
        hook_text=hook_text,
        skill_text=skill_text,
        entry=entry,
    )

    if dry_run:
        console.print(f"[{get_dim_style()}]Would write:[/{get_dim_style()}]")
        _print_plan(changes)
        console.print(
            f"[{get_dim_style()}]Codex trusts a hook only once; this command asks "
            f"Codex for the hook hash and records it, so the nudge runs without "
            f"a first-run approval prompt.[/{get_dim_style()}]"
        )
        console.print(
            f"[{get_dim_style()}]Preview only - nothing was written "
            f"(drop --dry-run to apply).[/{get_dim_style()}]"
        )
        return

    try:
        base.apply_changes(changes)
    except OSError as exc:
        print_error(f"Could not write Codex configuration: {exc}")
        raise typer.Exit(1) from exc

    trust_note = _record_hook_trust(
        hooks_path=hooks_path,
        config_path=config_path,
        manifest_path=manifest_path,
    )

    print_success("Codex is set up for indexed")
    console.print()
    _print_path("Config", config_path)
    _print_path("Server", " ".join(command))
    _print_path("Skill", skill_path)
    _print_path("Hook", hook_path)
    _print_path("Hook registry", hooks_path)
    collections = base.collections_root(home_override)
    _print_path("Collections", collections)
    console.print()
    _report_install(changes, trust_note)
    console.print()
    console.print(
        f"[{get_dim_style()}]Restart Codex; the {SKILL_NAME} skill is available and "
        f"the nudge hook watches Bash search commands.[/{get_dim_style()}]"
    )


def _record_hook_trust(
    *, hooks_path: Path, config_path: Path, manifest_path: Path
) -> str:
    """Ask Codex for our hook's hash and record the trust key; say what happened."""
    hooks_doc = base.read_config(hooks_path)
    index = our_group_index(hooks_doc)
    if index is None:
        return "skipped"
    key = trust_key(hooks_path, index)
    cwd = Path.cwd() if Path.cwd().is_dir() else Path.home()
    trusted_hash = harvest_hook_hash(hooks_path, key, cwd)
    if trusted_hash is None:
        return "unavailable"
    try:
        text = config_path.read_text(encoding="utf-8")
        updated = merge_trust_block(text, key, trusted_hash)
        # No second .bak here: `apply_changes` already backed up the file the
        # user had, and a second copy would overwrite that with our own write.
        base.write_text_atomic(config_path, updated)
        manifest = base.read_config(manifest_path)
        manifest["trust_state"] = key
        base.write_text_atomic(manifest_path, base.dump_config(manifest))
    except (OSError, base.ConfigFileError, CodexConfigError):
        return "failed"
    return "trusted"


def _report_install(changes: Sequence[base.Change], trust_note: str) -> None:
    """Say what changed, in the terms a user can check against their own files."""
    by_label = {change.label: change for change in changes}

    config = by_label.get("Config")
    if config is not None and config.writes:
        console.print("[dim]Registered MCP server 'indexed'.[/dim]")
    else:
        print_warning("MCP server 'indexed' already registered - left unchanged.")

    skill = by_label.get("Skill")
    if skill is not None and skill.writes:
        console.print(f"[dim]Installed the {SKILL_NAME} skill.[/dim]")
    else:
        print_warning(f"The {SKILL_NAME} skill was already up to date.")

    hook_script = by_label.get("Hook script")
    registry = by_label.get("Hook registry")
    changed = (hook_script is not None and hook_script.writes) or (
        registry is not None and registry.writes
    )
    if changed:
        console.print(
            "[dim]Installed the PreToolUse nudge hook (shell search -> MCP search).[/dim]"
        )
    else:
        print_warning("The PreToolUse nudge hook was already up to date.")

    if trust_note == "trusted":
        console.print(
            "[dim]Trusted that hook with Codex (one-time hash recorded).[/dim]"
        )
    elif trust_note == "unavailable":
        print_warning(
            "Codex was not found on PATH, so the hook is not trusted yet - "
            "approve it once in Codex, or re-run this command with Codex installed."
        )
    elif trust_note == "failed":
        print_warning(
            "Could not record the hook trust hash - approve the hook once in Codex."
        )
