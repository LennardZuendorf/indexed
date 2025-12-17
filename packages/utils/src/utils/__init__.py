"""Indexed utilities - shared code for all packages.

This package provides lightweight utilities for the indexed project:
- Logging: Base Loguru configuration (no Rich dependency)
- Retry: Exponential backoff for transient failures
- Batch: Paginated API reading with error handling
- Performance: Execution timing utilities
"""

from .logger import (
    setup_root_logger,
    is_verbose_mode,
    get_current_log_level,
)
from .batch import read_items_in_batches
from .retry import execute_with_retry
from .performance import execute_and_measure_duration, log_execution_duration
from .safe_getattr import safe_str_attr

__all__ = [
    # Logging
    "setup_root_logger",
    "is_verbose_mode",
    "get_current_log_level",
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
