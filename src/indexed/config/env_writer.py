"""Environment file writer for sensitive configuration values."""

from __future__ import annotations

import os
import re
from collections.abc import Callable

from pydantic.fields import FieldInfo

_SENSITIVE_PATTERNS = ["token", "password", "secret", "api_key", "api_token"]


def _dotenv_quote(value: str) -> str:
    """Double-quote a value per dotenv's quoted-value grammar (C4).

    Escapes backslash and double-quote characters so the *same* dotenv parser
    the app loads with (``python-dotenv``) reconstructs the value byte-
    identical — a raw ``KEY=value`` write truncates at the first `` #``
    (comment) and mangles embedded quotes/backslashes on reload.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class EnvFileWriter:
    """Write sensitive config values to .env files."""

    def __init__(self, get_env_path: Callable[[], str]) -> None:
        self._get_env_path = get_env_path

    def write(self, key: str, value: str) -> None:
        """Write or update an environment variable in the .env file."""
        env_path = self._get_env_path()

        existing_lines: list[str] = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                existing_lines = f.readlines()

        quoted_value = _dotenv_quote(value)

        key_found = False
        updated_lines: list[str] = []
        # Regex to match export-prefixed keys: optional "export " prefix followed by KEY=
        key_pattern = re.compile(rf"^(export\s+)?{re.escape(key)}\s*=")

        for line in existing_lines:
            stripped = line.strip()
            match = key_pattern.match(stripped)
            if match:
                # Preserve the export prefix if present
                export_prefix = match.group(1) or ""
                updated_lines.append(f"{export_prefix}{key}={quoted_value}\n")
                key_found = True
            else:
                updated_lines.append(line if line.endswith("\n") else line + "\n")

        if not key_found:
            updated_lines.append(f"{key}={quoted_value}\n")

        os.makedirs(os.path.dirname(env_path), exist_ok=True)

        # Atomic write: tmp -> fsync -> chmod 0600 -> os.replace (mirror
        # TomlStore.write pattern). The temp file is a fresh inode with
        # umask-derived permissions, so it must be hardened to 0600 before
        # the replace or the resulting .env would leak to group/world read.
        tmp = env_path + ".tmp"
        try:
            with open(tmp, "w") as f:
                f.writelines(updated_lines)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, env_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @staticmethod
    def is_sensitive_field(field_name: str) -> bool:
        """Detect whether a field name indicates sensitive data."""
        name_lower = field_name.lower()
        return any(pattern in name_lower for pattern in _SENSITIVE_PATTERNS)

    @staticmethod
    def get_env_var_name(field_name: str, field: FieldInfo) -> str | None:
        """Determine the environment variable name for a config field.

        Checks the field description for an explicit 'env: NAME' hint.
        """
        desc = field.description or ""
        if "env:" in desc.lower():
            match = re.search(r"env:\s*(\w+)", desc, re.IGNORECASE)
            if match:
                return match.group(1)

        return None
