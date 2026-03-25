"""Knowledge/index management module.

Provides CLI commands for managing document collections
and performing semantic search operations.
"""

from .cli import app

__all__ = ["app", "create", "search", "inspect", "update", "remove"]


# Lazy loading to avoid importing heavy dependencies during CLI startup
def __getattr__(name: str):
    if name == "create":
        from .commands import create

        return create
    elif name == "search":
        from .commands import search

        return search
    elif name == "inspect":
        from .commands import inspect

        return inspect
    elif name == "update":
        from .commands import update

        return update
    elif name == "remove":
        from .commands import remove

        return remove
    elif name == "commands":
        from . import commands

        return commands
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
