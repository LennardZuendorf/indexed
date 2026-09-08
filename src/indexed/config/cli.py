"""``indexed config`` command group.

Thin assembly point: builds the Typer app and registers the four subcommands
(get / set / list / validate), each implemented in its own module under
``commands/`` (thin commands, shared helpers in ``commands/_helpers.py``).

Helper functions are re-exported here for backwards-compatible imports
(``from indexed.config.cli import _coerce_value``).
"""

import typer

from .commands.get import get_config
from .commands.set import set_config
from .commands.list import list_config
from .commands.validate import validate
from .commands._helpers import (
    _coerce_value,
    _flatten_dict,
    _format_config_value,
    _is_sensitive_key,
    _mask_sensitive_raw,
    _masked_config_value,
    _merge_with_defaults,
)

app = typer.Typer(help="Manage configuration")

app.command("get", help="Get a configuration value")(get_config)
app.command("set", help="Set a configuration value")(set_config)
app.command("list", help="List resolved configuration")(list_config)
app.command("validate", help="Validate configuration")(validate)

__all__ = [
    "app",
    "get_config",
    "set_config",
    "list_config",
    "validate",
    "_coerce_value",
    "_flatten_dict",
    "_format_config_value",
    "_is_sensitive_key",
    "_mask_sensitive_raw",
    "_masked_config_value",
    "_merge_with_defaults",
]
