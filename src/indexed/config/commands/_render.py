"""Rendering for ``indexed config list`` (resolved-config overview).

Renders the merged view of configuration (defaults + workspace + env),
distinguishing manually-set values from defaults, masking secrets, and
supporting an optional section filter and ``--show-defaults``. Extracted from
the command module so ``list.py`` stays a thin dispatcher.
"""

from typing import Any

from rich.markup import escape

from indexed.cli.utils.console import console
from indexed.cli.utils.components import (
    create_key_value_panel,
    create_simple_key_value_panel,
    get_heading_style,
    get_accent_style,
    get_secondary_style,
    get_dim_style,
)

from ._helpers import (
    _get_full_config_schema,
    _masked_config_value,
    _merge_with_defaults,
)

# Select default values to always show (when not showing all defaults).
SELECT_DEFAULTS = {
    ("core", "v1.embedding.model_name"),
    ("core", "v1.embedding.provider"),
    ("core", "v1.storage.type"),
    ("logging", "level"),
}


def render_config_overview(
    config: Any,
    raw: dict[str, Any],
    section: str | None,
    show_defaults: bool,
) -> None:
    """Render the human-readable configuration overview to the console."""
    section_filter = section.lower() if section else None

    console.print()
    if section_filter:
        # section_filter is the user-supplied `section` CLI argument —
        # escape before it enters this markup string.
        console.print(
            f"[{get_heading_style()}]Configuration: "
            f"{escape(section_filter.title())}[/{get_heading_style()}]"
        )
    else:
        console.print(
            f"[{get_heading_style()}]Configuration Overview[/{get_heading_style()}]"
        )
    console.print()

    # Get defaults schema and merge with raw config
    defaults_schema = _get_full_config_schema()
    merged = _merge_with_defaults(raw, defaults_schema)

    # Track statistics
    manual_keys = 0
    default_keys = 0
    manual_sections: set[str] = set()

    # Group sections by type for display
    sources_sections = {}
    core_sections = {}
    other_sections = {}

    for section_name, section_data in merged.items():
        if not section_data:
            continue

        if section_name == "sources":
            sources_sections[section_name] = section_data
        elif section_name == "core":
            core_sections[section_name] = section_data
        else:
            other_sections[section_name] = section_data

        for key, info in section_data.items():
            if info["is_default"]:
                default_keys += 1
            else:
                manual_keys += 1
                manual_sections.add(section_name)

    # Get workspace config separately
    workspace_config = config.get_workspace_config()

    def should_show_key(section: str, key: str, is_default: bool) -> bool:
        """Decide whether a configuration key should be displayed."""
        if not is_default:
            return True  # Always show manual values
        if show_defaults:
            return True  # Show all if --show-defaults
        return (section, key) in SELECT_DEFAULTS

    # Display Sources panel (if no filter or filter matches)
    if sources_sections and (not section_filter or section_filter == "sources"):
        rows: list[tuple[str, str, str]] = []
        for section_name, section_data in sources_sections.items():
            for key, info in sorted(section_data.items()):
                if should_show_key(section_name, key, info["is_default"]):
                    parts = key.split(".", 1)
                    category = parts[0] if len(parts) > 1 else section_name
                    subkey = parts[1] if len(parts) > 1 else key
                    value = _masked_config_value(key, info["value"])
                    rows.append((category, subkey, value))

        if rows:
            panel = create_key_value_panel(
                "Sources",
                rows,
                category_width=14,
                key_width=20,
                headers=("source", "setting", "value"),
            )
            console.print(panel)
            console.print()

    # Display Core Settings panel (if no filter or filter matches)
    if core_sections and (not section_filter or section_filter == "core"):
        rows = []
        for section_name, section_data in core_sections.items():
            for key, info in sorted(section_data.items()):
                if should_show_key(section_name, key, info["is_default"]):
                    parts = key.split(".")
                    if len(parts) >= 2:
                        category = parts[-2] if len(parts) > 2 else parts[0]
                        subkey = parts[-1]
                    else:
                        category = "core"
                        subkey = key
                    value = _masked_config_value(key, info["value"])
                    rows.append((category, subkey, value))

        if rows:
            panel = create_key_value_panel(
                "Core Settings",
                rows,
                category_width=14,
                key_width=24,
                headers=("category", "setting", "value"),
            )
            console.print(panel)
            console.print()

    # Display other sections (logging, mcp, performance)
    for section_name, section_data in sorted(other_sections.items()):
        if section_filter and section_filter != section_name:
            continue

        rows = []
        for key, info in sorted(section_data.items()):
            if should_show_key(section_name, key, info["is_default"]):
                value = _masked_config_value(key, info["value"])
                rows.append((section_name, key, value))

        if rows:
            title = section_name.replace("_", " ").title()
            panel = create_key_value_panel(
                title,
                rows,
                category_width=14,
                key_width=24,
                headers=("category", "setting", "value"),
            )
            console.print(panel)
            console.print()

    # Display Workspace panel (if no filter)
    if workspace_config and not section_filter:
        ws_rows: list[tuple[str, str]] = []
        ws_rows.append(("mode", workspace_config.get("mode", "")))

        local_path = workspace_config.get("local_path", "")
        if len(local_path) > 45:
            local_path = "..." + local_path[-42:]
        ws_rows.append(("local_path", local_path))

        global_path = workspace_config.get("global_path", "~/.indexed")
        if len(global_path) > 45:
            global_path = "..." + global_path[-42:]
        ws_rows.append(("global_path", global_path))

        panel = create_simple_key_value_panel(
            "Workspace",
            ws_rows,
            key_width=15,
            value_max_len=50,
            headers=("setting", "value"),
        )
        console.print(panel)
        console.print()

    # Display Select Default Values panel (only when not filtering / not all)
    if not section_filter and not show_defaults:
        select_rows: list[tuple[str, str, str]] = []

        for section_name, section_data in merged.items():
            for key, info in sorted(section_data.items()):
                if (section_name, key) in SELECT_DEFAULTS and info["is_default"]:
                    parts = key.split(".")
                    if len(parts) >= 2:
                        category = parts[-2] if len(parts) > 2 else parts[0]
                        subkey = parts[-1]
                    else:
                        category = section_name
                        subkey = key
                    value = _masked_config_value(key, info["value"])
                    select_rows.append((category, subkey, value))

        if select_rows:
            panel = create_key_value_panel(
                "Select Default Values",
                select_rows,
                category_width=14,
                key_width=24,
                headers=("category", "setting", "value"),
            )
            console.print(panel)
            remaining_defaults = default_keys - len(select_rows)
            if remaining_defaults > 0:
                console.print(
                    f"[{get_secondary_style()}]{remaining_defaults} more default values used...[/{get_secondary_style()}]"
                )
            console.print()

    # Summary with manual vs default statistics
    total_keys = manual_keys + default_keys
    if total_keys == 0 and not workspace_config:
        console.print(f"[{get_dim_style()}]No configuration found[/{get_dim_style()}]")
        console.print()
        return

    if manual_keys > 0:
        # Section names are top-level config keys, which a user can set to an
        # arbitrary string via `config set <key> <value>` — escape before
        # they enter this markup string.
        section_list = escape(", ".join(sorted(manual_sections)))
        heading = get_heading_style()
        console.print(
            f"[{heading}]Overall:[/{heading}] [{get_accent_style()}]{manual_keys}[/{get_accent_style()}] keys "
            f"set manually for [{get_accent_style()}]{section_list}[/{get_accent_style()}]."
        )
    elif workspace_config:
        mode = workspace_config.get("mode", "unknown")
        heading = get_heading_style()
        console.print(
            f"[{heading}]Overall:[/{heading}] Workspace configured in [{get_accent_style()}]{mode}[/{get_accent_style()}] mode"
        )
    else:
        heading = get_heading_style()
        console.print(f"[{heading}]Overall:[/{heading}] All values using defaults")
    console.print()
