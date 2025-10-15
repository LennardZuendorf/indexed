"""Configuration storage helpers for indexed.toml.

Provides atomic read/write operations with file locking and backup.
Never persists secrets - only configuration values.
"""

import os
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List
import tomllib
import tomli_w
import portalocker


# Fields that should never be persisted (contain secrets)
SECRET_FIELDS = {"api_token", "password", "token", "secret", "key", "credential"}

# Environment variable field patterns (store env var name, not value)
ENV_VAR_FIELDS = {"api_token_env", "password_env", "token_env"}


def get_config_path() -> Path:
    """Get path to indexed.toml in project root."""
    return Path("indexed.toml")


def get_backup_path() -> Path:
    """Get path to backup file."""
    return Path("indexed.toml.bak")


def get_lock_path() -> Path:
    """Get path to lock file."""
    return Path("indexed.toml.lock")


def _is_secret_field(key_path: str) -> bool:
    """Check if a field path contains secrets that should not be persisted."""
    key_lower = key_path.lower()
    return any(secret in key_lower for secret in SECRET_FIELDS)


def _filter_secrets(data: Dict[str, Any], path: str = "") -> Dict[str, Any]:
    """Recursively filter out secret values from configuration data.

    Args:
        data: Configuration dictionary
        path: Current key path for nested checking

    Returns:
        Filtered dictionary with secrets removed
    """
    if not isinstance(data, dict):
        return data
    filtered: Dict[str, Any] = {}
    for key, value in data.items():
        current_path = f"{path}.{key}" if path else key
        # Keep env var name fields even if they contain secret-like substrings
        if key in ENV_VAR_FIELDS:
            filtered[key] = value
            continue
        # Skip actual secret fields entirely
        if _is_secret_field(current_path):
            continue
        if isinstance(value, dict):
            filtered_nested = _filter_secrets(value, current_path)
            filtered[key] = filtered_nested
        else:
            filtered[key] = value
    return filtered


def read_toml(path: Path | None = None) -> Dict[str, Any]:
    """Read TOML file safely with a shared lock.

    Returns an empty dict if file doesn't exist.
    """
    file_path = path or get_config_path()
    if not file_path.exists():
        return {}
    with portalocker.Lock(get_lock_path(), timeout=5):
        with file_path.open("rb") as f:
            return tomllib.load(f)


def atomic_write_toml(data: Dict[str, Any], path: Path | None = None) -> None:
    """Atomically write TOML with backup and file lock, filtering secrets."""
    file_path = path or get_config_path()
    filtered = _filter_secrets(data)
    tmp_fd = None
    with portalocker.Lock(get_lock_path(), timeout=5):
        try:
            with tempfile.NamedTemporaryFile("wb", delete=False) as tmp:
                tmp_fd = tmp.name
                tomli_w.dump(filtered, tmp)
            # Backup existing file if present
            if file_path.exists():
                shutil.copy2(file_path, get_backup_path())
            # Move in the new file atomically
            os.replace(tmp_fd, file_path)
        finally:
            if tmp_fd and os.path.exists(tmp_fd):
                try:
                    os.unlink(tmp_fd)
                except Exception:
                    pass


def validate_no_secrets(data: Dict[str, Any]) -> None:
    """Validate that data does not contain secret values, only *_env placeholders."""

    def _check_secrets(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                if _is_secret_field(current_path) and key not in ENV_VAR_FIELDS:
                    raise ValueError(
                        f"Secret field '{current_path}' cannot be persisted"
                    )
                _check_secrets(value, current_path)
        elif isinstance(obj, (list, tuple)):
            for i, item in enumerate(obj):
                _check_secrets(item, f"{path}[{i}]")

    _check_secrets(data)


# Recommended env vars to surface for users
REQUIRED_ENV_VARS: List[str] = [
    "JIRA_API_TOKEN",
    "CONFLUENCE_API_TOKEN",
]


def ensure_indexed_toml_exists() -> None:
    """Ensure that an indexed.toml file exists with a full commented scaffold.

    Creates a safe, non-secret scaffold if missing, including notes on required/optional fields.
    """
    path = get_config_path()
    if path.exists():
        return

    template = """
# Indexed configuration (indexed.toml)
# Notes:
# - These are explicit defaults so you can see and edit the configuration
# - Do NOT put secrets here; use environment variables referenced by *_env fields
# - Unknown keys will be ignored

[paths]
collections_dir = "./data/collections"
caches_dir = "./data/caches"
temp_dir = "./tmp"

[search]
max_docs = 10
max_chunks = 30
include_full_text = false
include_all_chunks = false
include_matched_chunks = false
# Set to a number 0.0..1.0 to filter by similarity; leave empty for no threshold
# score_threshold = 

[index]
default_indexer = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"
embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
embedding_batch_size = 64
use_gpu = false

[sources.files]
base_path = "./data"
include_patterns = ["*.md", "*.txt", "*.pdf", "*.pptx"]
exclude_patterns = []
follow_symlinks = false
max_file_size_mb = 50

[sources.jira_cloud]
# base_url = "https://your-domain.atlassian.net" # required
# email = "you@company.com" # required
api_token_env = "JIRA_API_TOKEN"
jql = "project = CURRENT"
max_results = 100
timeout_sec = 30

[sources.confluence_cloud]
# base_url = "https://your-domain.atlassian.net/wiki" # required
# email = "you@company.com" # required
api_token_env = "CONFLUENCE_API_TOKEN"
cql = "space = DEV"
include_comments = false
page_limit = 100
timeout_sec = 30

[mcp]
host = "localhost"
port = 8000
log_level = "WARNING"
enable_async_pool = false
mcp_json_output = true

[performance]
enable_cache = true
cache_max_entries = 32
log_sqlite_queries = false

[flags]
enable_profiles = true
cli_json_output = false

[logging]
level = "WARNING"  # one of: DEBUG, INFO, WARNING, ERROR, CRITICAL
as_json = false     # set true for JSON (structured) logs
""".lstrip()

    # Write template directly (no secrets and comments preserved)
    path.write_text(template, encoding="utf-8")


def ensure_env_example(required_vars: List[str] | None = None) -> None:
    """Ensure .env.example exists and contains the required variables.

    Appends missing variable names at the bottom of the file.
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
            '# Example: sources.jira_cloud.api_token_env = "<ENV_VAR_NAME>"',
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
            f.write("\n\n# Required variables for Jira/Confluence integrations\n")
            for line in to_append:
                f.write(line + "\n")
