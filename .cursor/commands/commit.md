---
title: Cursor Commit Command Rule
links:
  - "@.cursor/rules/actions/commit.mdc"
---

# Cursor Commit Command Rule

## Absolute Commit Workflow Standard

**All commit operations _MUST_ follow this strict flow. NO EXCEPTIONS.**

1. **Cluster Changes Thematically**
   - Analyse all staged and unstaged changes.
   - Propose clear, logical clusters based on what the changes _do_ (feature, fix, refactor, chore, etc.).
   - Present the suggested clusters _to the user for feedback_.
   - If uncertain, _ask and require user guidance_ on how to group changes for commit.
   - Never merge unrelated changes into one commit. Each commit must contain only _one logical change_.

2. **Stage and Draft**
   - Stage ONLY the files belonging to the first selected/confirmed cluster.
   - Draft a commit message in the exact format and constraints outlined in [@.cursor/rules/actions/commit.mdc]—use `feat`, `fix`, or `chore` as appropriate.
   - SHOW the draft message and files to the user for final confirmation _before actually committing_.

3. **Commit with Guardrails**
   - Run the commit _and wait for the pre-commit hook to finish_.
   - If the pre-commit hook fails or modifies files (e.g., formatting, linting):
       - Re-stage those updated files if the changes are purely cosmetic or formatting.
       - If errors remain, prompt the user to fix or fix automatically where obvious and aligned with the intended cluster purpose.
       - **NEVER** open a second, separate commit for auto-format or lint fixes tied to the commit cluster—use amend.

4. **Amend When Needed**
   - Amend (**not** a new commit) the original commit to incorporate relevant hook changes or formatting.
   - Repeat the pre-commit check and amend cycle _until the commit passes all hooks_.

5. **Strict Message Compliance**
   - The commit message **must** follow the mandated single-line, 50-char [type](scope): subject pattern.
   - _Do not allow_ multi-line messages, bodies, or non-conforming types—see [@.cursor/rules/actions/commit.mdc].
   - No periods, no past tense, no ambiguity.

6. **Repeat for Remaining Clusters**
   - Continue the process for each thematic cluster, always seeking user validation before final commit.

---

**This rule has PRIORITY but must always be used with the git commit rule!
Any violation must halt the command and require user rectification.**
