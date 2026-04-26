"""Environment file writer for sensitive configuration values."""

from __future__ import annotations

import os
import re
from typing import Callable, List

from pydantic.fields import FieldInfo

_SENSITIVE_PATTERNS = ["token", "password", "secret", "api_key", "api_token"]


class EnvFileWriter:
    """Write sensitive config values to .env files."""

    def __init__(self, get_env_path: Callable[[], str]) -> None:
        self._get_env_path = get_env_path

    def write(self, key: str, value: str) -> None:
        """Write or update an environment variable in the .env file."""
        env_path = self._get_env_path()

        existing_lines: List[str] = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                existing_lines = f.readlines()

        key_found = False
        updated_lines: List[str] = []
        for line in existing_lines:
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                updated_lines.append(f"{key}={value}\n")
                key_found = True
            else:
                updated_lines.append(line if line.endswith("\n") else line + "\n")

        if not key_found:
            updated_lines.append(f"{key}={value}\n")

        os.makedirs(os.path.dirname(env_path), exist_ok=True)

        with open(env_path, "w") as f:
            f.writelines(updated_lines)

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
