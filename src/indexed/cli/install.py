"""`indexed install claude-code` — wire indexed into Claude Code.

Registers the MCP server in the file Claude Code reads for *user* scope
(`~/.claude.json`, top-level `mcpServers`) and installs the `index-use` skill
into `~/.claude/skills/index-use/SKILL.md`.

Idempotent — safe to run multiple times: an identical entry is reported as
already installed and left untouched, and the rest of `~/.claude.json` (other
servers, `projects`, credentials) is preserved.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any, List, Optional

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

# Must stay "indexed": Claude Code exposes MCP tools as mcp__<server>__<tool>,
# and skills/index-use/SKILL.md documents mcp__indexed__search.
SERVER_NAME = "indexed"
SKILL_NAME = "index-use"
SKILL_RELATIVE = f"skills/{SKILL_NAME}"

app = typer.Typer(help="Install indexed integrations for coding agents")


def claude_config_path() -> Path:
    """User-scope MCP config Claude Code reads (`~/.claude.json`)."""
    return Path.home() / ".claude.json"


def claude_skill_path() -> Path:
    """Where Claude Code reads a personal skill."""
    return Path.home() / ".claude" / "skills" / SKILL_NAME / "SKILL.md"


def resolve_cli_command() -> List[str]:
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


def build_server_entry(command: List[str], home: Optional[Path]) -> dict[str, Any]:
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


def write_config(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically (temp file in the same dir, then os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_name).unlink()
        raise


def read_skill_text() -> str:
    """The `index-use` skill, from the installed package or a source checkout.

    The skill ships as package data (`indexed/skills/index-use/SKILL.md`, see
    pyproject wheel `force-include`); the repo-relative branch only serves
    `uv run` from a checkout.
    """
    try:
        return (
            resources.files("indexed")
            .joinpath(SKILL_RELATIVE, "SKILL.md")
            .read_text(encoding="utf-8")
        )
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
        pass
    source = Path(__file__).resolve().parents[3] / SKILL_RELATIVE / "SKILL.md"
    if source.is_file():
        return source.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"{SKILL_NAME} skill not found in the installed package or at {source}"
    )


def _print_path(label: str, value: object) -> None:
    label_style = get_label_style()
    dim = get_dim_style()
    console.print(f"  [{label_style}]{label}[/{label_style}]")
    console.print(render_user_text(value, style=dim), soft_wrap=True)


def backup_file(path: Path) -> Optional[Path]:
    """Copy `path` beside itself as `<name>.bak` before it is overwritten."""
    if not path.exists():
        return None
    backup = path.with_name(path.name + ".bak")
    shutil.copy2(path, backup)
    return backup


def _print_preview(
    config_path: Path,
    entry: dict[str, Any],
    skill_path: Path,
    existing_server: Optional[dict[str, Any]],
) -> None:
    dim = get_dim_style()
    console.print(f"[{dim}]Would write:[/{dim}]")
    _print_path("Config", config_path)
    command = entry.get("command")
    args = entry.get("args") or []
    line = " ".join(str(part) for part in [command, *args])
    _print_path(f"Server ({SERVER_NAME})", line)
    if existing_server is not None and existing_server != entry:
        print_warning(
            f"An existing mcpServers.{SERVER_NAME} entry would be replaced "
            f"(a .bak copy of {config_path.name} is kept)."
        )
    console.print(
        f"[{dim}]Other keys in that file — projects, credentials, other servers — "
        f"are preserved and are deliberately not printed here.[/{dim}]"
    )
    _print_path("Skill", skill_path)
    console.print(
        f"[{dim}]Preview only - nothing was written (drop --dry-run to apply).[/{dim}]"
    )


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
) -> None:
    """Register the indexed MCP server and skill with Claude Code.

    Writes the user-scope MCP registration into ~/.claude.json (other servers
    are preserved) and installs the index-use skill into ~/.claude/skills.
    Safe to run again: nothing is duplicated.

    \b
    Examples:
        indexed install claude-code            # Register server + skill
        indexed install claude-code --dry-run  # Show the config first
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
    skill_path = claude_skill_path()

    try:
        existing = read_config(config_path)
        skill_text = read_skill_text()
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

    merged = merge_server_entry(existing, SERVER_NAME, entry)

    if dry_run:
        _print_preview(config_path, entry, skill_path, existing_server)
        return

    config_changed = merged != existing
    skill_written = False
    try:
        if config_changed:
            backup_file(config_path)
            write_config(config_path, merged)
        skill_differs = (
            not skill_path.is_file()
            or skill_path.read_text(encoding="utf-8") != skill_text
        )
        if skill_differs:
            backup_file(skill_path)
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(skill_text, encoding="utf-8")
            skill_written = True
        else:
            skill_written = False
    except OSError as exc:
        print_error(f"Could not write Claude Code configuration: {exc}")
        raise typer.Exit(1) from exc

    print_success("Claude Code is set up for indexed")
    console.print()
    _print_path("Config", config_path)
    _print_path("Server", " ".join(command))
    _print_path("Skill", skill_path)
    collections = (home_override or Path.home()) / ".indexed" / "data" / "collections"
    _print_path("Collections", collections)
    console.print()

    if config_changed:
        console.print("[dim]Registered MCP server 'indexed'.[/dim]")
    else:
        print_warning("MCP server 'indexed' already registered - left unchanged.")
    if skill_written:
        console.print(f"[dim]Installed the {SKILL_NAME} skill.[/dim]")
    else:
        print_warning(f"The {SKILL_NAME} skill was already up to date.")

    console.print()
    console.print(
        f"[{get_dim_style()}]Restart Claude Code, then run /{SKILL_NAME}.[/{get_dim_style()}]"
    )
