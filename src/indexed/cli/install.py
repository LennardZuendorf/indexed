"""`indexed install claude-code` — wire indexed into Claude Code, and take it out.

Installs four owned artifacts into the user's home, and removes exactly those
again on `--remove`:

===========================================  =================================
``~/.claude.json`` (``mcpServers.indexed``)  the stdio MCP server entry
``~/.claude/skills/index-use/SKILL.md``      the ``index-use`` skill
``~/.claude/hooks/indexed-suggest-mcp.sh``   the PreToolUse nudge hook
``~/.claude/settings.json`` (hook group)     registers that hook with Claude Code
===========================================  =================================

``~/.claude/indexed-install.json`` records what was installed and by which
package version, so an upgrade is a re-run (owned files are rewritten, the rest
of every file is preserved) and a removal is exact.

Idempotent — safe to run multiple times: an identical entry is reported as
already installed and left untouched, and the rest of each file (other servers,
other hooks, ``projects``, credentials) is preserved.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import sys
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Optional, Sequence

import typer

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

# Must stay "indexed": Claude Code exposes MCP tools as mcp__<server>__<tool>,
# and skills/index-use/SKILL.md documents mcp__indexed__search.
SERVER_NAME = "indexed"
SKILL_NAME = "index-use"
SKILL_PAYLOAD = f"skills/{SKILL_NAME}/SKILL.md"
HOOK_SCRIPT_NAME = "indexed-suggest-mcp.sh"
HOOK_PAYLOAD = f"installers/claude-code/{HOOK_SCRIPT_NAME}"
# Bumped when the shape of the hook/registry contract changes; the manifest
# carries it so a future installer can tell an old install from a current one.
INSTALL_SCHEMA = 1
# Written into the hook script's first line and matched on removal, so a file a
# user put there by hand is never deleted by `--remove`.
HOOK_MARKER = "indexed-install-hook"
HOOK_MATCHER = "Grep|Glob"
MANIFEST_NAME = "indexed-install.json"

app = typer.Typer(help="Install indexed integrations for coding agents")


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def claude_dir() -> Path:
    """User-scope Claude Code directory (``~/.claude``)."""
    return Path.home() / ".claude"


def claude_config_path() -> Path:
    """User-scope MCP config Claude Code reads (`~/.claude.json`)."""
    return Path.home() / ".claude.json"


def claude_settings_path() -> Path:
    """User-scope settings file Claude Code reads (`~/.claude/settings.json`)."""
    return claude_dir() / "settings.json"


def claude_skill_path() -> Path:
    """Where Claude Code reads a personal skill."""
    return claude_dir() / "skills" / SKILL_NAME / "SKILL.md"


def claude_hook_path() -> Path:
    """The nudge hook this installer owns and Claude Code executes."""
    return claude_dir() / "hooks" / HOOK_SCRIPT_NAME


def claude_manifest_path() -> Path:
    """Record of what this installer owns in the user's Claude Code dir."""
    return claude_dir() / MANIFEST_NAME


# --------------------------------------------------------------------------- #
# Payloads (shipped in the wheel, readable from a source checkout)
# --------------------------------------------------------------------------- #
def resolve_cli_command() -> list[str]:
    """Absolute command that starts the MCP server.

    Prefers the console script beside the *running* interpreter (that is the
    install the user just invoked), then any `indexed` on PATH, then
    `python -m indexed.cli.app` — there is no `indexed/__main__.py`.
    """
    candidate = Path(sys.executable).parent / "indexed"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return [str(candidate), "mcp", "run"]
    found = shutil.which("indexed")
    if found:
        return [found, "mcp", "run"]
    return [sys.executable, "-m", "indexed.cli.app", "mcp", "run"]


