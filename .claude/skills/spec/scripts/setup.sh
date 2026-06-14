#!/bin/bash
# Initialize a .spec/ directory in the current project
# Copies templates as starting points for product, tech, design, and plan entrypoints

set -e

SPEC_DIR=".spec"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE_DIR="$SKILL_DIR/reference/templates"

green() { echo -e "\033[32m  $1\033[0m"; }
yellow() { echo -e "\033[33m  $1\033[0m"; }
red() { echo -e "\033[31m  $1\033[0m"; }

echo ""
echo "Setting up $SPEC_DIR/ ..."
echo ""

# Check if .spec/ already exists
if [[ -d "$SPEC_DIR" ]]; then
  existing=$(ls "$SPEC_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$existing" -gt 0 ]]; then
    yellow "WARN: $SPEC_DIR/ already exists with $existing file(s)."
    echo ""
    echo "  Existing files:"
    for f in "$SPEC_DIR"/*.md; do
      echo "    - $(basename "$f")"
    done
    echo ""
    yellow "Only missing entrypoints will be created. Existing files will NOT be overwritten."
    echo ""
  fi
else
  mkdir -p "$SPEC_DIR"
  green "Created $SPEC_DIR/"
fi

# Check template directory exists
if [[ ! -d "$TEMPLATE_DIR" ]]; then
  red "ERROR: Template directory not found at $TEMPLATE_DIR"
  red "Make sure the spec skill has its reference/templates directory."
  exit 1
fi

# Copy entrypoint templates (only if they don't exist)
# Use a non-postfix increment to play nice with set -e
copied=0

for entrypoint in product.md tech.md design.md plan.md; do
  if [[ -f "$SPEC_DIR/$entrypoint" ]]; then
    yellow "SKIP: $entrypoint already exists"
  else
    if [[ -f "$TEMPLATE_DIR/$entrypoint" ]]; then
      cp "$TEMPLATE_DIR/$entrypoint" "$SPEC_DIR/$entrypoint"
      green "Created $SPEC_DIR/$entrypoint (from template)"
      copied=$((copied + 1))
    else
      red "ERROR: Template not found: $TEMPLATE_DIR/$entrypoint"
    fi
  fi
done

# Create lessons.md if missing (no template — starts empty)
if [[ -f "$SPEC_DIR/lessons.md" ]]; then
  yellow "SKIP: lessons.md already exists"
else
  cat > "$SPEC_DIR/lessons.md" << 'LESSONS_EOF'
# Lessons

Mistakes made and rules to prevent repeating them. Review at the start of every session.
Tags make entries retrievable — scan for tags matching the work in hand.

<!-- Format for each lesson:
### [Short description]
**Pattern:** What went wrong and why
**Rule:** The concrete rule that prevents this
**Tags:** comma, separated, keywords
**Date:** YYYY-MM-DD
-->
LESSONS_EOF
  green "Created $SPEC_DIR/lessons.md"
  copied=$((copied + 1))
fi

echo ""

# .gitignore reminder
if [[ -d ".git" ]]; then
  if [[ -f ".gitignore" ]]; then
    if ! grep -q "^\.spec/" ".gitignore" 2>/dev/null; then
      yellow "NOTE: .spec/ is not in .gitignore."
      yellow "If you want to track specs in git (recommended), no action needed."
      yellow "If you want to exclude specs, add '.spec/' to .gitignore."
    fi
  fi
fi

echo "========================"
echo ""
if [[ $copied -gt 0 ]]; then
  green "Setup complete. $copied entrypoint(s) created."
else
  yellow "No new files created (all entrypoints already exist)."
fi
echo ""
echo "  Spec writing order:"
echo "    1. product.md           — Mini PRD (story / requirements / principles). Stay HIGH-LEVEL."
echo "    2. tech.md              — Architecture summary (stack / philosophy / basic impl). Stay HIGH-LEVEL."
echo "    3. design.md            — Shared UX/design language. Stay HIGH-LEVEL."
echo "    4. features/<name>/     — Decompose sub-parts into features. Each has product.md + tech.md."
echo "    5. plan.md              — Feature Sequence with binary gates (current-only; no backlog)."
echo "    *  product-{topic}.md   — Cross-cutting product branch (design system, conventions). Rare."
echo "    *  tech-{topic}.md      — Cross-cutting tech branch (infrastructure, observability). Rare."
echo "    *  lessons.md           — Updated only during COMPOUND. Read at session start."
echo ""
echo "  Templates:"
echo "    Root entrypoints:        $TEMPLATE_DIR/{product,tech,design,plan}.md"
echo "    Feature specs:           $TEMPLATE_DIR/feature-{product,tech}.md plus optional design.md"
echo "    Cross-cutting branches:  derive from root templates and rename product-/tech-/plan-<topic>.md"
echo ""
echo "  Validate anytime: bash .agents/skills/spec/scripts/validate.sh"
echo ""
