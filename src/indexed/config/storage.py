"""Storage path resolution for indexed.

There is exactly ONE storage root (workspace-profile/1, R1). Collections and
caches always live under ``~/.indexed/data/``; the former local root
(``./.indexed/data/``), the ``--local`` flag, the ``[workspace].mode``
preference and the storage-mode cascade are gone. A workspace narrows and
overrides (see ``workspace.py``); it never relocates data.

    ~/.indexed/
    ├── config.toml               # Global configuration
    ├── .env                      # Sensitive credentials
    └── data/
        ├── collections/          # Index storage
        └── caches/               # Document caches
"""

from __future__ import annotations

from pathlib import Path


def get_global_root() -> Path:
    """Get the one storage root directory.

    Returns:
        Path to ~/.indexed
    """
    return Path.home() / ".indexed"


def get_config_path(root: Path) -> Path:
    """
    Return the path to the config.toml file inside the provided storage root.

    Parameters:
        root (Path): Storage root directory.

    Returns:
        Path: Path to the config.toml file within the root
    """
    return root / "config.toml"


def get_env_path(root: Path) -> Path:
    """
    Return the path to the .env file inside the given storage root.

    Parameters:
        root (Path): Storage root directory.

    Returns:
        Path: Path to the `.env` file within `root`.
    """
    return root / ".env"


def get_data_root(root: Path) -> Path:
    """
    Resolve the path to the data directory inside a storage root.

    Parameters:
        root (Path): Storage root directory.

    Returns:
        Path: Path to the `data` directory within the given root.
    """
    return root / "data"


def get_collections_path(root: Path) -> Path:
    """Get the collections directory for a given root.

    Args:
        root: Storage root directory

    Returns:
        Path to data/collections within the root
    """
    return get_data_root(root) / "collections"


def get_caches_path(root: Path) -> Path:
    """Get the caches directory for a given root.

    Args:
        root: Storage root directory

    Returns:
        Path to data/caches within the root
    """
    return get_data_root(root) / "caches"


def get_global_collections_path() -> Path:
    """Path to the one collections directory (``~/.indexed/data/collections``)."""
    return get_collections_path(get_global_root())


def get_global_caches_path() -> Path:
    """Path to the one caches directory (``~/.indexed/data/caches``)."""
    return get_caches_path(get_global_root())


def has_global_config() -> bool:
    """
    Determine whether the global config file (~/.indexed/config.toml) exists.

    Returns:
        `true` if the global config file exists at ~/.indexed/config.toml, `false` otherwise.
    """
    return get_config_path(get_global_root()).exists()


def ensure_storage_dirs(root: Path) -> None:
    """
    Create the storage root and its data, collections, and caches subdirectories if they do not exist.

    Parameters:
        root (Path): Root directory under which `data`, `data/collections`, and `data/caches` will be created.
    """
    root.mkdir(parents=True, exist_ok=True)
    get_data_root(root).mkdir(parents=True, exist_ok=True)
    get_collections_path(root).mkdir(parents=True, exist_ok=True)
    get_caches_path(root).mkdir(parents=True, exist_ok=True)
