"""Knowledge/index management module.

Provides CLI commands and formatters for managing document collections
and performing semantic search operations.
"""

from . import commands, formatters
from .cli import app
from .commands import create, search, inspect, update, remove

__all__ = ["commands", "formatters", "app", "create", "search", "inspect", "update", "remove"]

