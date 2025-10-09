import sys
from typing import Optional

from loguru import logger
from rich.console import Console
from rich.logging import RichHandler

_LOGGING_CONFIGURED = False
_STATUS_SINK_ID = None
_CURRENT_LOG_LEVEL = "WARNING"

# Log level colors matching our design system
_LEVEL_COLORS = {
    "DEBUG": "dim",
    "INFO": "bold cyan",  # Our brand color
    "WARNING": "yellow",
    "ERROR": "bold red",
    "CRITICAL": "bold white on red",
}


def _get_level_color(level_name: str) -> str:
    """Get Rich color style for a log level."""
    return _LEVEL_COLORS.get(level_name, "")


def setup_root_logger(level_str: Optional[str] = None, json_mode: bool = False) -> None:
    """Setup Loguru with Rich formatting.
    
    Default mode (WARNING): Only show WARNING+ to console
    Verbose mode (INFO): Show INFO+ with Rich formatting
    Debug mode (DEBUG): Show DEBUG+ with Rich formatting
    
    Args:
        level_str: Log level (DEBUG, INFO, WARNING, ERROR)
        json_mode: Output logs as JSON (not implemented with Rich)
    """
    global _LOGGING_CONFIGURED, _CURRENT_LOG_LEVEL
    
    if _LOGGING_CONFIGURED:
        # Allow reconfiguration by removing all sinks
        logger.remove()
    
    effective_level = (level_str or "WARNING").upper()
    _CURRENT_LOG_LEVEL = effective_level
    
    # Console for Rich output
    console = Console(stderr=True)
    
    # In verbose/debug mode: show source path and time
    # In default mode: minimal output
    show_details = effective_level in ("DEBUG", "INFO")
    
    # Create a sink function that uses Rich for formatting
    def rich_sink(message):
        record = message.record
        level_name = record["level"].name
        level_color = _get_level_color(level_name)
        
        if show_details:
            # Verbose mode: show time, level, source, message
            source = f"{record['name']}:{record['line']}"
            console.print(
                f"[dim]{record['time'].strftime('%H:%M:%S')}[/dim] "
                f"[{level_color}]{level_name:<8}[/{level_color}] "
                f"[dim]({source})[/dim] {record['message']}"
            )
        else:
            # Default mode: just level and message
            console.print(
                f"[{level_color}]{level_name}[/{level_color}]: {record['message']}"
            )
    
    # Add the Rich sink
    logger.add(
        rich_sink,
        level=effective_level,
        format="{message}",
    )
    
    _LOGGING_CONFIGURED = True


def enable_status_capture(status_updater) -> int:
    """Enable capturing INFO logs for status display.
    
    Adds a temporary sink that captures INFO level logs and forwards
    them to a status updater (e.g., spinner). This allows showing
    progress without cluttering the console.
    
    Args:
        status_updater: Callable that takes a message string
        
    Returns:
        Sink ID that can be used to remove the sink later
    """
    global _STATUS_SINK_ID
    
    def status_sink(message):
        record = message.record
        if record["level"].name == "INFO":
            status_updater(record["message"])
    
    _STATUS_SINK_ID = logger.add(
        status_sink,
        level="INFO",
        format="{message}",
        filter=lambda record: record["level"].name == "INFO"
    )
    
    return _STATUS_SINK_ID


def disable_status_capture():
    """Disable INFO log capture for status display."""
    global _STATUS_SINK_ID
    
    if _STATUS_SINK_ID is not None:
        logger.remove(_STATUS_SINK_ID)
        _STATUS_SINK_ID = None


def is_verbose_mode() -> bool:
    """Check if verbose or debug mode is enabled.
    
    Returns:
        True if log level is INFO or DEBUG, False otherwise
    """
    return _CURRENT_LOG_LEVEL in ("INFO", "DEBUG")
