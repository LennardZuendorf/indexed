"""Logging configuration for the CLI.

Configures logging levels based on CLI flags:
- Default: WARNING (clean, no noise)
- --verbose: INFO (high-level operations)
- --debug: DEBUG (everything)
"""

import logging
from rich.logging import RichHandler


def setup_logging(verbose: bool = False, debug: bool = False, quiet: bool = False) -> None:
    """Setup logging with appropriate level.
    
    Args:
        verbose: Show INFO level logs
        debug: Show DEBUG level logs
        quiet: Show only ERROR logs
    """
    if quiet:
        level = logging.ERROR
    elif debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    
    # Configure with Rich handler for beautiful output
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                show_time=False,
                show_path=False,
                markup=True,
                rich_tracebacks=True
            )
        ]
    )


__all__ = ["setup_logging"]
