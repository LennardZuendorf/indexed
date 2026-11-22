#!/usr/bin/env bash
# indexed-install-hook v1 — installed by `indexed install claude-code`.
#
# PreToolUse nudge: when Claude reaches for Grep/Glob while indexed has
# collections, put a reminder in its context pointing at the MCP search tools.
# It never decides permissions — no `permissionDecision` is emitted, so the
# normal permission flow (including the outside-directory prompt) is untouched;
# only `additionalContext` is added, which Claude Code attaches to the tool
# result.
#
# Silent when nothing is indexed: with no workspace pointer and nothing in the
# collections root below, this exits 0 with no output, so it costs nothing on a
# machine or repo that does not use indexed.
#
# Remove with `indexed install claude-code --remove`.
set -uo pipefail

payload=$(cat 2>/dev/null || true)

# The collections root this install points at (`--home` is baked in here);
# an INDEXED_COLLECTIONS_HOME in the environment still wins.
INDEXED_COLLECTIONS_HOME="${INDEXED_COLLECTIONS_HOME:-{{COLLECTIONS_ROOT}}}"

project="${CLAUDE_PROJECT_DIR:-${PWD:-}}"

indexed=false
if [ -n "$project" ] && [ -f "$project/.indexed/collections.json" ]; then
  indexed=true
fi
if [ "$indexed" = false ] && [ -n "$INDEXED_COLLECTIONS_HOME" ]; then
  for candidate in "$INDEXED_COLLECTIONS_HOME"/*; do
    if [ -e "$candidate" ]; then
      indexed=true
      break
    fi
  done
fi
[ "$indexed" = true ] || exit 0

tool=""
if command -v jq >/dev/null 2>&1; then
  tool=$(printf '%s' "$payload" | jq -r '.tool_name // empty' 2>/dev/null || true)
fi
if [ -z "$tool" ]; then
  case "$payload" in
    *Grep*) tool="Grep" ;;
    *Glob*) tool="Glob" ;;
    *) tool="Grep/Glob" ;;
  esac
fi

context="This project has indexed collections: prefer mcp__indexed__search(query=\"...\") or mcp__indexed__search_collection(collection=\"...\", query=\"...\") over ${tool} for concept-based search, and follow a hit to its file:line before editing. Use ${tool} only for exact patterns or filenames."

# Optional trace for debugging an install: INDEXED_HOOK_LOG=/path/to/log
if [ -n "${INDEXED_HOOK_LOG:-}" ]; then
  printf '%s tool=%s project=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$tool" "$project" >>"$INDEXED_HOOK_LOG" 2>/dev/null || true
fi

# Only quotes and backslashes can appear in the context; bash escapes both, so
# the hook needs no external tools beyond the optional jq above.
escaped=${context//\\/\\\\}
escaped=${escaped//\"/\\\"}
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"%s"}}\n' "$escaped"
