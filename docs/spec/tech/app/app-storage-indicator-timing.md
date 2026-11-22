---
type: tech
updated: 2026-11-22
applies: "src/indexed/cli/**"
---

# Storage Indicator Timing

The storage-mode indicator (`display_storage_mode_for_command`) must print before any
connector prompt (URL, credentials). Each connector command hoists the indicator to its
top using a module-level helper:

```python
def _display_storage_indicator(verbose: bool, log_level: Optional[str]) -> None:
    """Print storage-mode indicator unless verbose/debug output is already active."""
    if not verbose and not (log_level and log_level.upper() in ("INFO", "DEBUG")):
        from ...utils.storage_info import display_storage_mode_for_command
        display_storage_mode_for_command(console)
```

**Why not `is_verbose_mode()`?** At command-function top, `setup_root_logger` has not
yet run (it lives inside `execute_create_command`), so `is_verbose_mode()` always
returns its module-level default (`False`) regardless of flags. The direct `verbose`
and `log_level` params are the only reliable source before logger setup.
