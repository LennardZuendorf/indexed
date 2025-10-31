"""Configuration schemas for Confluence connectors."""

import os
from typing import Optional

from pydantic import BaseModel, Field


class ConfluenceConfig(BaseModel):
    """Configuration for Confluence Server/Data Center."""

    url: str = Field(..., description="Confluence base URL")
    query: str = Field(..., description="CQL query to filter pages")
    token: Optional[str] = Field(None, description="Bearer token (env: CONF_TOKEN)")
    login: Optional[str] = Field(None, description="Username (env: CONF_LOGIN)")
    password: Optional[str] = Field(None, description="Password (env: CONF_PASSWORD)")
    read_all_comments: bool = Field(
        default=True, description="Read nested comments (yes/no)"
    )

    def get_token(self) -> Optional[str]:
        """Get token from config or environment."""
        return self.token or os.getenv("CONF_TOKEN")

    def get_login(self) -> Optional[str]:
        """Get login from config or environment."""
        return self.login or os.getenv("CONF_LOGIN")

    def get_password(self) -> Optional[str]:
        """Get password from config or environment."""
        return self.password or os.getenv("CONF_PASSWORD")


class ConfluenceCloudConfig(BaseModel):
    """Configuration for Confluence Cloud."""

    url: str = Field(..., description="Confluence Cloud URL (*.atlassian.net)")
    query: str = Field(..., description="CQL query to filter pages")
    email: str = Field(
        ..., description="Atlassian account email (env: ATLASSIAN_EMAIL)"
    )
    api_token: str = Field(
        ..., description="API token (env: ATLASSIAN_TOKEN)"
    )
    read_all_comments: bool = Field(
        default=True, description="Read nested comments (yes/no)"
    )

    def get_email(self) -> str:
        """Get email from config or environment."""
        return self.email or os.getenv("ATLASSIAN_EMAIL", "")

    def get_api_token(self) -> str:
        """Get API token from config or environment."""
        token = self.api_token or os.getenv("ATLASSIAN_TOKEN")
        if not token:
            raise ValueError("ATLASSIAN_TOKEN not set in config or environment")
        return token


__all__ = ["ConfluenceConfig", "ConfluenceCloudConfig"]


