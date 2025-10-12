"""Connector metadata and type definitions.

This module defines lightweight metadata used by the CLI to dynamically
discover connector capabilities and generate validated prompts using
Pydantic configuration models.
"""

from dataclasses import dataclass
from typing import Optional, Type

from pydantic import BaseModel


@dataclass
class ConnectorMetadata:
    """Metadata describing a connector's CLI interface.

    Attributes:
        name: Short CLI identifier (e.g., "files", "jira").
        display_name: Human-readable name for help/UX.
        description: Short description shown in help text.
        config_class: Pydantic model class for configuration validation.
        version: Version of the connector definition.
        min_core_version: Minimum core version required for compatibility.
        example: Optional example CLI usage string.
    """

    # Identity
    name: str
    display_name: str
    description: str

    # Configuration schema
    config_class: Type[BaseModel]

    # Versioning
    version: str = "1.0.0"
    min_core_version: Optional[str] = None

    # CLI hints
    example: Optional[str] = None


__all__ = ["ConnectorMetadata"]