def build_server_entry(command: list[str], home: Optional[Path]) -> dict[str, Any]:
    """One stdio server entry, in the shape Claude Code writes itself."""
    entry: dict[str, Any] = {
        "type": "stdio",
        "command": command[0],
        "args": list(command[1:]),
    }
    # indexed resolves collections from HOME (~/.indexed/data/collections);
    # an override is carried to the server process as its HOME.
    if home is not None:
        entry["env"] = {"HOME": str(home)}
    return entry


def read_payload(relative: str) -> str:
    """Text of an installer payload: wheel package data, else a source checkout.

    Payloads ship inside the wheel (``pyproject.toml`` ``force-include``); the
    repo-relative branch only serves `uv run` from a checkout.
    """
    try:
        return resources.files("indexed").joinpath(relative).read_text(encoding="utf-8")
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
        pass
    source = Path(__file__).resolve().parents[3] / relative
    if source.is_file():
        return source.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"{relative} not found in the installed package or at {source}"
    )


def read_skill_text() -> str:
    """The `index-use` skill payload."""
    return read_payload(SKILL_PAYLOAD)


def read_hook_text() -> str:
    """The PreToolUse nudge hook payload."""
    return read_payload(HOOK_PAYLOAD)


# --------------------------------------------------------------------------- #
# JSON files
# --------------------------------------------------------------------------- #
class ConfigFileError(ValueError):
    """An unreadable existing config, with the path and the reason kept apart.

    One flat message (``"<path> is not valid JSON: <reason>"``) is rendered as a
    single paragraph, so a long path folds the parser's reason across lines — at
    80 columns the only actionable part of the failure stops being readable and
    stops being greppable (#357). Carrying the parts separately lets the command
    print each one on its own unbroken line.
    """

    def __init__(self, path: Path, headline: str, reason: str) -> None:
        super().__init__(f"{path} {headline}: {reason}")
        self.path = path
        self.headline = headline
        self.reason = reason


def read_config(path: Path) -> dict[str, Any]:
    """Parse an existing config file, or return an empty one."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigFileError(path, "is not valid JSON", str(exc)) from exc
    if not isinstance(data, dict):
        raise ConfigFileError(
            path,
            "does not hold a JSON object",
            f"the top-level value is a {type(data).__name__}",
        )
    return data


def dump_config(data: dict[str, Any]) -> str:
    """The on-disk form every config this command writes uses."""
    return json.dumps(data, indent=2) + "\n"


def write_text_atomic(path: Path, text: str) -> None:
    """Write a file atomically (temp file in the same dir, then os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_name).unlink()
        raise


# --------------------------------------------------------------------------- #
# Merging our entries into files the user also owns
# --------------------------------------------------------------------------- #
def merge_server_entry(
    existing: dict[str, Any], name: str, entry: dict[str, Any]
) -> dict[str, Any]:
    """Return `existing` with `mcpServers[name]` set, every other key intact."""
    merged = dict(existing)
    servers = merged.get("mcpServers")
    servers = dict(servers) if isinstance(servers, dict) else {}
    servers[name] = entry
    merged["mcpServers"] = servers
    return merged


def remove_server_entry(existing: dict[str, Any], name: str) -> dict[str, Any]:
    """Return `existing` without `mcpServers[name]`; empty containers are dropped.

    ``mcpServers`` disappearing once its last server is gone keeps a removal from
    leaving an empty object behind as a trace of us.
    """
    merged = dict(existing)
    servers = merged.get("mcpServers")
    if not isinstance(servers, dict) or name not in servers:
        return merged
    servers = {key: value for key, value in servers.items() if key != name}
    if servers:
        merged["mcpServers"] = servers
    else:
        merged.pop("mcpServers", None)
    return merged


def server_entry_is_ours(entry: object) -> bool:
    """True when an ``mcpServers.indexed`` entry points at this CLI.

    Used by ``--remove``: a user who registered *their own* server named
    ``indexed`` (a different command) keeps it.
    """
    if not isinstance(entry, dict):
        return False
    command = entry.get("command")
    args = entry.get("args")
    if not isinstance(command, str):
        return False
    if Path(command).name != "indexed" and not command.endswith("indexed"):
        return False
    return args in (["mcp", "run"], ["mcp"])


