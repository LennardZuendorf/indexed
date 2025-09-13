"""Config command group for managing indexed.toml configuration."""

import json
from typing import Any, Dict, Optional, List, Tuple

import os
from pathlib import Path
import typer
from main.services import ConfigService
from main.config.store import read_toml
from main.config.settings import (
    IndexedSettings,
)
from pydantic import BaseModel
from cli.utils.config_format import ConfigSection, format_config_full, format_config_section, format_config_value


config_app = typer.Typer(help="Manage indexed.toml configuration")


# --- simple styling helpers (ANSI) ---
COLORS = {
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "magenta": "\033[35m",
    "blue": "\033[34m",
    "gray": "\033[90m",
}
RESET = "\033[0m"
BOLD = "\033[1m"


def bold(text: str) -> str:
    return f"{BOLD}{text}{RESET}"


def color(text: str, name: str | None) -> str:
    if not name:
        return text
    return f"{COLORS.get(name, '')}{text}{RESET}"


def status_style(status: str) -> tuple[str, str, str]:
    s = status.lower()
    if s == "ready":
        return ("✅", "green", status)
    if s.startswith("partially"):
        return ("🟡", "yellow", status)
    return ("⛔", "red", status)


def _parse_dot_path(key: str) -> list[str]:
    """Parse dot-separated key path into list of keys."""
    return key.split(".")


def _auto_type_value(value: str) -> Any:
    """Auto-detect and convert string value to appropriate type."""
    # Try boolean
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    
    # Try integer
    try:
        return int(value)
    except ValueError:
        pass
    
    # Try float
    try:
        return float(value)
    except ValueError:
        pass
    
    # Return as string
    return value


def _parse_json_value(value: str) -> Any:
    """Parse JSON string value."""
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        typer.echo(f"Error: Invalid JSON value: {e}", err=True)
        raise typer.Exit(1)


def _is_secret_key(key: str) -> bool:
    """Check if a key path represents a secret field."""
    secret_keywords = ["password", "token", "secret", "key", "credential"]
    key_lower = key.lower()
    return any(keyword in key_lower for keyword in secret_keywords) and not key_lower.endswith("_env")


def _dotenv_get(name: str) -> Optional[str]:
    """Get var from environment or .env without exporting."""
    val = os.getenv(name)
    if val is not None:
        return val
    env_path = Path(".env")
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, v = line.split("=", 1)
        key = key.strip()
        if key == name:
            return v.strip().strip('"').strip("'")
    return None


def _collect_unknowns(data: Dict[str, Any], model: type[BaseModel], path: str = "") -> List[str]:
    unknown: List[str] = []
    if not isinstance(data, dict):
        return unknown
    model_fields = getattr(model, "model_fields", {})
    allowed = set(model_fields.keys())
    for key, value in data.items():
        current_path = f"{path}.{key}" if path else key
        if key not in allowed:
            # Unknown field under this model
            try:
                rendered = json.dumps(value)
            except Exception:
                rendered = repr(value)
            unknown.append(f"{current_path} = {rendered}")
            continue
        # Recurse into nested models
        field = model_fields[key]
        sub_model = field.annotation
        try:
            if isinstance(value, dict) and issubclass(sub_model, BaseModel):
                unknown.extend(_collect_unknowns(value, sub_model, current_path))
        except TypeError:
            # Not a BaseModel type
            pass
    return unknown


# --- Origin tracking helpers ---

def _build_merged_toml_for_profile(profile: Optional[str]) -> Dict[str, Any]:
    """Return the TOML data as it would be applied for a profile (base + overlay)."""
    toml = read_toml()
    if not toml:
        return {}
    if not profile:
        return {k: v for k, v in toml.items() if k != "profiles"}
    base = {k: v for k, v in toml.items() if k != "profiles"}
    overlay = toml.get("profiles", {}).get(profile, {})
    # Deep-merge overlay into base
    def merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        res = dict(a)
        for k, v in b.items():
            if k in res and isinstance(res[k], dict) and isinstance(v, dict):
                res[k] = merge(res[k], v)
            else:
                res[k] = v
        return res
    return merge(base, overlay)


