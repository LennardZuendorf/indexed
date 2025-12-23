"""Sample document generators for testing.

This module provides functions to generate sample documents
for testing different connectors and indexing scenarios.
"""

from pathlib import Path
from typing import List, Dict, Any


def create_markdown_documents(base_dir: Path, count: int = 5) -> List[Path]:
    """Create sample markdown documents.

    Args:
        base_dir: Directory to create documents in
        count: Number of documents to create

    Returns:
        List of paths to created documents
    """
    base_dir.mkdir(parents=True, exist_ok=True)
    created_files = []

    for i in range(1, count + 1):
        file_path = base_dir / f"doc{i}.md"
        content = f"""# Document {i}

## Overview

This is test document number {i}. It contains information about
various topics including authentication, API design, and testing.

## Authentication Methods

- OAuth 2.0 flow
- JWT tokens
- API keys

## API Design

RESTful endpoints with proper HTTP methods and status codes.

## Testing

Integration and unit tests for all components.
"""
        file_path.write_text(content)
        created_files.append(file_path)

    return created_files


def create_text_documents(base_dir: Path, count: int = 3) -> List[Path]:
    """Create sample plain text documents.

    Args:
        base_dir: Directory to create documents in
        count: Number of documents to create

    Returns:
        List of paths to created documents
    """
    base_dir.mkdir(parents=True, exist_ok=True)
    created_files = []

    for i in range(1, count + 1):
        file_path = base_dir / f"notes{i}.txt"
        content = f"""Notes Document {i}

Plain text notes about deployment and configuration.

Topics:
- Docker containerization
- Kubernetes orchestration
- CI/CD pipelines
- Environment configuration
"""
        file_path.write_text(content)
        created_files.append(file_path)

    return created_files


def create_confluence_mock_data() -> List[Dict[str, Any]]:
    """Generate mock Confluence page data.

    Returns:
        List of mock Confluence page dictionaries
    """
    return [
        {
            "id": "page-001",
            "title": "Architecture Overview",
            "body": {"storage": {"value": "<p>System architecture documentation</p>"}},
            "space": {"key": "TECH"},
        },
        {
            "id": "page-002",
            "title": "API Reference",
            "body": {"storage": {"value": "<p>Complete API endpoint reference</p>"}},
            "space": {"key": "TECH"},
        },
        {
            "id": "page-003",
            "title": "Deployment Guide",
            "body": {
                "storage": {"value": "<p>Step-by-step deployment instructions</p>"}
            },
            "space": {"key": "OPS"},
        },
    ]


def create_jira_mock_data() -> List[Dict[str, Any]]:
    """Generate mock Jira issue data.

    Returns:
        List of mock Jira issue dictionaries
    """
    return [
        {
            "id": "issue-001",
            "key": "PROJ-1",
            "fields": {
                "summary": "Implement authentication",
                "description": "Add OAuth 2.0 authentication support",
                "issuetype": {"name": "Story"},
                "status": {"name": "In Progress"},
            },
        },
        {
            "id": "issue-002",
            "key": "PROJ-2",
            "fields": {
                "summary": "Fix API performance",
                "description": "Optimize database queries for API endpoints",
                "issuetype": {"name": "Bug"},
                "status": {"name": "Open"},
            },
        },
        {
            "id": "issue-003",
            "key": "PROJ-3",
            "fields": {
                "summary": "Add integration tests",
                "description": "Create comprehensive integration test suite",
                "issuetype": {"name": "Task"},
                "status": {"name": "Done"},
            },
        },
    ]
