"""System test: verify UI design consistency across CLI commands.

Checks that all major commands use the shared design system components
(phased progress, storage indicator, alert panels) consistently.
"""

import ast
from pathlib import Path

import pytest


# Paths to the command files under test
_COMMANDS_DIR = (
    Path(__file__).resolve().parents[2] / "apps" / "indexed" / "src" / "indexed"
)

_COMMAND_FILES = {
    "init": _COMMANDS_DIR / "init.py",
    "create": _COMMANDS_DIR / "knowledge" / "commands" / "_create_helpers.py",
    "search": _COMMANDS_DIR / "knowledge" / "commands" / "search.py",
    "update": _COMMANDS_DIR / "knowledge" / "commands" / "update.py",
    "remove": _COMMANDS_DIR / "knowledge" / "commands" / "remove.py",
}

# Commands that perform long-running operations and MUST use phased progress
_PROGRESS_COMMANDS = ["init", "create", "search", "update", "remove"]

# Commands that interact with storage and MUST show the storage mode indicator
_STORAGE_INDICATOR_COMMANDS = ["init", "create", "search", "update", "remove"]

# Commands that MUST use alert panels (print_success/print_error) for results
_ALERT_COMMANDS = ["init", "create", "search", "update", "remove"]


def _read_source(path: Path) -> str:
    """Read file source code."""
    return path.read_text(encoding="utf-8")


def _get_imports(source: str) -> set[str]:
    """Extract all imported names from source code."""
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.names:
                for alias in node.names:
                    names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


class TestUIDesignConsistency:
    """Verify all commands use the shared design system uniformly."""

    @pytest.mark.parametrize("cmd_name", _PROGRESS_COMMANDS)
    def test_commands_use_phased_progress(self, cmd_name):
        """All long-running commands must use create_phased_progress."""
        source = _read_source(_COMMAND_FILES[cmd_name])
        assert "create_phased_progress" in source, (
            f"{cmd_name} command must use create_phased_progress() "
            f"instead of raw Progress/SpinnerColumn or OperationStatus"
        )

    @pytest.mark.parametrize("cmd_name", _PROGRESS_COMMANDS)
    def test_commands_do_not_use_raw_progress(self, cmd_name):
        """No command should use raw Rich Progress with SpinnerColumn directly."""
        source = _read_source(_COMMAND_FILES[cmd_name])
        imports = _get_imports(source)
        assert "SpinnerColumn" not in imports, (
            f"{cmd_name} command imports SpinnerColumn directly. "
            f"Use create_phased_progress() instead."
        )

    @pytest.mark.parametrize("cmd_name", _STORAGE_INDICATOR_COMMANDS)
    def test_commands_show_storage_mode_indicator(self, cmd_name):
        """All storage-interacting commands must display the storage mode."""
        source = _read_source(_COMMAND_FILES[cmd_name])
        assert "display_storage_mode_for_command" in source, (
            f"{cmd_name} command must call display_storage_mode_for_command(console) "
            f"to show which storage mode (global/local) is active"
        )

    @pytest.mark.parametrize("cmd_name", _ALERT_COMMANDS)
    def test_commands_use_alert_panels(self, cmd_name):
        """All commands must use print_success/print_error alert panels."""
        source = _read_source(_COMMAND_FILES[cmd_name])
        has_success = "print_success" in source
        has_error = "print_error" in source
        assert has_success or has_error, (
            f"{cmd_name} command must use print_success() or print_error() "
            f"from the shared alert system instead of inline console.print"
        )

    @pytest.mark.parametrize("cmd_name", _PROGRESS_COMMANDS)
    def test_commands_use_suppress_core_output(self, cmd_name):
        """Commands with phased progress must suppress core output during progress."""
        source = _read_source(_COMMAND_FILES[cmd_name])
        assert "suppress_core_output" in source, (
            f"{cmd_name} command must use suppress_core_output() "
            f"to prevent core logs from interfering with progress display"
        )

    @pytest.mark.parametrize("cmd_name", ["create", "search", "update", "remove"])
    def test_knowledge_commands_handle_verbose_mode(self, cmd_name):
        """Knowledge commands must check is_verbose_mode for progress branching."""
        source = _read_source(_COMMAND_FILES[cmd_name])
        assert "is_verbose_mode" in source, (
            f"{cmd_name} command must check is_verbose_mode() "
            f"to switch between progress display and verbose logging"
        )

    @pytest.mark.parametrize("cmd_name", _PROGRESS_COMMANDS)
    def test_no_standalone_operation_status_for_progress(self, cmd_name):
        """Commands should not use OperationStatus as their main progress indicator."""
        source = _read_source(_COMMAND_FILES[cmd_name])
        imports = _get_imports(source)
        assert "OperationStatus" not in imports, (
            f"{cmd_name} command imports OperationStatus. "
            f"Use create_phased_progress() for consistent progress display."
        )
