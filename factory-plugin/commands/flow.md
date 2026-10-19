---
description: Transition the vibe flow state machine to a new state
---

Transition the vibe flow: $ARGUMENTS

This command is this host's native `/flow` entry point and deliberately does not
restate the procedure. Follow the shared transition contract in
`.agents/skills/vibe/SKILL.md` (Precedence) against
`.agents/skills/vibe/state-machine.json`, then run
`bash .agents/skills/vibe/scripts/set-state.sh <target> [feature]`.
Never edit `.agents/skills/vibe/state.json` by hand.
