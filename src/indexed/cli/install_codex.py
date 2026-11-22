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
import tempfile
import threading
import tomllib
from dataclasses import dataclass
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
    """The hook script as installed, with its collections root baked in.

    The root is inserted as shell-quoted data: a `--home` containing `$`, a
    backtick or `$(…)` must be a literal path, not something the hook expands
    when it runs (with `set -u`, an unexpected `$name` would abort the hook).
    """
    root = base.collections_root(home_override)
    return base.read_payload(HOOK_PAYLOAD).replace(
        COLLECTIONS_PLACEHOLDER, shlex.quote(str(root))
    )


def read_text_raw(path: Path) -> str:
    """Read a file without newline translation, so CRLF stays CRLF."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def write_text_raw_atomic(path: Path, text: str) -> None:
    """`base.write_text_atomic`, but the bytes written are exactly `text`.

    Text mode would translate every `\\n` to the platform's newline, turning a
    CRLF config into CRCRLF on Windows; the contract here is the user's file
    comes back unchanged.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_name).unlink()
        raise


def foreign_skill_text(path: Path, ours: str) -> Optional[str]:
    """Text of an existing skill file this installer did not write, or None."""
    if not path.is_file():
        return None
    try:
        existing = read_text_raw(path)
    except OSError:
        return None
    if existing == ours or base._frontmatter_name(existing) == SKILL_NAME:
        return None
    return existing


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


# A table header, with an optional inline comment, and either `[a]` or `[[a]]`.
# A multiline string that happens to contain a line starting with `[` is the one
# shape line scanning cannot see; every edit is re-parsed afterwards and refused
# if a foreign key would disappear (`_guard_foreign_keys`), so a mis-read can
# only make the command stop, never delete somebody else's table.
_TABLE_LINE = re.compile(r"^\s*\[\[?(?P<key>[^\[\]]+)\]\]?\s*(?:#.*)?$")


def _table_key(line: str) -> Optional[str]:
    """The key of a table header line (inline comments allowed), or None."""
    match = _TABLE_LINE.match(line)
    if match is None:
        return None
    return re.sub(r"\s+", "", match.group("key"))


def _in_table(key: str, target: str) -> bool:
    return key == target or key.startswith(target + ".")


@dataclass(frozen=True)
class _Span:
    """Character range of one table block inside the file's original text."""

    start: int
    end: int


def _line_ending(text: str) -> str:
    """The newline style the file already uses (`\r\n` files stay CRLF)."""
    return "\r\n" if "\r\n" in text else "\n"


def _is_ignorable(line: str) -> bool:
    """A blank or comment-only line: it belongs to whatever comes next."""
    return not line.strip() or line.lstrip().startswith("#")


def _table_span(text: str, target: str) -> Optional[_Span]:
    """The exact character span of `target` and its sub-tables.

    Offsets, not reconstructed lines: everything outside the span is copied
    verbatim, so line endings survive an install/remove round trip. The span
    stops after the block's last key/value line, so a comment the user wrote
    above *their* next table stays theirs.
    """
    offset = 0
    entries: list[tuple[int, str, Optional[str]]] = []
    for raw in text.splitlines(keepends=True):
        entries.append((offset, raw.rstrip("\r\n"), _table_key(raw)))
        offset += len(raw)
    start = None
    end = len(entries)
    for index, (_offset, _line, key) in enumerate(entries):
        if key is None:
            continue
        if _in_table(key, target):
            if start is None:
                start = index
        elif start is not None:
            end = index
            break
    if start is None:
        return None
    while end > start + 1 and _is_ignorable(entries[end - 1][1]):
        end -= 1
    if start > 0 and entries[start - 1][1].strip().startswith(SERVER_MARKER):
        start -= 1
    start_offset = entries[start][0]
    end_offset = entries[end][0] if end < len(entries) else len(text)
    return _Span(start_offset, end_offset)


def _render_block(lines: list[str], text: str) -> str:
    eol = _line_ending(text)
    return eol.join(lines) + eol


def _tail_state(text: str) -> dict[str, Any]:
    """The file's exact trailing newline run, recorded so removal can restore it.

    `"\\n"` for the usual file, `""` for one with no final newline, `"\\r\\n\\r\\n"`
    for a CRLF file ending in a blank line — whatever it was, it comes back.
    """
    return {"suffix": text[len(text.rstrip("\r\n")) :]}


def _restore_tail(text: str, tail: Optional[dict[str, Any]]) -> str:
    """Put the recorded trailing newline run back after our block is gone."""
    if not isinstance(tail, dict) or "suffix" not in tail:
        return text
    suffix = tail["suffix"]
    if not isinstance(suffix, str):
        return text
    return text.rstrip("\r\n") + suffix


