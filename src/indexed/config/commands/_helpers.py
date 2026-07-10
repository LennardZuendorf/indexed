"""Shared helpers for the ``indexed config`` commands.

Value coercion, dict flattening, display formatting, secret masking, and the
defaults-schema / merge logic used by the get / set / list / validate
commands. Kept separate from the thin command modules (thin commands, fat
helpers). Re-exported from ``indexed.config.cli`` for backwards-compatible
imports.
"""

import json
import re
from typing import Any, Optional
from collections import defaultdict


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_command_logging(
    verbose: bool, json_logs: bool, log_level: Optional[str]
) -> None:
    """Configure root logging for a config command from its shared options."""
    from indexed.cli.utils.logging import setup_root_logger

    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger(level_str=effective_level, json_mode=json_logs)


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------

# F5: float()/json.loads() happily parse these as non-finite numbers, but a
# user typing them as a config value almost certainly means the literal word
# (e.g. a free-text field containing "nan"), not IEEE NaN/Infinity.
_NON_FINITE_FLOAT_WORDS = {
    "nan",
    "inf",
    "+inf",
    "-inf",
    "infinity",
    "+infinity",
    "-infinity",
}

# A genuine int/float literal never leads with a zero before another digit —
# a zero-padded string like "001" is an identifier (version, ticket number,
# ...) that must stay a string, not become the int 1.
_LEADING_ZERO_NUMERIC_RE = re.compile(r"^[+-]?0\d")


def _coerce_value(value: str) -> Any:
    """
    Convert a string to an appropriate Python type.

    Attempts to interpret the input as a boolean, integer, float, or JSON
    value (list/dict); if none apply, returns the original string. Only
    coerces values that are genuinely numeric/bool/json (F5) — a string that
    merely *resembles* one (a zero-padded id like ``"001"``, or the word
    ``"nan"``) is returned unchanged so identifiers and literal words are
    never silently mangled into numbers.
    """
    # Try bool first
    low = value.lower()
    if low in {"true", "false"}:
        return low == "true"

    if low in _NON_FINITE_FLOAT_WORDS:
        return value

    if not _LEADING_ZERO_NUMERIC_RE.match(value):
        # Try int (handles both positive and negative integers properly)
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

    # Try JSON (for lists/dicts)
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        pass

    # Return original string if no conversion succeeded
    return value


# ---------------------------------------------------------------------------
# Dict flattening / formatting
# ---------------------------------------------------------------------------


def _flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict[str, Any]:
    """Flatten nested dictionary with dot notation keys."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def _format_config_value(value: Any) -> str:
    """
    Produce a display-friendly string for a configuration value.

    Booleans become "true"/"false", empty lists or dicts become "(empty)",
    None becomes "(not set)", non-empty lists are joined with ", ", and dicts
    are summarized as "(N items)".
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (list, tuple)):
        if not value:
            return "(empty)"
        return ", ".join(str(v) for v in value)
    elif isinstance(value, dict):
        if not value:
            return "(empty)"
        return f"({len(value)} items)"
    elif value is None:
        return "(not set)"
    else:
        return str(value)


# ---------------------------------------------------------------------------
# Secret masking (C1)
# ---------------------------------------------------------------------------


def _is_sensitive_key(key: str) -> bool:
    """
    Determine whether a configuration key should be treated as sensitive.

    Only the last dot-separated segment is inspected; a key is sensitive when
    that segment contains any of: "api_token", "token", "password", "secret".
    """
    sensitive_patterns = ["api_token", "token", "password", "secret"]
    key_lower = key.lower()
    key_name = key.split(".")[-1].lower() if "." in key else key_lower
    return any(pattern in key_name for pattern in sensitive_patterns)


def _masked_config_value(key: str, value: Any) -> str:
    """Format a config value for display, masking sensitive values (C1).

    A sensitive key (per ``_is_sensitive_key``) with a real value shows a
    fixed mask instead of the plaintext; unset/empty values still show as such.
    """
    formatted = _format_config_value(value)
    if _is_sensitive_key(key) and formatted not in ("(not set)", "(empty)"):
        return "*****"
    return formatted


