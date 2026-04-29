#!/usr/bin/env bash
# PreToolUse nudge: remind Claude about the indexed MCP server when
# Grep/Glob is used. Non-blocking — the tool still runs.
set -euo pipefail

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "Grep"')

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "Reminder: This project has the 'indexed' MCP server with semantic search. Prefer mcp__indexed__search(query=\"...\") or mcp__indexed__search_collection(collection=\"...\", query=\"...\") over $TOOL_NAME for concept-based code search. Use $TOOL_NAME only for exact pattern / filename matching."
  }
}
EOF