def _append_block(text: str, lines: list[str]) -> str:
    eol = _line_ending(text)
    rendered = _render_block(lines, text)
    if not text.strip():
        return rendered
    body = text
    if not body.endswith(("\n", "\r")):
        body += eol
    if not body.endswith(eol + eol):
        body += eol
    return body + rendered


def _remove_block(text: str, target: str) -> str:
    span = _table_span(text, target)
    if span is None:
        return text
    return text[: span.start] + text[span.end :]


def _leaf_paths(data: Any, prefix: str = "") -> set[str]:
    """Every leaf key path in a parsed TOML document."""
    if not isinstance(data, dict):
        return {prefix} if prefix else set()
    paths: set[str] = set()
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            paths |= _leaf_paths(value, path)
        else:
            paths.add(path)
    return paths


def _guard_foreign_keys(
    before: str, after: str, allowed: Sequence[str], path: Path
) -> None:
    """Refuse an edit that would drop a key from someone else's table.

    The editor splices text at computed offsets; this is the independent check
    that the splice did what the offsets claimed. A block that could not be
    identified unambiguously (a multiline string containing a table header, an
    exotic quoting style) fails here instead of taking a foreign key with it.
    """
    if not before.strip():
        return
    original = _leaf_paths(tomllib.loads(before))
    try:
        updated = _leaf_paths(tomllib.loads(after)) if after.strip() else set()
    except tomllib.TOMLDecodeError as exc:  # pragma: no cover - defensive
        raise CodexConfigError(
            path, "could not be edited safely", f"the result would not parse: {exc}"
        ) from exc
    missing = {
        key
        for key in original - updated
        if not any(key == item or key.startswith(item + ".") for item in allowed)
    }
    if missing:  # pragma: no cover - defensive
        raise CodexConfigError(
            path,
            "could not be edited safely",
            "the edit would drop " + ", ".join(sorted(missing)),
        )


def merge_server_block(text: str, entry: dict[str, Any], path: Path) -> str:
    """`text` with our server table set, every other byte preserved."""
    span = _table_span(text, SERVER_TABLE)
    rendered = render_server_table(entry)
    if span is None:
        updated = _append_block(text, rendered)
    else:
        block = _render_block(rendered, text)
        updated = text[: span.start] + block + text[span.end :]
        if not updated.endswith(("\n", "\r")):
            updated += _line_ending(text)
    _guard_foreign_keys(text, updated, [SERVER_TABLE], path)
    return updated


def remove_server_block(text: str, path: Path) -> str:
    """`text` without our server table (marker included), nothing else lost.

    The trailing newline run is restored by the caller once every owned block is
    gone (`_restore_tail`), so a removal that also takes the trust table back
    cannot over-trim between the two deletions.
    """
    updated = _remove_block(text, SERVER_TABLE)
    if updated == text:
        return text
    if updated.strip():
        _guard_foreign_keys(text, updated, [SERVER_TABLE], path)
    return updated


def merge_trust_block(text: str, key: str, trusted_hash: str, path: Path) -> str:
    """`text` with one `hooks.state` entry for our hook, nothing else touched."""
    target = re.sub(r"\s+", "", f"{TRUST_PREFIX}{_toml_string(key)}")
    rendered = render_trust_table(key, trusted_hash)
    span = _table_span(text, target)
    if span is None:
        updated = _append_block(text, rendered)
    else:
        block = _render_block(rendered, text)
        updated = text[: span.start] + block + text[span.end :]
        if not updated.endswith(("\n", "\r")):
            updated += _line_ending(text)
    _guard_foreign_keys(text, updated, [f"{TRUST_PREFIX}{key}"], path)
    return updated


def remove_trust_block(text: str, key: str, path: Path) -> str:
    """`text` without the `hooks.state` entry for `key`, nothing else lost."""
    target = re.sub(r"\s+", "", f"{TRUST_PREFIX}{_toml_string(key)}")
    updated = _remove_block(text, target)
    if updated == text:
        return text
    if updated.strip():
        _guard_foreign_keys(text, updated, [f"{TRUST_PREFIX}{key}"], path)
    return updated


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


