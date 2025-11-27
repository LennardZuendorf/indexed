from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

# TOML read (tomllib on 3.11+, fallback to tomli)
if sys.version_info >= (3, 11):
    import tomllib  # type: ignore
else:
    try:
        import tomli as tomllib  # type: ignore
    except Exception:
        tomllib = None  # type: ignore

import tomlkit
from platformdirs import user_config_dir

from .path_utils import deep_merge


class TomlStore:
    """Read/write config with merge: Global, Workspace, ENV.

    - Global: ~/.config/indexed/config.toml
    - Workspace: ./.indexed/config.toml (overrides global)
    - ENV overrides: INDEXED__section__key=value (overrides both)
    """

    def __init__(self, *, workspace: Optional[Path] = None) -> None:
        self.workspace = workspace or Path.cwd()

    @property
    def global_path(self) -> Path:
        return Path(user_config_dir("indexed", "indexed")) / "config.toml"

    @property
    def workspace_path(self) -> Path:
        return self.workspace / ".indexed" / "config.toml"
    
    @property
    def env_path(self) -> Path:
        """Path to the .env file for sensitive values."""
        return self.workspace / ".indexed" / ".env"
    
    def get_env_path(self) -> str:
        """Get the .env file path as string."""
        return str(self.env_path)

    def _read_toml_file(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, "rb") as f:
            if tomllib is None:
                raise RuntimeError("tomllib/tomli not available for reading TOML")
            return tomllib.load(f)  # type: ignore

    def read(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        # Global
        data = deep_merge(data, self._read_toml_file(self.global_path))
        # Workspace
        data = deep_merge(data, self._read_toml_file(self.workspace_path))
        # Load .env file if it exists (before checking os.environ)
        self._load_dotenv()
        # ENV
        env_data = self._env_to_mapping()
        data = deep_merge(data, env_data)
        return data
    
    def _load_dotenv(self) -> None:
        """Load .indexed/.env file into environment if it exists."""
        if not self.env_path.exists():
            return
        
        with open(self.env_path, "r") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                # Parse KEY=value
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    # Only set if not already in environment (env takes precedence)
                    if key not in os.environ:
                        os.environ[key] = value

    def write(self, data: Mapping[str, Any]) -> None:
        # Write to workspace file only (single writable source)
        target = self.workspace_path
        target.parent.mkdir(parents=True, exist_ok=True)
        # Preserve ordering but we just dump mapping
        with open(target, "w", encoding="utf-8") as f:
            tomlkit.dump(dict(data), f)

    def _env_to_mapping(self) -> Dict[str, Any]:
        """Convert INDEXED__A__B=val env vars to nested dict {"a": {"b": val}}.
        Values are left as strings; Pydantic will coerce types on bind().
        """
        prefix = "INDEXED__"
        out: Dict[str, Any] = {}
        for k, v in os.environ.items():
            if not k.startswith(prefix):
                continue
            parts = [p for p in k[len(prefix):].split("__") if p]
            if not parts:
                continue
            cur = out
            for seg in parts[:-1]:
                seg = seg.lower()
                cur = cur.setdefault(seg, {})  # type: ignore[assignment]
            cur[parts[-1].lower()] = v
        return out
