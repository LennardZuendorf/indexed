---
description: Transition the vibe flow state machine to a new state
argument-hint: <flow.phase> [feature] [confirm]
---

You have been asked to transition the vibe flow: $ARGUMENTS

Parse `$ARGUMENTS` into up to three parts (whitespace-separated):

- **target** — the first token, a `<flow.phase>` state key (e.g. `feature.design`, `idle`).
- **confirm** — the literal token `confirm`, if present anywhere after the target: the
  human-approval token that unlocks a gated edge.
- **feature** — any remaining non-`confirm` token: the feature name to carry into the cursor.

Do exactly this, in order:

1. Read `.agents/skills/vibe/state.json` for the current `<flow>.<phase>` (treat a
   missing/invalid cursor as `idle`).
2. Read `.agents/skills/vibe/state-machine.json` for that state's `next` array and its
   `gates` object.
3. **Abort is always legal.** If **target** is `idle`, skip the membership and gate
   checks (steps 4–5) and go straight to the transition (step 6).
4. **Membership.** If **target** is NOT in the current state's `next`, refuse: print the
   current state and the legal `next` values, and stop. Do not write.
5. **Gate teeth.** Form the edge key `<current>><target>` (e.g. `feature.plan>feature.impl`).
   If that key exists in `gates` AND **confirm** was NOT supplied, STOP: print the gate's
   requirement text from `gates` and tell the user to re-run with the approval token in the
   same message (e.g. `/flow feature.impl confirm`). Do not write. (`idle` is never gated —
   it was already handled in step 3.)
6. **Transition.** Run `.agents/skills/vibe/scripts/set-state.sh <target> [feature]` — pass
   **feature** as the second argument only when it was supplied; otherwise omit it so the
   existing `feature` is preserved (`idle` clears it). Never write `state.json` directly.
   There is no `notes` field, and `confirm` is a command token — never pass it to
   `set-state.sh`.
7. Print a one-line confirmation: `→ <new_state>`.

Continue directly into the new state's work now — do not wait for the next user prompt.