def _apply_changes(changes: Sequence[base.Change]) -> None:
    """`base.apply_changes`, but `config.toml` keeps its exact newline bytes.

    Every other artifact is JSON or a script, where text-mode writing is
    harmless; the user's TOML is the one file that must come back unchanged,
    CRLF and missing final newline included.
    """
    base.apply_changes([change for change in changes if change.label != "Config"])
    for change in changes:
        if change.label != "Config" or change.action in ("unchanged", "skipped"):
            continue
        if change.action == "removed":
            if change.keep_backup:
                base.backup_file(change.path)
            with contextlib.suppress(FileNotFoundError):
                change.path.unlink()
            _prune_emptied(change.path.parent)
            continue
        if change.text is None:  # pragma: no cover - defensive
            continue
        base.backup_file(change.path)
        write_text_raw_atomic(change.path, change.text)


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
    config_tail: Optional[dict[str, Any]] = None,
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
        # What appending our block had to add at EOF, so `--remove` can take
        # exactly that back and return the user's file byte for byte.
        "config_tail": config_tail or {},
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
    previous_manifest: Optional[dict[str, Any]] = None,
) -> list[base.Change]:
    """Every artifact an install writes, with what would change about each."""
    merged_hooks = merge_hook_group(hooks_doc, build_hook_group(hook_path))
    merged_config = merge_server_block(config_text, entry, config_path)
    # The tail is recorded by the run that first appended the block and carried
    # forward by every upgrade, or `--remove` could no longer restore the file.
    previous_tail = (
        previous_manifest.get("config_tail")
        if isinstance(previous_manifest, dict)
        else None
    )
    if isinstance(previous_tail, dict) and previous_tail.get("suffix") is not None:
        tail = previous_tail
    elif _table_span(config_text, SERVER_TABLE) is None:
        tail = _tail_state(config_text)
    else:
        tail = None
    manifest = _manifest(config_path, hooks_path, skill_path, hook_path, None, tail)
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
        tail = manifest.get("config_tail") if isinstance(manifest, dict) else None
        remaining = remove_server_block(config_text, config_path)
        trust_values = _trust_keys_to_remove(hooks_doc, hooks_path, manifest)
        for key in trust_values:
            remaining = remove_trust_block(remaining, key, config_path)
        remaining = _restore_tail(remaining, tail)
        # A file that held only comments is still the user's file: only a file
        # we left truly empty is ours to delete.
        if not remaining.strip():
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
        config_text = read_text_raw(config_path) if config_path.is_file() else ""
        existing = read_toml(config_path)
        hooks_existed = hooks_path.is_file()
        hooks_doc = base.read_config(hooks_path)
        manifest = base.read_config(manifest_path)
        skill_text = "" if remove else read_skill_text()
        hook_text = "" if remove else installed_hook_text(home_override)
        foreign_hook = base.foreign_hook_script(hook_path, hook_text)
        foreign_skill = None if remove else foreign_skill_text(skill_path, skill_text)
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
            _apply_changes(changes)
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

    if foreign_skill is not None and not force:
        # A user's own skill directory named index-use is theirs: without this
        # check a routine upgrade silently replaces the file they wrote.
        print_error(f"{skill_path} already exists and was not written by indexed.")
        _print_path(
            "First line", foreign_skill.splitlines()[0] if foreign_skill else ""
        )
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
        previous_manifest=manifest,
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
        _apply_changes(changes)
    except OSError as exc:
        print_error(f"Could not write Codex configuration: {exc}")
        raise typer.Exit(1) from exc

    trust_note = _record_hook_trust(
        hooks_path=hooks_path,
        config_path=config_path,
        manifest_path=manifest_path,
        manifest=_planned_manifest(changes),
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


def _planned_manifest(changes: Sequence[base.Change]) -> dict[str, Any]:
    """The manifest document this install plan wrote, as data."""
    for change in changes:
        if change.label != "Manifest" or not change.text:
            continue
        try:
            data = json.loads(change.text)
        except json.JSONDecodeError:  # pragma: no cover - defensive
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _manifest_with_trust(
    manifest: Optional[dict[str, Any]], manifest_path: Path, key: str
) -> dict[str, Any]:
    """The written manifest plus this trust key, dropping nothing it recorded."""
    document = dict(manifest) if isinstance(manifest, dict) else {}
    if not document:
        document = base.read_config(manifest_path)
    document["trust_state"] = key
    return document


def _record_hook_trust(
    *,
    hooks_path: Path,
    config_path: Path,
    manifest_path: Path,
    manifest: Optional[dict[str, Any]] = None,
) -> str:
    """Ask Codex for our hook's hash and record the trust key; say what happened.

    ``manifest`` is the document the install plan just wrote. The trust state is
    merged into it (rather than into a fresh re-read) so a write here can never
    drop what the plan recorded, ``config_tail`` in particular — that is what
    lets ``--remove`` restore the user's file byte for byte.
    """
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
        # Raw read/write: this is the last writer of config.toml, and a text-mode
        # round trip here would translate a CRLF file to LF after the splice
        # above carefully preserved it.
        text = read_text_raw(config_path)
        updated = merge_trust_block(text, key, trusted_hash, config_path)
        document = _manifest_with_trust(manifest, manifest_path, key)
        # No second .bak here: `apply_changes` already backed up the file the
        # user had, and a second copy would overwrite that with our own write.
        write_text_raw_atomic(config_path, updated)
        base.write_text_atomic(manifest_path, base.dump_config(document))
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