def build_hook_group(hook_path: Path) -> dict[str, Any]:
    """The PreToolUse group that runs our nudge hook for Grep/Glob."""
    return {
        "matcher": HOOK_MATCHER,
        "hooks": [{"type": "command", "command": str(hook_path), "timeout": 10}],
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
    """True when a PreToolUse group runs the script this installer owns.

    Matched on the script's basename (after unquoting) rather than marker text,
    so a group the user re-pointed elsewhere, or added with a different matcher,
    is left for them.
    """
    command = _hook_command(group)
    if not command:
        return False
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    return bool(parts) and Path(parts[0]).name == HOOK_SCRIPT_NAME


def merge_hook_group(existing: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    """Return `existing` settings with our PreToolUse group set, nothing else lost.

    Our group is replaced in place when already present, so re-running the
    installer cannot accumulate duplicates and cannot reorder the user's other
    hook groups.
    """
    merged = dict(existing)
    hooks = merged.get("hooks")
    hooks = dict(hooks) if isinstance(hooks, dict) else {}
    groups = hooks.get("PreToolUse")
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
    hooks["PreToolUse"] = out
    merged["hooks"] = hooks
    return merged


def remove_hook_group(existing: dict[str, Any]) -> dict[str, Any]:
    """Return `existing` settings without our hook group; empty containers go."""
    merged = dict(existing)
    hooks = merged.get("hooks")
    if not isinstance(hooks, dict):
        return merged
    hooks = dict(hooks)
    groups = hooks.get("PreToolUse")
    if isinstance(groups, list):
        kept = [group for group in groups if not hook_group_is_ours(group)]
        if kept:
            hooks["PreToolUse"] = kept
        else:
            hooks.pop("PreToolUse", None)
    if hooks:
        merged["hooks"] = hooks
    else:
        merged.pop("hooks", None)
    return merged


# --------------------------------------------------------------------------- #
# Change planning
# --------------------------------------------------------------------------- #
@dataclass
class Change:
    """One owned artifact the command will write, leave alone, or delete."""

    label: str
    path: Path
    action: str  # created | updated | unchanged | removed | skipped
    text: Optional[str] = None  # None on removals: delete the file
    executable: bool = False  # hook scripts are run by Claude Code, so +x
    # Generated payloads are regenerated on the next install, so a removal does
    # not litter the user's directory with .bak copies of them; a config the
    # user may have edited always keeps a backup.
    keep_backup: bool = True

    @property
    def writes(self) -> bool:
        return self.action in ("created", "updated")


def _file_change(
    label: str, path: Path, text: str, *, executable: bool = False
) -> Change:
    """Plan a whole-file write, reporting whether anything actually changes."""
    if not path.is_file():
        return Change(label, path, "created", text, executable)
    try:
        current = path.read_text(encoding="utf-8")
        mode = path.stat().st_mode
    except OSError:
        return Change(label, path, "updated", text, executable)
    if current != text:
        return Change(label, path, "updated", text, executable)
    # A script Claude Code executes must stay executable; a copy that lost its
    # mode is not "already current" even though the bytes match.
    if executable and not mode & 0o100:
        return Change(label, path, "updated", text, executable)
    return Change(label, path, "unchanged", text, executable)


def _json_change(
    label: str,
    path: Path,
    data: dict[str, Any],
    existing: dict[str, Any],
    had_file: bool,
) -> Change:
    """Plan a config write, comparing documents so key order cannot churn."""
    if had_file and data == existing:
        return Change(label, path, "unchanged", dump_config(data))
    return Change(
        label, path, "created" if not had_file else "updated", dump_config(data)
    )


def _deletion(label: str, path: Path, *, keep_backup: bool = True) -> Change:
    return Change(label, path, "removed", None, keep_backup=keep_backup)


def backup_file(path: Path) -> Optional[Path]:
    """Copy `path` beside itself as `<name>.bak` before it is overwritten."""
    if not path.exists():
        return None
    backup = path.with_name(path.name + ".bak")
    shutil.copy2(path, backup)
    return backup


def apply_changes(changes: Sequence[Change]) -> None:
    """Write or delete every non-unchanged artifact, keeping a .bak of each."""
    for change in changes:
        if change.action == "unchanged" or change.action == "skipped":
            continue
        if change.action == "removed":
            if change.keep_backup:
                backup_file(change.path)
            with contextlib.suppress(FileNotFoundError):
                change.path.unlink()
            _prune_empty_dirs(change.path.parent)
            continue
        if change.text is None:  # pragma: no cover - defensive
            continue
        backup_file(change.path)
        write_text_atomic(change.path, change.text)
        if change.executable:
            change.path.chmod(0o755)


def _prune_empty_dirs(directory: Path) -> None:
    """Remove `directory` (and its parent) when we emptied it, never further."""
    stop = claude_dir()
    current = directory
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _print_path(label: str, value: object) -> None:
    label_style = get_label_style()
    dim = get_dim_style()
    console.print(f"  [{label_style}]{label}[/{label_style}]")
    console.print(render_user_text(value, style=dim), soft_wrap=True)


def _print_plan(changes: Sequence[Change]) -> None:
    """Print one line per artifact the command will touch."""
    for change in changes:
        if change.action == "unchanged":
            _print_path(change.label, f"{change.path} (already current)")
        elif change.action == "skipped":
            _print_path(change.label, f"{change.path} (not ours - left alone)")
        else:
            _print_path(change.label, f"{change.path} ({change.action})")


def _print_preview(
    config_path: Path,
    entry: dict[str, Any],
    changes: Sequence[Change],
    existing_server: Optional[dict[str, Any]],
    removing: bool,
) -> None:
    dim = get_dim_style()
    verb = "remove" if removing else "write"
    console.print(f"[{dim}]Would {verb}:[/{dim}]")
    _print_path("Config", config_path)
    command = entry.get("command")
    args = entry.get("args") or []
    line = " ".join(str(part) for part in [command, *args])
    _print_path(f"Server ({SERVER_NAME})", line)
    if existing_server is not None and existing_server != entry and not removing:
        print_warning(
            f"An existing mcpServers.{SERVER_NAME} entry would be replaced "
            f"(a .bak copy of {config_path.name} is kept)."
        )
    console.print(
        f"[{dim}]Other keys in that file - projects, credentials, other servers - "
        f"are preserved and are deliberately not printed here.[/{dim}]"
    )
    _print_plan(changes)
    console.print(
        f"[{dim}]Preview only - nothing was written (drop --dry-run to apply).[/{dim}]"
    )


# --------------------------------------------------------------------------- #
# The command
# --------------------------------------------------------------------------- #
@app.command("claude-code")
def claude_code(
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
        help="Replace an existing mcpServers.indexed entry that points elsewhere.",
    ),
    remove: bool = typer.Option(
        False,
        "--remove",
        help="Remove everything this installer added, leaving the rest of your "
        "configuration untouched.",
    ),
) -> None:
    """Register the indexed MCP server, skill and search hook with Claude Code.

    Writes the user-scope MCP registration into ~/.claude.json, the index-use
    skill into ~/.claude/skills, and a PreToolUse nudge hook into
    ~/.claude/settings.json (other servers, hooks and settings are preserved).
    Safe to run again: an existing install is upgraded in place, never
    duplicated. --remove undoes exactly what was installed.

    \b
    Examples:
        indexed install claude-code            # Register server + skill + hook
        indexed install claude-code --dry-run  # Show the plan first
        indexed install claude-code --remove   # Undo, keep everything else
        indexed install claude-code --home /data --dry-run
    """
    heading = get_heading_style()
    console.print()
    console.print(f"[{heading}]Claude Code Setup[/{heading}]")
    console.print()

    command = resolve_cli_command()
    home_override = Path(home).expanduser().resolve() if home else None
    entry = build_server_entry(command, home_override)
    config_path = claude_config_path()
    settings_path = claude_settings_path()
    skill_path = claude_skill_path()
    hook_path = claude_hook_path()
    manifest_path = claude_manifest_path()

    try:
        existing = read_config(config_path)
        settings_existed = settings_path.is_file()
        settings = read_config(settings_path)
        skill_text = "" if remove else read_skill_text()
        hook_text = "" if remove else read_hook_text()
    except ConfigFileError as exc:
        # The reason is the only actionable part of this failure: print it (and
        # the path) on their own unbroken lines rather than folding both into the
        # panel paragraph, where an 80-column terminal used to split the reason
        # mid-phrase (#357).
        print_error(f"Claude Code config {exc.headline}")
        _print_path("File", exc.path)
        _print_path("Reason", exc.reason)
        raise typer.Exit(1) from exc
    except (FileNotFoundError, OSError) as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    servers = existing.get("mcpServers")
    existing_server = servers.get(SERVER_NAME) if isinstance(servers, dict) else None

    if remove:
        changes = _plan_removal(
            existing=existing,
            settings=settings,
            settings_existed=settings_existed,
            config_path=config_path,
            settings_path=settings_path,
            skill_path=skill_path,
            hook_path=hook_path,
            manifest_path=manifest_path,
        )
        if not any(change.action != "unchanged" for change in changes):
            print_success("indexed is not installed in Claude Code - nothing to remove")
            return
        if dry_run:
            _print_preview(config_path, entry, changes, existing_server, removing=True)
            return
        try:
            apply_changes(changes)
        except OSError as exc:
            print_error(f"Could not update Claude Code configuration: {exc}")
            raise typer.Exit(1) from exc
        print_success("Removed indexed from Claude Code")
        console.print()
        _print_plan(changes)
        console.print()
        console.print(
            f"[{get_dim_style()}]Kept everything else in {config_path.name} and "
            f"{settings_path.name} (a .bak copy of each written file is beside it)."
            f"[/{get_dim_style()}]"
        )
        return

    if existing_server is not None and existing_server != entry and not force:
        print_error(
            f"{config_path} already registers an mcpServers.{SERVER_NAME} entry "
            "that points somewhere else."
        )
        _print_path("Existing", json.dumps(existing_server))
        _print_path("Wanted", json.dumps(entry))
        print_warning(
            "Refusing to overwrite it. Re-run with --force to replace it "
            "(a .bak copy of the file is kept)."
        )
        raise typer.Exit(1)

    changes = _plan_install(
        existing=existing,
        settings=settings,
        settings_existed=settings_existed,
        entry=entry,
        config_path=config_path,
        settings_path=settings_path,
        skill_path=skill_path,
        hook_path=hook_path,
        manifest_path=manifest_path,
        skill_text=skill_text,
        hook_text=hook_text,
    )

    if dry_run:
        _print_preview(config_path, entry, changes, existing_server, removing=False)
        return

    try:
        apply_changes(changes)
    except OSError as exc:
        print_error(f"Could not write Claude Code configuration: {exc}")
        raise typer.Exit(1) from exc

    by_label = {change.label: change for change in changes}
    print_success("Claude Code is set up for indexed")
    console.print()
    _print_path("Config", config_path)
    _print_path("Server", " ".join(command))
    _print_path("Skill", skill_path)
    _print_path("Hook", hook_path)
    _print_path("Settings", settings_path)
    collections = (home_override or Path.home()) / ".indexed" / "data" / "collections"
    _print_path("Collections", collections)
    console.print()
    _report_install(by_label)
    console.print()
    console.print(
        f"[{get_dim_style()}]Restart Claude Code, then run /{SKILL_NAME}.[/{get_dim_style()}]"
    )


def _plan_install(
    *,
    existing: dict[str, Any],
    settings: dict[str, Any],
    settings_existed: bool,
    entry: dict[str, Any],
    config_path: Path,
    settings_path: Path,
    skill_path: Path,
    hook_path: Path,
    manifest_path: Path,
    skill_text: str,
    hook_text: str,
) -> list[Change]:
    """Every artifact an install writes, with what would change about each."""
    merged_servers = merge_server_entry(existing, SERVER_NAME, entry)
    merged_settings = merge_hook_group(settings, build_hook_group(hook_path))
    manifest = {
        "schema": INSTALL_SCHEMA,
        "package_version": installed_version(),
        "server": {"file": str(config_path), "key": f"mcpServers.{SERVER_NAME}"},
        "skill": str(skill_path),
        "hook": str(hook_path),
        "settings": {"file": str(settings_path), "key": "hooks.PreToolUse"},
    }
    return [
        _json_change(
            "Config", config_path, merged_servers, existing, config_path.is_file()
        ),
        _file_change("Hook script", hook_path, hook_text, executable=True),
        _json_change(
            "Settings", settings_path, merged_settings, settings, settings_existed
        ),
        _file_change("Skill", skill_path, skill_text),
        _file_change("Manifest", manifest_path, dump_config(manifest)),
    ]


def _plan_removal(
    *,
    existing: dict[str, Any],
    settings: dict[str, Any],
    settings_existed: bool,
    config_path: Path,
    settings_path: Path,
    skill_path: Path,
    hook_path: Path,
    manifest_path: Path,
) -> list[Change]:
    """Every artifact a removal touches, with what would change about each."""
    changes: list[Change] = []

    servers = existing.get("mcpServers")
    ours_server = servers.get(SERVER_NAME) if isinstance(servers, dict) else None
    if ours_server is None:
        changes.append(Change("Config", config_path, "unchanged"))
    elif not server_entry_is_ours(ours_server):
        changes.append(Change("Config", config_path, "skipped"))
    else:
        remaining = remove_server_entry(existing, SERVER_NAME)
        if remaining:
            changes.append(
                _json_change("Config", config_path, remaining, existing, True)
            )
        else:
            changes.append(_deletion("Config", config_path))

    merged_settings = remove_hook_group(settings)
    if merged_settings == settings:
        changes.append(Change("Settings", settings_path, "unchanged"))
    elif not merged_settings and settings_existed:
        changes.append(_deletion("Settings", settings_path))
    else:
        changes.append(
            _json_change("Settings", settings_path, merged_settings, settings, True)
        )

    changes.append(
        _owned_file_removal("Hook script", hook_path, HOOK_MARKER, keep_backup=False)
    )
    changes.append(
        _owned_file_removal(
            "Skill", skill_path, f"name: {SKILL_NAME}", keep_backup=False
        )
    )
    changes.append(
        _deletion("Manifest", manifest_path, keep_backup=False)
        if manifest_path.is_file()
        else Change("Manifest", manifest_path, "unchanged")
    )
    return changes


def _owned_file_removal(
    label: str, path: Path, marker: str, *, keep_backup: bool = True
) -> Change:
    """Plan a file deletion only when the file carries our marker."""
    if not path.is_file():
        return Change(label, path, "unchanged")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return Change(label, path, "skipped")
    if marker not in text:
        return Change(label, path, "skipped")
    return _deletion(label, path, keep_backup=keep_backup)


def _report_install(by_label: dict[str, Change]) -> None:
    """Say what changed, in the terms a user can check against their own files."""
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

    hook = by_label.get("Hook script")
    settings = by_label.get("Settings")
    hook_current = hook is not None and hook.writes
    settings_current = settings is not None and settings.writes
    if hook_current or settings_current:
        console.print(
            "[dim]Installed the PreToolUse search hook (Grep/Glob \u2192 MCP search).[/dim]"
        )
    else:
        print_warning("The PreToolUse search hook was already up to date.")
