"""Simple output mode for machine-readable CLI output.

When active, all CLI commands output clean JSON to stdout instead of
Rich-formatted panels, spinners, and colors. Designed for programmatic
consumers like coding tools (Claude Code, Cursor, etc.).

Precedence: CLI flag (--simple-output) > env var > TOML config > False
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

_simple_output_flag: Optional[bool] = None
_resolved_cache: Optional[bool] = None


def set_simple_output(value: bool) -> None:
    """Set simple output mode from CLI --simple-output flag."""
    global _simple_output_flag, _resolved_cache
    _simple_output_flag = value
    _resolved_cache = None


def is_simple_output() -> bool:
    """Check if simple output mode is active.

    Precedence:
        1. CLI flag (set via set_simple_output) — highest
        2. Environment variable INDEXED_SIMPLE_OUTPUT
        3. TOML config output.simple_output
        4. Default: False

    The result from env/config lookup is cached after first resolution.
    """
    if _simple_output_flag is not None:
        return _simple_output_flag

    global _resolved_cache
    if _resolved_cache is not None:
        return _resolved_cache

    result = _resolve_from_env_and_config()
    _resolved_cache = result
    return result


def _resolve_from_env_and_config() -> bool:
    """Resolve simple output from environment variable and TOML config."""
    env = os.getenv("INDEXED_SIMPLE_OUTPUT", "").lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False

    try:
        from indexed_config import ConfigService

        cfg = ConfigService.instance().load_raw()
        val = (cfg.get("output", {}) or {}).get("simple_output")
        if isinstance(val, bool):
            return val
    except Exception:
        pass

    return False


def reset_simple_output() -> None:
    """Reset all state. Used in tests."""
    global _simple_output_flag, _resolved_cache
    _simple_output_flag = None
    _resolved_cache = None


def print_json(data: Any) -> None:
    """Print JSON to stdout for machine consumers."""
    print(json.dumps(data, indent=2, default=str), file=sys.stdout)
