#!/usr/bin/env bash
# indexed-install-hook v1 — installed by `indexed install claude-code`.
#
# PreToolUse nudge: when Claude reaches for Grep/Glob inside a project that has
# indexed collections, remind it that semantic search exists. Non-blocking — the
# tool still runs (permissionDecision "allow" prints the reason, it never denies).
#
# Silent everywhere else — the two layouts indexed can store collections in are
# (a) the global store under $HOME/.indexed/data/collections (the default), and
# (b) a workspace pointer at <project>/.indexed/collections.json (what
# `indexed storage migrate` writes). With neither, this exits 0 with no output,
# so it costs nothing on a machine or repo that does not use indexed.
#
# Remove with `indexed install claude-code --remove`.
set -uo pipefail

payload=$(cat 2>/dev/null || true)

project="${CLAUDE_PROJECT_DIR:-${PWD:-}}"

indexed=false
if [ -f "${project:-/nonexistent}/.indexed/collections.json" ]; then
  indexed=true
fi
set -- "${HOME:-/nonexistent}"/.indexed/data/collections/*/
if [ -d "$1" ]; then
  indexed=true
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

reason="This project has indexed collections: prefer mcp__indexed__search(query=\"...\") or mcp__indexed__search_collection(collection=\"...\", query=\"...\") over ${tool} for concept-based search, and follow a hit to its file:line before editing. Use ${tool} only for exact patterns or filenames."

# Optional trace for debugging an install: INDEXED_HOOK_LOG=/path/to/log
if [ -n "${INDEXED_HOOK_LOG:-}" ]; then
  printf '%s tool=%s project=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$tool" "$project" >>"$INDEXED_HOOK_LOG" 2>/dev/null || true
fi

# Only quotes and backslashes can appear in the reason; bash escapes both, so
# the hook needs no external tools beyond the optional jq above.
escaped=${reason//\\/\\\\}
escaped=${escaped//\"/\\\"}
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"%s"}}\n' "$escaped"
