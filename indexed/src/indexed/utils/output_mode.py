from __future__ import annotations

from typing import Literal, Optional

from indexed_config import ConfigService


def should_output_json(
    for_context: Literal["cli", "mcp"],
    flag_value: Optional[bool] = None,
) -> bool:
    """
    Decide whether output should be formatted as JSON for the given context.

    Precedence:
    - If `flag_value` is provided, it takes precedence.
    - For `for_context == "cli"`: consult `flags.cli_json_output` from configuration, defaulting to False when absent or not a boolean.
    - For `for_context == "mcp"`: consult `mcp.mcp_json_output` from configuration, defaulting to True when absent or not a boolean.

    Parameters:
        for_context (Literal["cli", "mcp"]): The runtime context requesting output format.
        flag_value (Optional[bool]): Explicit flag override; if set, its value is returned.

    Returns:
        bool: `true` if JSON output should be used, `false` otherwise.
    """
    # Flag wins if explicitly provided
    if flag_value is True:
        return True
    if flag_value is False:
        # Explicitly disabled via flag (if we add negative flags in future)
        return False

    cfg = ConfigService.instance().load_raw()

    if for_context == "cli":
        val = (cfg.get("flags", {}) or {}).get("cli_json_output")
        return bool(val) if isinstance(val, bool) else False

    if for_context == "mcp":
        val = (cfg.get("mcp", {}) or {}).get("mcp_json_output")
        if isinstance(val, bool):
            return val
        return True

    # Default conservative choice
    return False
