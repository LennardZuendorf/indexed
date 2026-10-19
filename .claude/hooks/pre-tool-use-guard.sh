#!/usr/bin/env bash
# pre-tool-use-guard.sh — vibe flow guard hook.
#
# Event: PreToolUse, matcher Edit|Write|NotebookEdit|Bash. Node-first: runs the
# engine's `hook pre-tool-use-guard` (engine/commands/hook.mjs), which owns the
# stdin parsing, the warn-only Bash write sniffer, the warnings relay, and the
# exit-code translation. Path POLICY is not here and not in the engine either —
# both ask content/policy.json through `detect-context.sh decide`.
#
# DEGRADE (no node, no engine, or an unexpected engine exit code):
# `.agents/skills/vibe/hooks-fallback/pre-tool-use-guard.sh` — the frozen pre-port
# implementation — answers instead. This hook carries a HARD BLOCK, so losing it
# to a missing runtime is not acceptable: enforcement degrades to bash, never to
# nothing. It still never inverts an allow into a spurious exit 2.
set -euo pipefail

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
FALLBACK_DIR="${VIBE_HOOKS_FALLBACK:-$ROOT/.agents/skills/vibe/hooks-fallback}"

# `${BASH}` — the absolute path of the shell already running this script — not a
# bare `bash`, which resolves through PATH. A no-jq/no-node test shim (and a
# genuinely minimal PATH) can lack `bash` entirely, and then the hook dies with
# `exec: bash: not found` and exit 127 instead of answering.
exec "${BASH:-bash}" "$HOOKS_DIR/_engine-hook.sh" pre-tool-use-guard "$FALLBACK_DIR/pre-tool-use-guard.sh"
