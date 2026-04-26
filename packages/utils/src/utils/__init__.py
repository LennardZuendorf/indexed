"""Indexed utilities — shared code for all packages.

- Logging: single-sink Loguru architecture (Rich-optional).
- Retry: exponential backoff for transient failures.
- Batch: paginated API reading with error handling.
- Performance: execution timing utilities.
"""

from .logger import (
    THIRD_PARTY_LOGGERS,
    bootstrap_logging,
    emit_status,
    get_current_log_level,
    is_verbose_mode,
    setup_root_logger,  # deprecated shim
    subscribe_status,
    unsubscribe_status,
)
from .batch import read_items_in_batches
from .retry import execute_with_retry
from .performance import execute_and_measure_duration, log_execution_duration
from .safe_getattr import safe_str_attr

__all__ = [
    # Logging
    "bootstrap_logging",
    "emit_status",
    "subscribe_status",
    "unsubscribe_status",
    "is_verbose_mode",
    "get_current_log_level",
    "THIRD_PARTY_LOGGERS",
    "setup_root_logger",  # deprecated
    # Batch processing
    "read_items_in_batches",
    # Retry logic
    "execute_with_retry",
    # Performance
    "execute_and_measure_duration",
    "log_execution_duration",
    # Utilities
    "safe_str_attr",
]
