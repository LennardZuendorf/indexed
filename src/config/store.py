"""Configuration storage helpers for indexed.toml.

Provides atomic read/write operations with file locking and backup.
Never persists secrets - only configuration values.
"""

from pathlib import Path
from typing import List


# Fields that should never be persisted (contain secrets)
SECRET_FIELDS = {
    "api_token", "password", "token", "secret", "key", "credential"
}

# Environment variable field patterns (store env var name, not value)
ENV_VAR_FIELDS = {
    "api_token_env", "password_env", "token_env"
}

# Recommended env vars to surface for users
REQUIRED_ENV_VARS: List[str] = [
    "JIRA_API_TOKEN",
    "CONFLUENCE_API_TOKEN",
]


def ensure_env_example(required_vars: List[str] | None = None) -> None:
    """Ensure .env.example exists and contains the required variables.
    
    Appends missing variable names at the bottom of the file without duplication.
    """
    vars_list = required_vars or REQUIRED_ENV_VARS
    env_example = Path(".env.example")
    existing_lines: List[str] = []
    if env_example.exists():
        try:
            existing_lines = env_example.read_text().splitlines()
        except Exception:
            existing_lines = []
    else:
        # Create with header
        header = [
            "# Example environment variables for indexed",
            "# Copy to .env and fill in values. Do NOT commit real secrets.",
            "",
            "# Secrets are referenced by *_env fields in indexed.toml.",
            "# Example: sources.jira_cloud.api_token_env = \"JIRA_API_TOKEN\"",
            "",
        ]
        env_example.write_text("\n".join(header))
        existing_lines = header
    
    existing_keys = set()
    for line in existing_lines:
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        existing_keys.add(key)
    
    to_append: List[str] = []
    for var in vars_list:
        if var not in existing_keys:
            to_append.append(f"{var}=")
    
    if to_append:
        with env_example.open("a", encoding="utf-8") as f:
            # Only add the section header if not already present in file
            header_line = "# Required variables for Jira/Confluence integrations"
            if header_line not in existing_lines:
                f.write("\n\n" + header_line + "\n")
            for line in to_append:
                f.write(line + "\n")
