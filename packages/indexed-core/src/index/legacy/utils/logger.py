import logging
import sys
import inspect
from typing import Optional

from loguru import logger

_LOGGING_CONFIGURED = False


def _install_intercept_handler() -> None:
    class InterceptHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                level: str | int = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            frame, depth = inspect.currentframe(), 0
            while frame:
                filename = frame.f_code.co_filename
                is_logging = filename == logging.__file__
                is_frozen = "importlib" in filename and "_bootstrap" in filename
                if depth > 0 and not (is_logging or is_frozen):
                    break
                frame = frame.f_back
                depth += 1

            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)


def setup_root_logger(level_str: Optional[str] = None, json_mode: bool = False) -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    # Remove default sink and add our stderr sink with desired level/format
    logger.remove()

    effective_level = (level_str or "INFO").upper()
    logger.add(
        sys.stderr,
        level=effective_level,
        serialize=json_mode,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
    )

    _install_intercept_handler()

    # Configure specific third-party library log levels
    configure_third_party_loggers()

    _LOGGING_CONFIGURED = True


def configure_third_party_loggers():
    library_configs = {
        "faiss": logging.WARNING,
        "sentence_transformers": logging.WARNING,
    }

    for lib_name, log_level in library_configs.items():
        logging.getLogger(lib_name).setLevel(log_level)