def _flatten_paths(data: Any, prefix: Tuple[str, ...] = ()) -> List[Tuple[Tuple[str, ...], Any]]:
    """Flatten a nested mapping into list of (path_tuple, value) for leaves."""
    items: List[Tuple[Tuple[str, ...], Any]] = []
    if isinstance(data, dict):
        for k, v in data.items():
            items.extend(_flatten_paths(v, prefix + (k,)))
    else:
        items.append((prefix, data))
    return items


def _has_toml_key(toml_data: Dict[str, Any], path: Tuple[str, ...]) -> bool:
    cur: Any = toml_data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return False
        cur = cur[key]
    return True


def _env_var_name_for_path(path: Tuple[str, ...]) -> str:
    return "INDEXED__" + "__".join(p.upper() for p in path)


def _build_origin_map(effective: Dict[str, Any], profile: Optional[str]) -> Dict[str, Any]:
    """Build a nested map mirroring `effective` where leaf values are one of: 'env' | 'toml' | 'default'."""
    toml_merged = _build_merged_toml_for_profile(profile)

    def build(node: Any, path: Tuple[str, ...]) -> Any:
        if isinstance(node, dict):
            return {k: build(v, path + (k,)) for k, v in node.items()}
        # Leaf: decide origin by precedence
        env_name = _env_var_name_for_path(path)
        if _dotenv_get(env_name) is not None:
            return "env"
        if _has_toml_key(toml_merged, path):
            return "toml"
        return "default"

    return build(effective, tuple())


# Origin badges

def _origin_badge(origin: Optional[str]) -> str:
    if origin == "env":
        return color("[env]", "cyan")
    if origin == "toml":
        return color("[toml]", "magenta")
    return color("[default]", "gray")


def _to_nested_dict(keys: List[str], value: Any) -> Dict[str, Any]:
    """Build a nested dict from a list of keys setting the final value."""
    result: Dict[str, Any] = {}
    cursor = result
    for key in keys[:-1]:
        next_level: Dict[str, Any] = {}
        cursor[key] = next_level
        cursor = next_level
    cursor[keys[-1]] = value
    return result


def _get_from_mapping(mapping: Dict[str, Any], keys: List[str]) -> Any:
    current: Any = mapping
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            raise KeyError(".".join(keys))
    return current


