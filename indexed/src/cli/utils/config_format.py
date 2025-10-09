from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.v1.config.settings import IndexedSettings
from core.v1.config.store import read_toml


# --- ANSI styling helpers ---
_COLORS = {
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "magenta": "\033[35m",
    "blue": "\033[34m",
    "gray": "\033[90m",
}
_RESET = "\033[0m"
_BOLD = "\033[1m"


def _bold(text: str) -> str:
    return f"{_BOLD}{text}{_RESET}"


def _color(text: str, name: Optional[str]) -> str:
    if not name:
        return text
    return f"{_COLORS.get(name, '')}{text}{_RESET}"


def _status_style(status: str) -> tuple[str, str, str]:
    lowered = status.lower()
    if lowered == "ready":
        return ("✅", "green", status)
    if lowered.startswith("partially"):
        return ("🟡", "yellow", status)
    return ("⛔", "red", status)


# --- origin helpers ---

def _dotenv_get(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is not None:
        return value
    env_path = Path(".env")
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k == name:
            return v.strip().strip('"').strip("'")
    return None


def _env_var_name_for_path(path: Tuple[str, ...]) -> str:
    return "INDEXED__" + "__".join(p.upper() for p in path)


def _has_toml_key(toml_data: Dict[str, Any], path: Tuple[str, ...]) -> bool:
    cur: Any = toml_data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return False
        cur = cur[key]
    return True


def _build_merged_toml_for_profile(profile: Optional[str]) -> Dict[str, Any]:
    toml = read_toml()
    if not toml:
        return {}
    if not profile:
        return {k: v for k, v in toml.items() if k != "profiles"}
    base = {k: v for k, v in toml.items() if k != "profiles"}
    overlay = toml.get("profiles", {}).get(profile, {})

    def merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        res = dict(a)
        for k, v in b.items():
            if k in res and isinstance(res[k], dict) and isinstance(v, dict):
                res[k] = merge(res[k], v)
            else:
                res[k] = v
        return res

    return merge(base, overlay)


def _build_origin_map(effective: Dict[str, Any], profile: Optional[str]) -> Dict[str, Any]:
    toml_merged = _build_merged_toml_for_profile(profile)

    def build(node: Any, path: Tuple[str, ...]) -> Any:
        if isinstance(node, dict):
            return {k: build(v, path + (k,)) for k, v in node.items()}
        env_name = _env_var_name_for_path(path)
        if _dotenv_get(env_name) is not None:
            return "env"
        if _has_toml_key(toml_merged, path):
            return "toml"
        return "default"

    return build(effective, tuple())


def _origin_badge(origin: Optional[str]) -> str:
    if origin == "env":
        return _color("[env]", "cyan")
    if origin == "toml":
        return _color("[toml]", "magenta")
    return _color("[default]", "gray")


# --- small utils ---

def _parse_dot_path(key: str) -> List[str]:
    return key.split(".")


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


# --- enum for public API ---
class ConfigSection(Enum):
    ALL = "all"
    PATHS = "paths"
    SEARCH = "search"
    INDEX = "index"
    SOURCES = "sources"
    MCP = "mcp"
    PERFORMANCE = "performance"
    FLAGS = "flags"


# --- section renderers (return lines) ---

def _render_configuration_summary_lines(settings: IndexedSettings, profile: Optional[str]) -> List[str]:
    lines: List[str] = []
    lines.append(_bold("⚙️  Configuration"))
    lines.append(f"  Profile: {_bold(profile) if profile else 'Default'}")
    try:
        src = settings.sources
        ready_count = int(src.files.is_ready) + int(src.jira_cloud.is_ready) + int(src.confluence_cloud.is_ready)
        lines.append(f"  Sources ready: {_bold(str(ready_count))}/3")
    except Exception:
        pass
    lines.append("")
    return lines


def _render_kv_section_lines(title: str, emoji: str, section: Dict[str, Any], origins: Optional[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    lines.append(_bold(f"{emoji} {title}:"))
    for key in sorted(section.keys()):
        origin = None
        if origins and isinstance(origins.get(key), (str, dict)):
            leaf = origins.get(key)
            origin = leaf if isinstance(leaf, str) else None
        badge = f" {_origin_badge(origin)}" if origin else ""
        lines.append(f"  - {key}: {_stringify(section[key])}{badge}")
    lines.append("")
    return lines


def _render_sources_section_lines(sources: Dict[str, Any], origins: Optional[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    lines.append(_bold("🌐 Sources:"))
    # Files
    if isinstance(sources.get("files"), dict):
        lines.append(f"  - {_bold('📂 Files:')}")
        for key in sorted(sources["files"].keys()):
            origin_map = None
            if origins and isinstance(origins.get("files"), dict):
                leaf = origins["files"].get(key)
                origin_map = leaf if isinstance(leaf, str) else None
            badge = f" {_origin_badge(origin_map)}" if origin_map else ""
            lines.append(f"      - {key}: {_stringify(sources['files'][key])}{badge}")
    # Jira Cloud
    if isinstance(sources.get("jira_cloud"), dict):
        lines.append(f"  - {_bold('🧩 Jira Cloud:')}")
        for key in sorted(sources["jira_cloud"].keys()):
            origin_map = None
            if origins and isinstance(origins.get("jira_cloud"), dict):
                leaf = origins["jira_cloud"].get(key)
                origin_map = leaf if isinstance(leaf, str) else None
            badge = f" {_origin_badge(origin_map)}" if origin_map else ""
            lines.append(f"      - {key}: {_stringify(sources['jira_cloud'][key])}{badge}")
    # Confluence Cloud
    if isinstance(sources.get("confluence_cloud"), dict):
        lines.append(f"  - {_bold('📘 Confluence Cloud:')}")
        for key in sorted(sources["confluence_cloud"].keys()):
            origin_map = None
            if origins and isinstance(origins.get("confluence_cloud"), dict):
                leaf = origins["confluence_cloud"].get(key)
                origin_map = leaf if isinstance(leaf, str) else None
            badge = f" {_origin_badge(origin_map)}" if origin_map else ""
            lines.append(f"      - {key}: {_stringify(sources['confluence_cloud'][key])}{badge}")
    lines.append("")
    return lines


# --- Public API ---

def format_config_full(settings: IndexedSettings, profile: Optional[str] = None) -> str:
    data: Dict[str, Any] = settings.model_dump()
    origins = _build_origin_map(data, profile)

    lines: List[str] = []
    lines.append("")
    lines.extend(_render_configuration_summary_lines(settings, profile))

    # Main areas list
    lines.append(_bold("🧭 Main Config Areas:"))
    for _, label in [
        ("paths", "Paths"),
        ("search", "Search"),
        ("index", "Index"),
        ("sources", "Sources"),
        ("mcp", "MCP"),
        ("performance", "Performance"),
        ("flags", "Flags"),
    ]:
        lines.append(f"  - {label}")
    lines.append("\n ")

    # Sections
    lines.extend(_render_kv_section_lines("Paths", "📂", data.get("paths", {}), origins.get("paths", {}) if isinstance(origins, dict) else None))
    lines.extend(_render_kv_section_lines("Search", "🔎", data.get("search", {}), origins.get("search", {}) if isinstance(origins, dict) else None))
    lines.extend(_render_kv_section_lines("Index", "🗂️", data.get("index", {}), origins.get("index", {}) if isinstance(origins, dict) else None))
    lines.extend(_render_sources_section_lines(data.get("sources", {}), origins.get("sources", {}) if isinstance(origins, dict) else None))
    lines.extend(_render_kv_section_lines("MCP", "🧠", data.get("mcp", {}), origins.get("mcp", {}) if isinstance(origins, dict) else None))
    lines.extend(_render_kv_section_lines("Performance", "⚡", data.get("performance", {}), origins.get("performance", {}) if isinstance(origins, dict) else None))
    lines.extend(_render_kv_section_lines("Flags", "🚩", data.get("flags", {}), origins.get("flags", {}) if isinstance(origins, dict) else None))

    return "\n".join(lines)


def format_config_section(
    section: ConfigSection,
    settings: IndexedSettings,
    profile: Optional[str] = None,
) -> str:
    data: Dict[str, Any] = settings.model_dump()
    origins = _build_origin_map(data, profile)

    if section == ConfigSection.SOURCES:
        return "\n".join([""] + _render_sources_section_lines(data.get("sources", {}), origins.get("sources", {}) if isinstance(origins, dict) else None))

    mapping = {
        ConfigSection.PATHS: ("📂", "Paths", "paths"),
        ConfigSection.SEARCH: ("🔎", "Search", "search"),
        ConfigSection.INDEX: ("🗂️", "Index", "index"),
        ConfigSection.MCP: ("🧠", "MCP", "mcp"),
        ConfigSection.PERFORMANCE: ("⚡", "Performance", "performance"),
        ConfigSection.FLAGS: ("🚩", "Flags", "flags"),
    }

    if section == ConfigSection.ALL:
        return format_config_full(settings, profile)

    if section in mapping:
        emoji, title, key = mapping[section]
        section_data = data.get(key, {}) if isinstance(data, dict) else {}
        section_origins = origins.get(key, {}) if isinstance(origins, dict) else None
        return "\n".join([""] + _render_kv_section_lines(title, emoji, section_data, section_origins))

    # Fallback: unknown section
    return ""


def format_config_value(
    key_path: str,
    settings: IndexedSettings,
    profile: Optional[str] = None,
) -> str:
    data: Dict[str, Any] = settings.model_dump()
    origins = _build_origin_map(data, profile)

    # Resolve value
    try:
        value = _get_from_mapping(data, _parse_dot_path(key_path))
    except KeyError:
        raise KeyError(f"Key not found: {key_path}")

    # Resolve origin for this key
    origin_cursor: Any = origins
    for part in _parse_dot_path(key_path):
        origin_cursor = origin_cursor.get(part) if isinstance(origin_cursor, dict) else None
    origin = origin_cursor if isinstance(origin_cursor, str) else "default"

    lines: List[str] = []
    lines.append("")
    lines.append(f"{_bold('🔧 Config Value')}")
    lines.append(f"  Key: {_bold(key_path)}")
    if profile:
        lines.append(f"  Profile: {_bold(profile)}")
    lines.append(f"  Source: {_bold(origin.upper())}")
    rendered = _render_json(value)

    # Echo multiline value
    sv = "  "
    val_lines = rendered.splitlines() or [rendered]
    if len(val_lines) == 1:
        lines.append(f"{sv}Value: {val_lines[0]}")
    else:
        lines.append(f"{sv}Value:")
        for line in val_lines:
            lines.append(f"{sv}  {line}")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "ConfigSection",
    "format_config_full",
    "format_config_section",
    "format_config_value",
]
