#!/usr/bin/env bash
# _engine-hook.sh — the shared body of all four vibe hook shims.
#
#   bash _engine-hook.sh <hook-name> [fallback-script]
#
# Runs the Node engine's `hook <name>` command and decides what a failure means.
# Not wired into settings.json itself — the four named hooks are; this is what
# they all call, so the degrade policy is written once.
#
# WHY THIS EXISTS (js-core review): the shims used to be
# `command -v node || exit 0` followed by `exec node …`, which has two holes.
#
#  1. A node-less target lost the guard's hard block and the Stop gate's
#     evidence tooth ENTIRELY, silently — while detect-context.sh's own header
#     promised "a target without node must still be enforced". A hook with a
#     fallback now execs it instead of exiting 0. Enforcement degrades to bash,
#     never to nothing.
#  2. `exec node` on a PRESENT-but-broken engine (a half-written file, a version
#     skew) printed a raw Node stack trace on EVERY prompt and tool call. stdout
#     and stderr are buffered here and relayed only for the two exit codes the
#     hook protocol defines; anything else is a broken engine, not a verdict.
#
# Exit-code contract: 0 = proceed, 2 = block. Those pass through byte-exact,
# including the engine's own stderr. Any other code (a crash, a signal) is
# treated as "the engine could not answer": a hook WITH a fallback runs it, a
# hook WITHOUT one exits 0 with a single-line note. Never exit 2 on a path that
# did not genuinely block.
#
# stdin is read ONCE here and replayed into whichever implementation answers —
# the engine consumes it, so a fallback spawned afterwards would otherwise see
# an empty payload.

set -euo pipefail

HOOK_NAME="${1:-}"
FALLBACK="${2:-}"
[[ -n "$HOOK_NAME" ]] || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
ENGINE="${VIBE_ENGINE:-$ROOT/.agents/skills/vibe/engine}"

PAYLOAD="$(cat 2>/dev/null || true)"

# run_fallback — hand the same stdin to the frozen bash implementation and adopt
# its exit code verbatim (that is where the block lives).
run_fallback() {
  if [[ -n "$FALLBACK" && -f "$FALLBACK" ]]; then
    printf '%s' "$PAYLOAD" | "${BASH:-bash}" "$FALLBACK"
    exit $?
  fi
  exit 0
}

command -v node >/dev/null 2>&1 || run_fallback
[[ -f "$ENGINE/cli.mjs" ]] || run_fallback

# Buffer stderr so a crash's stack trace can be withheld — but ONLY if a temp
# file is actually available. A minimal PATH may have no `mktemp`, and losing a
# real BLOCK message is far worse than relaying a stack trace, so that case runs
# with stderr inherited and keeps the message.
ERRFILE="$(mktemp 2>/dev/null || true)"

rc=0
if [[ -n "$ERRFILE" ]]; then
  OUT="$(printf '%s' "$PAYLOAD" | node "$ENGINE/cli.mjs" hook "$HOOK_NAME" 2>"$ERRFILE")" || rc=$?
else
  OUT="$(printf '%s' "$PAYLOAD" | node "$ENGINE/cli.mjs" hook "$HOOK_NAME")" || rc=$?
fi

relay_stderr() {
  [[ -n "$ERRFILE" && -s "$ERRFILE" ]] || return 0
  while IFS= read -r _l || [[ -n "$_l" ]]; do printf '%s\n' "$_l" >&2; done < "$ERRFILE"
}

case "$rc" in
  0|2)
    if [[ -n "$OUT" ]]; then printf '%s\n' "$OUT"; fi
    relay_stderr
    if [[ -n "$ERRFILE" ]]; then rm -f "$ERRFILE"; fi
    exit "$rc"
    ;;
esac

# Unexpected exit code: the engine crashed rather than answered. Its stack trace
# is deliberately NOT relayed when it could be buffered — one line is enough to
# diagnose, and a trace on every turn is noise the user cannot act on.
if [[ -n "$ERRFILE" ]]; then rm -f "$ERRFILE"; fi
if [[ -n "$FALLBACK" && -f "$FALLBACK" ]]; then
  echo "vibe: engine failed (exit $rc) for hook '$HOOK_NAME' — using the bash fallback" >&2
else
  echo "vibe: engine failed (exit $rc) for hook '$HOOK_NAME' — skipping this hook" >&2
fi
run_fallback
