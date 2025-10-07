"""Configuration service for loading and saving TOML configs."""
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import logging

# Python 3.11+ has tomllib built-in, earlier versions need tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        raise ImportError("tomli package is required for Python < 3.11")

import tomlkit
from platformdirs import user_config_dir

from .models import IndexedConfig, WorkspaceConfig

logger = logging.getLogger(__name__)


class ConfigService:
    """Loads, validates, and saves configuration."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize config service.
        
        Args:
            config_path: Optional path to config file. If None, uses default.
        """
        self.config_path = config_path or self._default_config_path()
    
    def load_config(self, workspace_path: Optional[Path] = None) -> IndexedConfig:
        """Load and validate configuration.
        
        Args:
            workspace_path: Optional workspace path for workspace-specific config.
            
        Returns:
            Validated IndexedConfig instance.
        """
        # Load global config
        global_config = {}
        if self.config_path.exists():
            logger.info(f"Loading global config from {self.config_path}")
            global_config = self._load_toml(self.config_path)
        else:
            logger.info("No global config found, using defaults")
        
        # Load workspace config if workspace_path provided
        workspace_config = {}
        if workspace_path:
            workspace_config_path = workspace_path / ".indexed" / "config.toml"
            if workspace_config_path.exists():
                logger.info(f"Loading workspace config from {workspace_config_path}")
                workspace_config = self._load_toml(workspace_config_path)
            
            # Ensure workspace has root_path set
            if 'workspace' not in workspace_config:
                workspace_config['workspace'] = {}
            workspace_config['workspace']['root_path'] = str(workspace_path)
        
        # Merge configs (workspace takes precedence)
        merged_config = self._merge_configs(global_config, workspace_config)
        
        # If no workspace config, create minimal workspace config
        if 'workspace' not in merged_config:
            merged_config['workspace'] = {
                'root_path': str(workspace_path) if workspace_path else str(Path.cwd())
            }
        
        # Set workspace-based persistence path if not explicitly set
        if 'vector_store' not in merged_config:
            merged_config['vector_store'] = {}
        if 'persistence_path' not in merged_config['vector_store']:
            workspace_root = Path(merged_config['workspace']['root_path'])
            merged_config['vector_store']['persistence_path'] = str(workspace_root / ".indexed" / "faiss_index")
        
        # Validate with Pydantic
        try:
            return IndexedConfig(**merged_config)
        except Exception as e:
            logger.error(f"Failed to validate config: {e}")
            raise ValueError(f"Invalid configuration: {e}")
    
    def save_config(self, config: IndexedConfig, path: Optional[Path] = None) -> None:
        """Save configuration to TOML file.
        
        Args:
            config: Config to save.
            path: Optional path to save to. If None, uses self.config_path.
        """
        save_path = path or self.config_path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert Pydantic model to dict
        config_dict = config.model_dump(mode='json', exclude_none=True)
        
        # Convert Path objects to strings
        config_dict = self._serialize_paths(config_dict)
        
        # Write TOML
        with open(save_path, 'w') as f:
            tomlkit.dump(config_dict, f)
        
        logger.info(f"Saved config to {save_path}")
    
    def _load_toml(self, path: Path) -> Dict[str, Any]:
        """Load TOML file.
        
        Args:
            path: Path to TOML file.
            
        Returns:
            Dictionary of config values.
        """
        with open(path, 'rb') as f:
            return tomllib.load(f)
    
    def _merge_configs(self, global_config: Dict[str, Any], workspace_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge workspace config with global config.
        
        Workspace config takes precedence for conflicting keys.
        
        Args:
            global_config: Global configuration dictionary.
            workspace_config: Workspace configuration dictionary.
            
        Returns:
            Merged configuration dictionary.
        """
        merged = global_config.copy()
        
        # Deep merge
        for key, value in workspace_config.items():
            if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        
        return merged
    
    def _serialize_paths(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Path objects to strings recursively.
        
        Args:
            config_dict: Configuration dictionary potentially containing Path objects.
            
        Returns:
            Configuration dictionary with Paths converted to strings.
        """
        for key, value in config_dict.items():
            if isinstance(value, dict):
                config_dict[key] = self._serialize_paths(value)
            elif isinstance(value, Path):
                config_dict[key] = str(value)
        return config_dict
    
    @staticmethod
    def _default_config_path() -> Path:
        """Get default config path.
        
        Returns:
            Path to default config file.
        """
        config_dir = Path(user_config_dir("indexed", "indexed"))
        return config_dir / "config.toml"
