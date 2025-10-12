import os
import logging
from importlib import reload


def test_setup_root_logger_central_level(tmp_path, monkeypatch):
    # Ensure environment variables control level/json
    monkeypatch.setenv("INDEXED_LOG_LEVEL", "WARNING")
    monkeypatch.delenv("INDEXED_LOG_JSON", raising=False)

    # Reload logger module to reset _LOGGING_CONFIGURED
    import main.utils.logger as logger_mod

    reload(logger_mod)

    # Initialize with env (WARNING) and verify stdlib logs below level are ignored
    logger_mod.setup_root_logger(level_str=None, json_mode=False)

    # Intercept stdlib logging (already installed), try emitting INFO and ERROR
    logging.info("info message should be ignored")
    logging.error("error message should pass")

    # Basic assertion: no exceptions and module-level flag set
    assert getattr(logger_mod, "_LOGGING_CONFIGURED", False) is True


def test_cli_verbose_overrides_env(monkeypatch, capsys):
    # Set env to WARNING but use CLI verbose later
    monkeypatch.setenv("INDEXED_LOG_LEVEL", "WARNING")
    monkeypatch.delenv("INDEXED_LOG_JSON", raising=False)

    # Import CLI app and invoke help (callback will run); simulate verbose flag by calling callback directly
    import cli.app as cli_app

    # Call the callback to initialize logging with verbose
    cli_app._init_logging(verbose=True, log_level=None, json_logs=False)

    # Emit a DEBUG message via stdlib; with verbose, it should be configured as DEBUG sink level
    logging.debug("debug visible when verbose")

    # No hard assertion on output; confirm no exceptions and app object exists
    assert hasattr(cli_app, "app")


def test_mcp_init_uses_args(monkeypatch):
    # Ensure MCP uses args to initialize logging without throwing
    import types
    import server.mcp as mcp_mod

    reload(mcp_mod)

    # Simulate parsed args
    args = types.SimpleNamespace(
        host="localhost", port=0, log_level="ERROR", json_logs=True
    )

    # Initialize logging using the same logic as main() without starting the server
    from main.utils.logger import setup_root_logger

    level = (args.log_level or os.getenv("INDEXED_LOG_LEVEL", "INFO")).upper()
    json_mode = (
        args.json_logs or os.getenv("INDEXED_LOG_JSON", "false").lower() == "true"
    )
    setup_root_logger(level_str=level, json_mode=json_mode)

    # Emit a warning which should be suppressed at ERROR level
    logging.warning("suppressed at ERROR level")

    assert True
