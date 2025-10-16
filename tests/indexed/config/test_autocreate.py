"""Tests for config auto-creation."""
import pytest
from indexed.config.cli import init as AutoCreator

pytestmark = pytest.mark.indexed  # Mark as main app test