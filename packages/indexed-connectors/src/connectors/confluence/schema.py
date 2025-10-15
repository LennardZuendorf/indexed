"""Configuration schemas for Confluence connectors."""

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


__all__ = ["ConfluenceConfig", "ConfluenceCloudConfig"]


