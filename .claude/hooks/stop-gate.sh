#!/usr/bin/env bash
# stop-gate.sh — vibe flow gate hook.
#
# Event: Stop. Node-first: runs the engine's `hook stop-gate`
# (engine/commands/hook.mjs) — re-entry guard on stop_hook_active, warn-only TDD
# and stuck-phase nudges, and the one promoted blocking tooth: a `*.verify` state
# needs a fresh evidence receipt. Cursor and machine reads are pure JS, so there
# is no no-jq branch to reproduce here.
#
# DEGRADE (no node, no engine, or an unexpected engine exit code):
# `.agents/skills/vibe/hooks-fallback/stop-gate.sh` — the frozen pre-port
# implementation — answers instead. The evidence tooth is a HARD BLOCK the docs
# promise; it degrades to bash, never to nothing.
set -euo pipefail

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
FALLBACK_DIR="${VIBE_HOOKS_FALLBACK:-$ROOT/.agents/skills/vibe/hooks-fallback}"

# `${BASH}` — the absolute path of the shell already running this script — not a
# bare `bash`, which resolves through PATH. A no-jq/no-node test shim (and a
# genuinely minimal PATH) can lack `bash` entirely, and then the hook dies with
# `exec: bash: not found` and exit 127 instead of answering.
exec "${BASH:-bash}" "$HOOKS_DIR/_engine-hook.sh" stop-gate "$FALLBACK_DIR/stop-gate.sh"
