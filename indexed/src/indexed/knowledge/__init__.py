"""Knowledge/index management module.

Provides CLI commands for managing document collections
and performing semantic search operations.
"""

from . import commands
from .cli import app
from .commands import create, search, inspect, update, remove

__all__ = ["commands", "app", "create", "search", "inspect", "update", "remove"]

