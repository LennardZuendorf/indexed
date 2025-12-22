"""Mock API response data for testing.

This module provides sample API responses that match the structure
of real Confluence and Jira API responses.
"""

# Confluence API responses
CONFLUENCE_PAGE_RESPONSE = {
    "results": [
        {
            "id": "123456",
            "title": "Authentication Guide",
            "type": "page",
            "body": {
                "storage": {
                    "value": "<h1>Authentication Methods</h1><p>This page covers OAuth 2.0 and JWT authentication.</p>"
                }
            },
            "space": {"key": "DEV"},
            "_links": {"webui": "/display/DEV/Authentication+Guide"},
        }
    ],
    "size": 1,
    "limit": 25,
    "start": 0,
}

CONFLUENCE_EMPTY_RESPONSE = {"results": [], "size": 0, "limit": 25, "start": 0}

# Jira API responses
JIRA_ISSUE_RESPONSE = {
    "issues": [
        {
            "id": "10001",
            "key": "PROJ-123",
            "fields": {
                "summary": "Implement OAuth authentication",
                "description": "Add OAuth 2.0 authentication to the API",
                "issuetype": {"name": "Story"},
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "John Doe"},
            },
        }
    ],
    "total": 1,
    "maxResults": 50,
    "startAt": 0,
}

JIRA_EMPTY_RESPONSE = {"issues": [], "total": 0, "maxResults": 50, "startAt": 0}
