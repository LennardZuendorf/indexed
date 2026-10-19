#!/usr/bin/env bash
# user-prompt-submit-inject.sh — vibe flow per-turn inject hook.
#
# Event: UserPromptSubmit. Node-first: runs the engine's
# `hook user-prompt-submit-inject` (engine/commands/hook.mjs), which composes the
# level / edge / event channels — the current state and its transition command,
# the full orders on a cursor change, and any drift nudge or queued warning.
#
# DEGRADE (no node, no engine, or an unexpected engine exit code): exit 0
# silently. This hook only injects text, so losing it costs guidance, not
# enforcement. It never exits 2.
set -euo pipefail

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# `${BASH}` — the absolute path of the shell already running this script — not a
# bare `bash`, which resolves through PATH. A no-jq/no-node test shim (and a
# genuinely minimal PATH) can lack `bash` entirely, and then the hook dies with
# `exec: bash: not found` and exit 127 instead of answering.
exec "${BASH:-bash}" "$HOOKS_DIR/_engine-hook.sh" user-prompt-submit-inject ""
