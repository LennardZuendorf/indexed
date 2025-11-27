from __future__ import annotations

from typing import Literal, Optional

from indexed_config import ConfigService


def should_output_json(
    for_context: Literal["cli", "mcp"],
    flag_value: Optional[bool] = None,
) -> bool:
    """Decide whether to output JSON based on precedence and context.

    Precedence:
    - CLI: `--json-output` flag > config flags.cli_json_output > default False
    - MCP: future flag > config mcp.mcp_json_output > default True
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
