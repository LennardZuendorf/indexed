"""Outline Wiki connector for Cloud and self-hosted deployments."""

from .connector import OutlineConnector
from .schema import OUTLINE_CLOUD_URL, OutlineConfig

__all__ = ["OUTLINE_CLOUD_URL", "OutlineConfig", "OutlineConnector"]
