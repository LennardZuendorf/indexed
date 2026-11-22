#!/usr/bin/env bash
# indexed-install-hook v1 — installed by `indexed install codex`.
#
# PreToolUse nudge: Codex has no Grep/Glob tool — it searches through the shell
# (`Bash`), so this hook watches the *command line* and, when it looks like a
# recursive text search while indexed has collections, adds a reminder pointing
# at the MCP search tools. It only adds `additionalContext`: no decision, no
# permissionDecision, so Codex's approval flow is untouched.
#
# Silent when nothing is indexed or the command is not a search, so it costs
# nothing on a machine or repo that does not use indexed.
#
# Remove with `indexed install codex --remove`.
set -uo pipefail

payload=$(cat 2>/dev/null || true)

# The collections root this install points at (`--home` is baked in here as
# shell-quoted data, so a path with $ or backticks stays literal); an
# INDEXED_COLLECTIONS_HOME in the environment still wins.
INDEXED_COLLECTIONS_DEFAULT={{COLLECTIONS_ROOT}}
INDEXED_COLLECTIONS_HOME="${INDEXED_COLLECTIONS_HOME:-$INDEXED_COLLECTIONS_DEFAULT}"

# Codex passes the session cwd in the hook payload; fall back to the process cwd.
project=""
case "$payload" in
  *'"cwd"'*)
    project=$(printf '%s' "$payload" |
      sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)
    ;;
esac
[ -n "$project" ] || project="${PWD:-}"

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

# The command line behind a `Bash` tool call; the raw payload is the fallback so
# a machine without jq still gets the nudge (and never a broken hook).
command_line=""
if command -v jq >/dev/null 2>&1; then
  command_line=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
fi
[ -n "$command_line" ] || command_line="$payload"

# Already going through indexed, or not a text search: nothing to add.
case "$command_line" in
  *indexed*) exit 0 ;;
esac
printf '%s' "$command_line" |
  grep -Eq '(^|[^[:alnum:]_])(rg|grep|egrep|fgrep|ag|ack)([^[:alnum:]_]|$)' || exit 0

context="This project has indexed collections: prefer the MCP tool mcp__indexed__search(query=\"...\") (or mcp__indexed__search_collection(collection=\"...\", query=\"...\")) over shell grep/rg for concept-based search, and follow a hit to its file:line before editing. Use shell grep only for exact patterns or non-indexed paths."

# Optional trace for debugging an install: INDEXED_HOOK_LOG=/path/to/log
if [ -n "${INDEXED_HOOK_LOG:-}" ]; then
  printf '%s command=%s project=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$command_line" "$project" >>"$INDEXED_HOOK_LOG" 2>/dev/null || true
fi

# Only quotes and backslashes can appear in the context; bash escapes both, so
# the hook needs no external tools beyond the optional jq above.
escaped=${context//\\/\\\\}
escaped=${escaped//\"/\\\"}
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"%s"}}\n' "$escaped"
