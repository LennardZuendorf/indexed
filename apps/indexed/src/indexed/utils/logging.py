"""Backwards-compatible shim — delegates to the unified ``utils.logger``.

The previous Rich-aware logger module here has been folded into
``packages/utils/src/utils/logger.py``. Existing imports continue to work via
this shim until callers are migrated to import ``bootstrap_logging`` directly.
"""

from utils import (
    bootstrap_logging,
    get_current_log_level,
    is_verbose_mode,
    setup_root_logger,
)

__all__ = [
    "bootstrap_logging",
    "setup_root_logger",
    "is_verbose_mode",
    "get_current_log_level",
]
