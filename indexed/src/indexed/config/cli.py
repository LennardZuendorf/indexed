"""Config command for managing index configuration."""

import json
from typing import Any

import typer

from indexed_config import ConfigService

app = typer.Typer(help="Manage configuration")


def _coerce_value(value: str) -> Any:
    # Try int, float, bool, JSON (list/dict), else keep string
    low = value.lower()
    if low in {"true", "false"}:
        return low == "true"
    try:
        if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            return int(value)
        f = float(value)
        return f
    except Exception:
        pass
    try:
        return json.loads(value)
    except Exception:
        return value


@app.command("inspect")
def inspect():
    """Display merged configuration (global + workspace + env)."""
    svc = ConfigService.instance()
    raw = svc.load_raw()
    typer.echo(json.dumps(raw, indent=2, ensure_ascii=False))


@app.command("init")
def init():
    """Initialize workspace configuration file (no profiles)."""
    svc = ConfigService.instance()
    raw = svc.load_raw()  # start from merged; write as-is to workspace
    svc.save_raw(raw or {})
    typer.echo("✓ Workspace configuration initialized (.indexed/config.toml)")


@app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Dot path (e.g., core.v1.indexing.chunk_size)"),
    value: str = typer.Argument(..., help="Value (auto-coerced)"),
):
    """Set a configuration value at dot-path in workspace config."""
    svc = ConfigService.instance()
    coerced = _coerce_value(value)
    try:
        svc.set(key, coerced)
        # Re-validate affected specs (best-effort)
        errs = svc.validate()
        if errs:
            typer.echo("⚠️  Validation issues detected:")
            for path, msg in errs:
                typer.echo(f"  • {path}: {msg}")
        typer.echo(f"✓ Set {key} = {value}")
    except Exception as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("delete")
def delete_config(key: str = typer.Argument(..., help="Dot path to delete")):
    """Delete a configuration key from workspace config."""
    svc = ConfigService.instance()
    if svc.delete(key):
        typer.echo(f"✓ Deleted {key}")
    else:
        typer.echo(f"ℹ️  Key not found: {key}")


@app.command("validate")
def validate():
    """Validate current configuration against registered specs."""
    svc = ConfigService.instance()
    errs = svc.validate()
    if errs:
        typer.echo("❌ Configuration validation failed:")
        for path, msg in errs:
            typer.echo(f"  • {path}: {msg}")
        raise typer.Exit(1)
    typer.echo("✓ Configuration is valid")
