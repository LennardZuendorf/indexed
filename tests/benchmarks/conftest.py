"""Benchmark-specific test fixtures.

This module provides fixtures for performance benchmarking:
- Configures environment for CLI commands
- Reuses TQDM handling from system tests
- Reuses shared fixtures from fixtures module

Note: TQDM handling is imported from tests/system/conftest.py
"""

# Import TQDM handling from system tests
# This ensures TQDM_DISABLE is set before any imports
from tests.system.conftest import pytest_configure  # noqa: F401