def _render_json(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except Exception:
        return str(value)


def _echo_multiline(label: str, content: str, indent: int = 2) -> None:
    spaces = " " * indent
    lines = content.splitlines() or [content]
    if len(lines) == 1:
        typer.echo(f"{spaces}{label} {lines[0]}")
        return
    typer.echo(f"{spaces}{label}")
    for line in lines:
        typer.echo(f"{spaces}  {line}")


def _print_configuration_summary(settings: IndexedSettings, profile: Optional[str]) -> None:
    typer.echo(bold("⚙️  Configuration"))
    typer.echo(f"  Profile: {bold(profile) if profile else 'Default'}")
    try:
        src = settings.sources
        ready_count = int(src.files.is_ready) + int(src.jira_cloud.is_ready) + int(src.confluence_cloud.is_ready)
        typer.echo(f"  Sources ready: {bold(str(ready_count))}/3")
    except Exception:
        pass
    typer.echo()


def _print_section_json(title: str, payload: Any) -> None:
    typer.echo(bold(title))
    rendered = _render_json(payload)
    for line in rendered.splitlines():
        typer.echo(f"  {line}")
    typer.echo()


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        inner = ", ".join(_stringify(v) for v in value)
        return f"[{inner}]"
    return str(value)


def _print_kv_section(title: str, emoji: str, section: Dict[str, Any], origin_map: Optional[Dict[str, Any]] = None) -> None:
    typer.echo(bold(f"{emoji} {title}:"))
    # Stable order
    for key in sorted(section.keys()):
        origin = None
        if origin_map and isinstance(origin_map.get(key), (str, dict)):
            # Leaf values should be str; if dict, we won't append badge here
            leaf = origin_map.get(key)
            origin = leaf if isinstance(leaf, str) else None
        badge = f" { _origin_badge(origin) }" if origin else ""
        typer.echo(f"  - {key}: {_stringify(section[key])}{badge}")
    typer.echo()


def _print_sources_section(sources: Dict[str, Any], origins: Optional[Dict[str, Any]] = None) -> None:
    typer.echo(bold("🌐 Sources:"))
    # Files
    if isinstance(sources.get("files"), dict):
        typer.echo(f"  - {bold('📂 Files:')}")
        for key in sorted(sources["files"].keys()):
            origin_map = None
            if origins and isinstance(origins.get("files"), dict):
                leaf = origins["files"].get(key)
                origin_map = leaf if isinstance(leaf, str) else None
            badge = f" { _origin_badge(origin_map) }" if origin_map else ""
            typer.echo(f"      - {key}: {_stringify(sources['files'][key])}{badge}")
    # Jira Cloud
    if isinstance(sources.get("jira_cloud"), dict):
        typer.echo(f"  - {bold('🧩 Jira Cloud:')}")
        for key in sorted(sources["jira_cloud"].keys()):
            origin_map = None
            if origins and isinstance(origins.get("jira_cloud"), dict):
                leaf = origins["jira_cloud"].get(key)
                origin_map = leaf if isinstance(leaf, str) else None
            badge = f" { _origin_badge(origin_map) }" if origin_map else ""
            typer.echo(f"      - {key}: {_stringify(sources['jira_cloud'][key])}{badge}")
    # Confluence Cloud
    if isinstance(sources.get("confluence_cloud"), dict):
        typer.echo(f"  - {bold('📘 Confluence Cloud:')}")
        for key in sorted(sources["confluence_cloud"].keys()):
            origin_map = None
            if origins and isinstance(origins.get("confluence_cloud"), dict):
                leaf = origins["confluence_cloud"].get(key)
                origin_map = leaf if isinstance(leaf, str) else None
            badge = f" { _origin_badge(origin_map) }" if origin_map else ""
            typer.echo(f"      - {key}: {_stringify(sources['confluence_cloud'][key])}{badge}")
    typer.echo()


@config_app.command("get")
def get_value(
    key: str = typer.Argument("all", help="Key to read: 'all' for full config, section name (e.g. 'flags'), or dot-path (e.g. 'sources.files.base_path')"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Use specific profile"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON value"),
) -> None:
    """Get configuration values. Use 'all' for full config, section names, or dot-paths for specific values."""
    try:
        settings = ConfigService.get_instance().get(profile=profile)
        data = settings.model_dump()
        
        # Handle special "all" case
        if key == "all":
            if json_output:
                typer.echo(json.dumps(data))
            else:
                formatted = format_config_full(settings, profile)
                typer.echo(formatted)
            return
        
        # Try to get the value
        try:
            value = _get_from_mapping(data, _parse_dot_path(key))
        except KeyError:
            typer.echo(f"Error: Key not found: {key}", err=True)
            raise typer.Exit(1)
            
        if json_output:
            typer.echo(json.dumps(value))
        else:
            # Check if this is a top-level section that should use section formatting
            _enum_map = {
                "paths": ConfigSection.PATHS,
                "search": ConfigSection.SEARCH,
                "index": ConfigSection.INDEX,
                "sources": ConfigSection.SOURCES,
                "mcp": ConfigSection.MCP,
                "performance": ConfigSection.PERFORMANCE,
                "flags": ConfigSection.FLAGS,
            }
            if key in _enum_map and isinstance(value, dict):
                # Use section formatter for top-level sections
                formatted = format_config_section(_enum_map[key], settings, profile)
                typer.echo(formatted)
            else:
                # Use value formatter for individual keys
                formatted = format_config_value(key, settings, profile)
                typer.echo(formatted)
    except Exception as e:
        typer.echo(f"Error: Failed to read value: {e}", err=True)
        raise typer.Exit(1)


@config_app.command("set")
def set_value(
    key: str = typer.Argument(..., help="Dot-path key to set, e.g. sources.files.base_path"),
    value: str = typer.Argument(..., help="Value to set. Use --json for JSON-typed values."),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Update specific profile instead of base"),
    json_value: bool = typer.Option(False, "--json", help="Interpret value as JSON"),
) -> None:
    """Set or update a configuration value by dot-path."""
    try:
        # Convert input value
        converted: Any = _parse_json_value(value) if json_value else _auto_type_value(value)

        # Prevent direct secrets from being set (only *_env accepted)
        if _is_secret_key(key) and not key.lower().endswith("_env"):
            typer.echo("Error: This field appears to be secret. Use a *_env field instead.", err=True)
            raise typer.Exit(1)

        # Capture previous value if present
        svc = ConfigService.get_instance()
        before = svc.get(profile=profile).model_dump()
        existed = True
        try:
            prev_value = _get_from_mapping(before, _parse_dot_path(key))
        except KeyError:
            existed = False
            prev_value = None

        patch = _to_nested_dict(_parse_dot_path(key), converted)
        svc.update(patch, profile=profile)

        after = svc.get(profile=profile).model_dump()
        new_value = _get_from_mapping(after, _parse_dot_path(key))
        
        # Show the updated value using unified formatter
        typer.echo()
        if existed:
            typer.echo(f"{bold('✅ Updated configuration')}")
            typer.echo(f"  Key: {bold(key)}")
            if profile:
                typer.echo(f"  Profile: {bold(profile)}")
            _echo_multiline("Old:", _render_json(prev_value), indent=2)
            _echo_multiline("New:", _render_json(new_value), indent=2)
            typer.echo()
        else:
            typer.echo(f"{bold('➕ Added configuration')}")
            # Show the new value using the unified formatter
            settings_after = svc.get(profile=profile)
            formatted = format_config_value(key, settings_after, profile)
            typer.echo(formatted)
    except ValueError as ve:
        typer.echo(f"Error: {ve}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: Failed to set value: {e}", err=True)
        raise typer.Exit(1)


@config_app.command("unset")
def unset_value(
    key: str = typer.Argument(..., help="Dot-path key to delete"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Delete from specific profile"),
) -> None:
    """Delete a configuration key by dot-path from base or a profile."""
    try:
        svc = ConfigService.get_instance()
        before = svc.get(profile=profile).model_dump()
        try:
            prev_value = _get_from_mapping(before, _parse_dot_path(key))
            existed = True
        except KeyError:
            existed = False
        svc.delete([key], profile=profile)
        typer.echo()
        if existed:
            typer.echo(f"{bold('🗑️ Removed configuration key')}")
            typer.echo(f"  Key: {bold(key)}")
            if profile:
                typer.echo(f"  Profile: {bold(profile)}")
            _echo_multiline("Previous:", _render_json(prev_value), indent=2)
            typer.echo()
        else:
            typer.echo(f"{bold('ℹ️ Key not found')}  {key}")
            typer.echo()
    except Exception as e:
        typer.echo(f"Error: Failed to delete key: {e}", err=True)
        raise typer.Exit(1)




@config_app.command("validate")
def validate_config(
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Validate specific profile"
    ),
) -> None:
    """Validate configuration and check readiness."""
    try:
        config_service = ConfigService.get_instance()
        settings = config_service.get(profile=profile)
        
        # Unknown keys at any level
        toml = read_toml()
        if profile and toml.get("profiles", {}).get(profile):
            base = {k: v for k, v in toml.items() if k != "profiles"}
            merged = {}
            merged.update(base)
            for k, v in toml["profiles"][profile].items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k] = {**merged[k], **v}
                else:
                    merged[k] = v
            toml_to_check = merged
        else:
            toml_to_check = {k: v for k, v in toml.items() if k != "profiles"}
        unknowns = _collect_unknowns(toml_to_check, IndexedSettings)
        
        # Readiness per source
        files_status = "Not defined"
        if settings.sources.files.base_path is not None:
            if Path(settings.sources.files.base_path).exists():
                files_status = "Ready"
            else:
                files_status = "Partially Defined, missing existing base_path"
        
        jc_missing = []
        if not settings.sources.jira_cloud.base_url:
            jc_missing.append("base_url")
        if not settings.sources.jira_cloud.email:
            jc_missing.append("email")
        jc_token_env = settings.sources.jira_cloud.api_token_env or "JIRA_API_TOKEN"
        if not _dotenv_get(jc_token_env):
            jc_missing.append(jc_token_env)
        if not settings.sources.jira_cloud.base_url and not settings.sources.jira_cloud.email and jc_token_env in jc_missing:
            jira_status = "Not defined"
        elif jc_missing:
            jira_status = f"Partially Defined, missing {', '.join(jc_missing)}"
        else:
            jira_status = "Ready"
        
        cc_missing = []
        if not settings.sources.confluence_cloud.base_url:
            cc_missing.append("base_url")
        if not settings.sources.confluence_cloud.email:
            cc_missing.append("email")
        cc_token_env = settings.sources.confluence_cloud.api_token_env or "CONFLUENCE_API_TOKEN"
        if not _dotenv_get(cc_token_env):
            cc_missing.append(cc_token_env)
        if not settings.sources.confluence_cloud.base_url and not settings.sources.confluence_cloud.email and cc_token_env in cc_missing:
            conf_status = "Not defined"
        elif cc_missing:
            conf_status = f"Partially Defined, missing {', '.join(cc_missing)}"
        else:
            conf_status = "Ready"
        
        ready_count = sum(1 for s in (files_status, jira_status, conf_status) if s == "Ready")
        
        # --- Pretty output ---
        typer.echo()
        typer.echo(f"✨  {bold('Status')}: {bold('Configuration is Valid.') } {color(str(ready_count), 'cyan')} {bold('Sources Ready')}\n")
        typer.echo(bold("Full Breakdown:"))
        
        f_ico, f_col, f_txt = status_style(files_status)
        j_ico, j_col, j_txt = status_style(jira_status)
        c_ico, c_col, c_txt = status_style(conf_status)
        
        def details(status: str) -> str:
            if status.startswith("Partially Defined"):
                return color("  ↳ " + status.replace("Partially Defined, ", "missing "), "yellow")
            return ""
        
        typer.echo(f"  📁 Files Source: {f_ico} {color(f_txt, f_col)}")
        d = details(files_status)
        if d:
            typer.echo(d)
        typer.echo()
        
        typer.echo(f"  🧩 Jira Cloud Source: {j_ico} {color(j_txt, j_col)}")
        d = details(jira_status)
        if d:
            typer.echo(d)
        typer.echo()
        
        typer.echo(f"  📘 Confluence Cloud Source: {c_ico} {color(c_txt, c_col)}")
        d = details(conf_status)
        if d:
            typer.echo(d)
        
        if unknowns:
            if len(unknowns) == 1:
                typer.echo(f"\n⚠️  {bold('Warning')}: An unknown key/value pair has been detected in the config: {color(unknowns[0], 'yellow')}. Please check if this is intended or an error!")
            else:
                typer.echo(f"\n⚠️  {bold('Warnings')}: Unknown key/value pairs detected in the config:")
                for item in unknowns:
                    typer.echo(f"  - {color(item, 'yellow')}")
                typer.echo("Please check if these are intended or errors!")
        typer.echo()
    
    except Exception as e:
        typer.echo(f"Error: Configuration validation failed: {e}", err=True)
        raise typer.Exit(1)