def _mask_sensitive_raw(data: dict) -> dict:
    """Return a deep copy of a raw config dict with sensitive leaves masked.

    Used for machine-readable output (``--simple-output`` JSON) so a secret
    that reached the merged config (e.g. via an ``INDEXED__*`` env override)
    is never dumped in cleartext (C1).
    """
    masked: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            masked[key] = _mask_sensitive_raw(value)
        elif _is_sensitive_key(key) and value not in (None, ""):
            masked[key] = "*****"
        else:
            masked[key] = value
    return masked


# ---------------------------------------------------------------------------
# Defaults schema + merge (used by `list`)
# ---------------------------------------------------------------------------


def _get_full_config_schema() -> dict[str, dict[str, Any]]:
    """
    Return a mapping of configuration sections to their default values.

    Attempts to obtain defaults from Pydantic models (core.v1 indexing,
    embedding, search, storage; MCP; performance; logging). If those models
    are unavailable, falls back to a minimal built-in defaults schema.
    """
    try:
        from indexed.core.v1.config_models import (
            CoreV1IndexingConfig,
            CoreV1EmbeddingConfig,
            CoreV1SearchConfig,
            CoreV1StorageConfig,
            MCPConfig,
            PerformanceConfig,
            LoggingConfig,
        )

        indexing_defaults = CoreV1IndexingConfig().model_dump()
        embedding_defaults = CoreV1EmbeddingConfig().model_dump()
        search_defaults = CoreV1SearchConfig().model_dump()
        storage_defaults = CoreV1StorageConfig().model_dump()
        mcp_defaults = MCPConfig().model_dump()
        performance_defaults = PerformanceConfig().model_dump()
        logging_defaults = LoggingConfig().model_dump()

        return {
            "core": {
                "v1": {
                    "indexing": indexing_defaults,
                    "embedding": embedding_defaults,
                    "search": search_defaults,
                    "storage": storage_defaults,
                }
            },
            "mcp": mcp_defaults,
            "performance": performance_defaults,
            "logging": logging_defaults,
            # Sources don't have defaults - they're user-configured
            "sources": {},
        }
    except ImportError:
        # Fallback if core models aren't available
        return {
            "core": {
                "v1": {
                    "indexing": {
                        "chunk_size": 512,
                        "chunk_overlap": 50,
                        "batch_size": 32,
                    },
                    "embedding": {
                        "provider": "sentence-transformers",
                        "model_name": "all-MiniLM-L6-v2",
                        "batch_size": 64,
                    },
                    "search": {
                        "max_docs": 10,
                        "max_chunks": 30,
                        "include_full_text": False,
                    },
                }
            },
            "logging": {
                "level": "WARNING",
            },
            "sources": {},
        }


def _merge_with_defaults(
    raw_config: dict[str, Any],
    defaults_schema: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Merge raw config with defaults, tracking which values are manually set.

    Returns a dict where each key maps to ``{"value": Any, "is_default": bool}``
    grouped by section.
    """
    flat_raw = _flatten_dict(raw_config) if raw_config else {}
    flat_defaults = _flatten_dict(defaults_schema) if defaults_schema else {}

    result: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    all_keys = set(flat_raw.keys()) | set(flat_defaults.keys())

    for key in sorted(all_keys):
        parts = key.split(".", 1)
        section = parts[0]
        subkey = parts[1] if len(parts) > 1 else key

        # Skip workspace - handled separately
        if section == "workspace":
            continue

        if key in flat_raw:
            result[section][subkey] = {
                "value": flat_raw[key],
                "is_default": False,
            }
        elif key in flat_defaults:
            result[section][subkey] = {
                "value": flat_defaults[key],
                "is_default": True,
            }

    return dict(result)
