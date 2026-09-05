"""Indexed CLI application - stateless commands backed by services."""

# Process-wide env vars — must be set before any third-party imports.
# Fix OpenMP threading on macOS; suppress noisy third-party output.
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TQDM_DISABLE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("ORT_LOGGING_LEVEL", "3")

import warnings

warnings.filterwarnings("ignore", message="builtin type Swig.*")
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Optional  # noqa: E402

import typer  # noqa: E402
import typer.rich_utils  # noqa: E402
from indexed.config.errors import IndexedError  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.theme import Theme  # noqa: E402

from indexed.utils import bootstrap_logging  # noqa: E402

from .utils.banner import print_indexed_banner  # noqa: E402
from .utils.components.alerts import print_error  # noqa: E402
from .utils.components.theme import (  # noqa: E402
    get_accent_style,
    get_dim_style,
    get_error_style,
    get_help_theme_styles,
    get_info_style,
    get_success_style,
    get_warning_style,
)
from .utils.console import console as _shared_console  # noqa: E402

# Single source of truth for level → Rich style mapping. New themes change
# theme.py; logging picks them up automatically.
THEME_STYLES: dict[str, str] = {
    "TRACE": get_dim_style(),
    "DEBUG": get_dim_style(),
    "INFO": get_info_style(),
    "SUCCESS": get_success_style(),
    "WARNING": get_warning_style(),
    "ERROR": get_error_style(),
    "CRITICAL": get_error_style(),
}

# typer's stubs declare these as narrow Literal defaults (e.g. "bold cyan"),
# but they're plain module-level str attributes at runtime — overriding them
# for accent theming is a supported, if untyped, customization point.
typer.rich_utils.STYLE_OPTION = f"bold {get_accent_style()}"  # ty: ignore[invalid-assignment]
typer.rich_utils.STYLE_SWITCH = f"bold {get_accent_style()}"  # ty: ignore[invalid-assignment]
typer.rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = f"bold {get_accent_style()}"  # ty: ignore[invalid-assignment]

_help_console = Console(theme=Theme(get_help_theme_styles()))

app = typer.Typer(
    add_completion=True,
    help="Index Institutional Knowledge and Make it Available for AI Agents and LLMs!",
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    context_settings={"help_option_names": ["--help"]},
)


@app.callback(invoke_without_command=True)
def _init_app(
    ctx: typer.Context,
    local: bool = typer.Option(
        False,
        "--local",
        help="Use local .indexed/ storage instead of global ~/.indexed/",
        rich_help_panel="Usage Options",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose (INFO) logging",
        rich_help_panel="Debug Options",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Set logging level (DEBUG, INFO, WARNING, ERROR)",
        case_sensitive=False,
        show_choices=True,
        rich_help_panel="Debug Options",
    ),
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Output logs as JSON",
        rich_help_panel="Debug Options",
    ),
    simple_output: bool = typer.Option(
        False,
        "--simple-output",
        help="Machine-readable JSON output (for programmatic use)",
        rich_help_panel="Usage Options",
    ),
    engine: Optional[str] = typer.Option(
        None,
        "--engine",
        help="Engine for NEW collections: v1 or v2 (default: v1)",
        rich_help_panel="Usage Options",
    ),
) -> None:
    """Initialize logging and handle storage flags. ConfigService is deferred to commands."""
    if simple_output:
        from .utils.simple_output import set_simple_output

        set_simple_output(True)

    if (
        ctx.invoked_subcommand is None
        and not ctx.resilient_parsing
        and ("--help" in sys.argv or "-h" in sys.argv)
    ):
        print_indexed_banner()

    from .utils.simple_output import is_simple_output

    env_level = os.getenv("INDEXED_LOG_LEVEL")
    resolved_level = log_level or ("INFO" if verbose else None) or env_level
    level = resolved_level.upper() if resolved_level else None
    json_mode = (
        json_logs
        or is_simple_output()
        or os.getenv("INDEXED_LOG_JSON", "false").lower() == "true"
    )
    effective_level = (level or "WARNING").upper()
    bootstrap_logging(
        level=effective_level,
        debug=(effective_level == "DEBUG"),
        quiet=(effective_level == "ERROR"),
        rich_console=_shared_console,
        theme_styles=THEME_STYLES,
        log_dir=Path.home() / ".indexed" / "logs",
        json_mode=json_mode,
    )

    # Store resolved mode_override on ctx.obj for subcommands to access
    ctx.ensure_object(dict)
    ctx.obj["mode_override"] = "local" if local else None
    # Store the raw (normalized) engine selector, mirroring mode_override: None
    # when unset. ``isinstance`` guards the direct-call path in tests where the
    # unpassed option is still its typer OptionInfo default, not a str/None.
    if isinstance(engine, str):
        from .composition import normalize_engine_selector

        ctx.obj["engine"] = normalize_engine_selector(engine)
    else:
        ctx.obj["engine"] = None

    from indexed.config import get_config

    from .composition import register_app_config

    register_app_config(get_config(mode_override=ctx.obj.get("mode_override")))

    if local:
        from indexed.config import ensure_storage_dirs, get_local_root

        workspace = Path.cwd()
        local_root = get_local_root(workspace)
        ensure_storage_dirs(local_root, is_local=True)


from ._app_setup import register_commands  # noqa: E402

# Wire every subcommand onto the app at import time so the console-script entry
# points (`indexed.cli.app:app` / `:main`) get a fully-populated CLI.
register_commands(app)


__all__ = [
    "app",
    "main",
    "DEFAULT_INDEXER",  # noqa: F822
    "svc_create",  # noqa: F822
    "svc_update",  # noqa: F822
    "svc_clear",  # noqa: F822
    "svc_search",  # noqa: F822
    "svc_status",  # noqa: F822
    "SourceConfig",  # noqa: F822
]


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests."""
    if name == "DEFAULT_INDEXER":
        from indexed.core.v1.constants import DEFAULT_INDEXER

        return DEFAULT_INDEXER
    elif name == "svc_create":
        from indexed.core.engine import create

        return create
    elif name == "svc_update":
        from indexed.core.engine import update

        return update
    elif name == "svc_clear":
        from indexed.core.engine import clear

        return clear
    elif name == "svc_search":
        from indexed.core.engine import search

        return search
    elif name == "svc_status":
        from indexed.core.engine import status

        return status
    elif name == "SourceConfig":
        from indexed.core.engine import SourceConfig

        return SourceConfig
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def main() -> None:
    """CLI entry point."""
    # Wire logging BEFORE Typer parses args so any third-party module imported
    # during command resolution can't leak to stderr. The Typer callback
    # reconfigures with the resolved verbosity (idempotent).
    bootstrap_logging(
        level="WARNING",
        rich_console=_shared_console,
        theme_styles=THEME_STYLES,
    )

    if len(sys.argv) == 2 and sys.argv[1] in ["--help", "-h"]:
        print_indexed_banner()
    try:
        app()
    except IndexedError as exc:
        from .errors import exit_code_for, format_cli_error

        # No `escape()` here: `print_error` renders through a `rich.text.Text`
        # sink, which is literal by construction (never markup-parsed), so a
        # user-supplied `[core.v2.rerank].enabled` prints verbatim. Escaping
        # first would leak the backslash into the output.
        print_error(format_cli_error(exc))
        # `app()` already ran (and exited) the click runner — `typer.Exit`
        # raised here would be uncaught (no click main() left to interpret
        # it), producing a traceback and losing the mapped exit code
        # (foundation/6 E1). `sys.exit` is the correct process-exit primitive
        # outside the runner.
        sys.exit(exit_code_for(exc))


if __name__ == "__main__":
    main()
