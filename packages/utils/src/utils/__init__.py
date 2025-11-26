"""Indexed utilities - shared code for all packages."""

from .logger import (
    setup_root_logger,
    enable_status_capture,
    disable_status_capture,
    is_verbose_mode,
)
from .batch import read_items_in_batches

# Progress bars moved to CLI utils - core services should be pure logic
from .retry import execute_with_retry
from .performance import execute_and_measure_duration, log_execution_duration
from .safe_getattr import safe_str_attr

__all__ = [
    "setup_root_logger",
    "enable_status_capture",
    "disable_status_capture",
    "is_verbose_mode",
    "read_items_in_batches",
    "execute_with_retry",
    "execute_and_measure_duration",
    "log_execution_duration",
    "safe_str_attr",
]
