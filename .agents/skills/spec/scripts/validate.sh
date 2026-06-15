#!/usr/bin/env bash
# Validate .spec/ documents for consistency
# Checks: frontmatter, cross-references, naming conventions, orphaned files,
#         feature-folder structure, design tokens (SF3), optional design lint (SF4)

set -euo pipefail

SPEC_DIR=".spec"
ERRORS=0
WARNINGS=0

TOKEN_GROUPS=(colors typography rounded spacing components)

red() { echo -e "\033[31m  ERROR: $1\033[0m"; ((ERRORS++)) || true; }
yellow() { echo -e "\033[33m  WARN:  $1\033[0m"; ((WARNINGS++)) || true; }
green() { echo -e "\033[32m  OK:    $1\033[0m"; }

# SF3 — warn on empty design token groups in frontmatter
check_design_tokens() {
  local file="$1"
  local label="$2"

  [[ -f "$file" ]] || return 0
  head -1 "$file" | grep -q '^---$' || return 0

  while IFS= read -r group; do
    [[ -n "$group" ]] && yellow "$label: empty token group '$group'"
  done < <(awk -v groups="${TOKEN_GROUPS[*]}" '
    BEGIN {
      split(groups, garr, " ")
      for (i in garr) tg[garr[i]] = 1
    }
    function flush_pending() {
      if (pending != "" && !has_child && (pending in tg)) print pending
      pending = ""
      has_child = 0
    }
    function is_token_key(line,    key, rest) {
      if (line !~ /^[a-z]+:/) return 0
      split(line, parts, ":")
      key = parts[1]
      rest = substr(line, length(key) + 2)
      if (!(key in tg)) return 0
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", rest)
      return (rest == "")
    }
    /^---$/ {
      if (++delim == 2) { flush_pending(); exit }
      next
    }
    delim != 1 { next }
    /^[^[:space:]#]/ {
      if (is_token_key($0)) {
        flush_pending()
        split($0, parts, ":")
        pending = parts[1]
        has_child = 0
      } else if ($0 ~ /^[a-z]+:[[:space:]]+[^[:space:]]/) {
        flush_pending()
      } else {
        flush_pending()
      }
      next
    }
    /^[[:space:]]+/ {
      if (pending != "") has_child = 1
    }
  ' "$file")
}

# SF4 — optional external design.md linter (advisory, graceful-degrade)
lint_design_md() {
  local file="$1"
  local label="$2"

  [[ -f "$file" ]] || return 0
  [[ "${VIBE_DESIGN_LINT:-}" == "1" ]] || return 0

  if ! command -v node >/dev/null 2>&1 || ! command -v npx >/dev/null 2>&1; then
    yellow "$label: design.md lint skipped (node/npx not found)"
    return 0
  fi

  if ! curl -fsS --max-time 3 https://registry.npmjs.org/ >/dev/null 2>&1; then
    yellow "$label: design.md lint skipped (npm registry unreachable)"
    return 0
  fi

  local lint_out lint_rc=0
  lint_out="$(npx --yes @google/design.md lint "$file" 2>&1)" || lint_rc=$?
  if [[ $lint_rc -ne 0 ]]; then
    yellow "$label: design.md lint reported issues (advisory)"
    while IFS= read -r line; do
      [[ -n "$line" ]] && yellow "$label:   $line"
    done <<< "$lint_out"
  fi
}

# SF8 — feature product.md Scope table
check_feature_scope() {
  local file="$1"
  local label="$2"

  [[ -f "$file" ]] || return 0

  if ! grep -q '^## Scope' "$file"; then
    yellow "$label: missing '## Scope' section (add Owns / Does not own table)"
    return 0
  fi

  if ! grep -qi 'owns' "$file"; then
    yellow "$label: Scope section missing 'Owns' column or row"
  fi
  if ! grep -qi 'does not own' "$file"; then
    yellow "$label: Scope section missing 'Does not own' column or row"
  fi
}

# SF9 — feature frontmatter fields
check_feature_frontmatter() {
  local file="$1"
  local label="$2"
  local doc_kind="$3"

  [[ -f "$file" ]] || return 0
  head -1 "$file" | grep -q '^---$' || return 0

  if ! grep -q '^feature:' "$file"; then
    yellow "$label: missing 'feature:' in frontmatter"
  fi
  if ! grep -q '^parent:' "$file"; then
    yellow "$label: missing 'parent:' in frontmatter"
  fi
  if [[ "$doc_kind" == "product" || "$doc_kind" == "tech" ]]; then
    if ! grep -q '^sibling:' "$file"; then
      yellow "$label: missing 'sibling:' in frontmatter"
    fi
  fi
}

# SF10 — Requirement + Scenario blocks (warn-only)
check_requirements_scenarios() {
  local file="$1"
  local label="$2"

  [[ -f "$file" ]] || return 0
  grep -q '^### Requirement:' "$file" || return 0

  local had_issues=false
  while IFS= read -r issue; do
    [[ -n "$issue" ]] && yellow "$label: $issue"
    had_issues=true
  done < <(awk '
    function finish_req() {
      if (req_line != "") {
        if (!has_rfc) print "requirement missing RFC-2119 keyword (SHALL|MUST|SHOULD|MAY) -> " req_line
        if (scenarios == 0) print "requirement has zero #### Scenario: blocks -> " req_line
      }
    }
    function note_rfc(line) {
      if (toupper(line) ~ /(SHALL|MUST|SHOULD|MAY)/) has_rfc = 1
    }
    /^### Requirement:/ {
      finish_req()
      req_line = $0
      sub(/^### Requirement:[[:space:]]*/, "", req_line)
      has_rfc = (toupper(req_line) ~ /(SHALL|MUST|SHOULD|MAY)/)
      scenarios = 0
      in_req = 1
      next
    }
    /^#### Scenario:/ {
      if (in_req) scenarios++
      next
    }
    /^### / {
      if (in_req) { finish_req(); in_req = 0; req_line = ""; has_rfc = 0; scenarios = 0 }
      next
    }
    /^## / {
      if (in_req) { finish_req(); in_req = 0; req_line = ""; has_rfc = 0; scenarios = 0 }
      next
    }
    in_req { note_rfc($0) }
    END { if (in_req) finish_req() }
  ' "$file")

  if [[ "${had_issues:-false}" == true ]]; then
    yellow "$label: requirement hint — use '### Requirement: Title SHALL ...' with one or more '#### Scenario: ...' blocks"
  fi
}

# SF11 — feature plan structure
check_feature_plan_structure() {
  local file="$1"
  local label="$2"

  [[ -f "$file" ]] || return 0

  # Accept canonical 'feature/n' headings and legacy '{PREFIX}{N}' (back-compat).
  local has_units=false
  if grep -qE '^### ([a-z0-9][a-z0-9-]*/[0-9]+|[A-Z]{1,4}[0-9]+)' "$file"; then
    has_units=true
  fi

  local has_trace=false
  if grep -qi 'requirements trace' "$file"; then
    has_trace=true
  fi

  if ! $has_units; then
    yellow "$label: plan missing '### <feature>/<n>' unit sections (e.g. '### vibe-flow/1 — ...')"
  fi
  if ! $has_trace; then
    yellow "$label: plan missing 'Requirements Trace' section linking R-IDs to units"
  fi
}

# SF11 — root plan should not embed per-unit detail under milestones
check_root_plan_milestones() {
  local file="$1"
  local label="$2"

  [[ -f "$file" ]] || return 0

  awk '
    /^## M[0-9]/ { in_milestone = 1; next }
    /^## / { in_milestone = 0 }
    in_milestone && /^### ([a-z0-9][a-z0-9-]*\/[0-9]+|[A-Z]{1,4}[0-9]+)/ {
      print "milestone section embeds unit heading (move to feature plan) -> " $0
    }
    in_milestone && /^\|[[:space:]]*([a-z0-9][a-z0-9-]*\/[0-9]+|[A-Z]{1,4}[0-9]+)[[:space:]]*\|/ {
      print "milestone section embeds unit table row (move to feature plan) -> " $0
    }
  ' "$file" | while IFS= read -r msg; do
    [[ -n "$msg" ]] && yellow "$label: $msg"
  done
}

# SF12 — duplicate unit IDs and R-ID traceability
check_plan_id_traceability() {
  local product="$1"
  local plan="$2"
  local label="$3"

  [[ -f "$plan" ]] || return 0

  while IFS= read -r dup; do
    [[ -n "$dup" ]] && yellow "$label: duplicate unit heading ID '$dup' in plan"
  done < <(grep -E '^### ([a-z0-9][a-z0-9-]*/[0-9]+|[A-Z]{1,4}[0-9]+)' "$plan" 2>/dev/null \
    | grep -oE '([a-z0-9][a-z0-9-]*/[0-9]+|[A-Z]{1,4}[0-9]+)' \
    | sort | uniq -d)

  [[ -f "$product" ]] || return 0

  local r_id
  while IFS= read -r r_id; do
    [[ -z "$r_id" ]] && continue
    if ! grep -q "$r_id" "$plan"; then
      yellow "$label: $r_id in product.md not cited in plan.md (light traceability check)"
    fi
  done < <(awk '
    function emit_r_ids(line,    s, n, i) {
      s = line
      while (match(s, /\bR[0-9]+\b/)) {
        print substr(s, RSTART, RLENGTH)
        s = substr(s, RSTART + RLENGTH)
      }
    }
    tolower($0) ~ /^## requirements trace/ { in_trace = 1; next }
    /^## / { in_trace = 0 }
    in_trace { emit_r_ids($0); next }
    /^### Requirement:/ {
      if (in_req) emit_r_ids(req_buf)
      in_req = 1
      req_buf = $0
      next
    }
    /^### / {
      if (in_req) { emit_r_ids(req_buf); in_req = 0; req_buf = "" }
      next
    }
    /^## / {
      if (in_req) { emit_r_ids(req_buf); in_req = 0; req_buf = "" }
      next
    }
    in_req { req_buf = req_buf "\n" $0 }
    END { if (in_req) emit_r_ids(req_buf) }
  ' "$product" | sort -u)
}

# I1 — feature plan declares same-feature deps only; cross-feature order is a
# whole-feature gate in the root plan, never a unit-to-unit edge. Warn-only.
check_cross_feature_deps() {
  local plan="$1"
  local feature="$2"
  local label="$3"

  [[ -f "$plan" ]] || return 0

  while IFS= read -r dep; do
    [[ -n "$dep" ]] && yellow "$label: cross-feature unit dependency '$dep' — use a whole-feature gate in the root plan Feature Sequence, not a unit edge"
  done < <(grep -oE '\b[a-z][a-z0-9-]*/[0-9]+\b' "$plan" 2>/dev/null \
    | grep -vE "^${feature}/[0-9]+$" \
    | sort -u)
}

echo "Validating $SPEC_DIR/..."
echo ""

if [[ ! -d "$SPEC_DIR" ]]; then
  red "No .spec/ directory found. Run setup first: bash .agents/skills/spec/scripts/setup.sh"
  exit 1
fi

shopt -s nullglob
specs=("$SPEC_DIR"/*.md)

if [[ ${#specs[@]} -eq 0 ]]; then
  red "No spec files found in $SPEC_DIR/"
  exit 1
fi

# ─── Validate root layer files ──────────────────────────────────────────────

for f in "${specs[@]}"; do
  name=$(basename "$f")
  echo "--- $name ---"

  if [[ "$name" == "lessons.md" ]]; then
    while IFS= read -r untagged; do
      yellow "$name: lesson missing '**Tags:**' -> ${untagged#### }"
    done < <(awk '
      /^### / {
        if (have_entry && !have_tags) print prev_title
        have_entry = 1; have_tags = 0; prev_title = $0; next
      }
      /^\*\*Tags:\*\*/ { if (have_entry) have_tags = 1 }
      END { if (have_entry && !have_tags) print prev_title }
    ' "$f")
    green "$name: checked (lessons file, no frontmatter required)"
    echo ""
    continue
  fi

  if ! head -1 "$f" | grep -q '^---$'; then
    red "$name: missing YAML frontmatter"
    continue
  fi

  if ! grep -q '^type:' "$f"; then
    red "$name: missing 'type:' in frontmatter"
  fi
  if ! grep -q '^updated:' "$f"; then
    red "$name: missing 'updated:' in frontmatter"
  fi

  if grep -q '^type: entrypoint' "$f"; then
    if ! grep -q '^children:' "$f"; then
      if [[ "$name" == "plan.md" ]]; then
        yellow "$name: entrypoint has no 'children:' list (add sub-plans if needed)"
      else
        red "$name: entrypoint missing 'children:' list"
      fi
    fi
  fi

  if grep -q '^type: branch' "$f"; then
    if ! grep -q '^parent:' "$f"; then
      red "$name: branch doc missing 'parent:' field"
    fi
    if ! grep -q '^scope:' "$f"; then
      yellow "$name: branch doc missing 'scope:' field"
    fi
    if ! grep -q '^covers:' "$f"; then
      yellow "$name: branch doc missing 'covers:' field"
    fi
  fi

  if [[ "$name" != "product.md" && "$name" != "tech.md" && "$name" != "design.md" && "$name" != "plan.md" && "$name" != "lessons.md" ]]; then
    if [[ "$name" != product-* && "$name" != tech-* && "$name" != plan-* ]]; then
      red "$name: must start with 'product-', 'tech-', or 'plan-' (e.g., product-design.md, tech-api.md, plan-editor.md)"
    fi

    if [[ "$name" =~ ^(product|tech|plan)-(.+)\.md$ ]]; then
      topic="${BASH_REMATCH[2]}"
      if [[ ! "$topic" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
        red "$name: topic must be lowercase with hyphens only, no leading/trailing hyphens (found: '$topic')"
      fi
    fi
  fi

  if [[ "$name" == "design.md" ]]; then
    check_design_tokens "$f" "$name"
    lint_design_md "$f" "$name"
  fi

  if [[ "$name" == "plan.md" ]]; then
    check_root_plan_milestones "$f" "$name"
  fi

  check_requirements_scenarios "$f" "$name"

  while IFS= read -r link; do
    target=$(echo "$link" | sed 's/.*(\(.*\))/\1/' | sed 's/#.*//')
    if [[ -n "$target" && "$target" != http* && "$target" != ../ ]]; then
      if [[ ! -f "$SPEC_DIR/$target" && ! -f "$(dirname "$f")/$target" ]]; then
        red "$name: broken link to '$target'"
      fi
    fi
  done < <(grep -oE '\[.*?\]\([^)]+\.md[^)]*\)' "$f" 2>/dev/null || true)

  green "$name: checked"
  echo ""
done

# ─── Validate entrypoint children exist ─────────────────────────────────────

for entrypoint in "$SPEC_DIR"/product.md "$SPEC_DIR"/tech.md "$SPEC_DIR"/design.md "$SPEC_DIR"/plan.md; do
  if [[ -f "$entrypoint" ]]; then
    name=$(basename "$entrypoint")
    in_children=false
    while IFS= read -r line; do
      if [[ "$line" == "children:" ]]; then
        in_children=true
        continue
      fi
      if $in_children; then
        if [[ "$line" =~ ^[[:space:]]*-[[:space:]]+(.*) ]]; then
          child="${BASH_REMATCH[1]}"
          if [[ ! -f "$SPEC_DIR/$child" ]]; then
            red "$name: child '$child' listed in frontmatter but file doesn't exist"
          fi
        else
          in_children=false
        fi
      fi
    done < "$entrypoint"
  fi
done

# ─── Validate feature folders ───────────────────────────────────────────────

if [[ -d "$SPEC_DIR/features" ]]; then
  for feature_dir in "$SPEC_DIR"/features/*/; do
    [[ -d "$feature_dir" ]] || continue
    feature_name=$(basename "$feature_dir")
    echo "--- features/$feature_name/ ---"

    for required in product.md tech.md; do
      f="$feature_dir$required"
      if [[ ! -f "$f" ]]; then
        red "features/$feature_name/: missing required '$required'"
        continue
      fi

      if ! head -1 "$f" | grep -q '^---$'; then
        red "features/$feature_name/$required: missing YAML frontmatter"
        continue
      fi

      if ! grep -q '^type:' "$f"; then
        red "features/$feature_name/$required: missing 'type:' in frontmatter"
      fi
      if ! grep -q '^updated:' "$f"; then
        red "features/$feature_name/$required: missing 'updated:' in frontmatter"
      fi

      expected_type="feature-${required%.md}"
      if ! grep -q "^type: $expected_type" "$f"; then
        yellow "features/$feature_name/$required: expected 'type: $expected_type'"
      fi

      check_feature_frontmatter "$f" "features/$feature_name/$required" "${required%.md}"
      if [[ "$required" == "product.md" ]]; then
        check_feature_scope "$f" "features/$feature_name/product.md"
      fi
      check_requirements_scenarios "$f" "features/$feature_name/$required"

      while IFS= read -r link; do
        target=$(echo "$link" | sed 's/.*(\(.*\))/\1/' | sed 's/#.*//')
        if [[ -n "$target" && "$target" != http* ]]; then
          if [[ "$target" == "design.md" || "$target" == "plan.md" ]] \
            && [[ ! -f "$feature_dir$target" ]]; then
            continue
          fi
          resolved=$(cd "$feature_dir" 2>/dev/null && [[ -f "$target" ]] && echo "ok" || echo "")
          if [[ -z "$resolved" ]]; then
            red "features/$feature_name/$required: broken link to '$target'"
          fi
        fi
      done < <(grep -oE '\[.*?\]\([^)]+\.md[^)]*\)' "$f" 2>/dev/null || true)
    done

    for optional in design.md plan.md; do
      f="$feature_dir$optional"
      [[ -f "$f" ]] || continue

      if ! head -1 "$f" | grep -q '^---$'; then
        red "features/$feature_name/$optional: missing YAML frontmatter"
        continue
      fi
      if ! grep -q '^type:' "$f"; then
        red "features/$feature_name/$optional: missing 'type:' in frontmatter"
      fi
      if ! grep -q '^updated:' "$f"; then
        red "features/$feature_name/$optional: missing 'updated:' in frontmatter"
      fi

      expected_type="feature-${optional%.md}"
      if ! grep -q "^type: $expected_type" "$f"; then
        yellow "features/$feature_name/$optional: expected 'type: $expected_type'"
      fi

      check_feature_frontmatter "$f" "features/$feature_name/$optional" "${optional%.md}"

      if [[ "$optional" == "design.md" ]]; then
        check_design_tokens "$f" "features/$feature_name/design.md"
        lint_design_md "$f" "features/$feature_name/design.md"
      fi

      if [[ "$optional" == "plan.md" ]]; then
        check_feature_plan_structure "$f" "features/$feature_name/plan.md"
        check_plan_id_traceability "$feature_dir/product.md" "$f" "features/$feature_name"
        check_cross_feature_deps "$f" "$feature_name" "features/$feature_name/plan.md"
      fi

      check_requirements_scenarios "$f" "features/$feature_name/$optional"
    done

    green "features/$feature_name/: checked"
    echo ""
  done
fi

# ─── Validate CLAUDE.md links ──────────────────────────────────────────────

if [[ -f "CLAUDE.md" ]]; then
  echo "--- CLAUDE.md ---"
  while IFS= read -r link; do
    target=$(echo "$link" | sed 's/.*(\(.*\))/\1/' | sed 's/#.*//')
    if [[ "$target" == .spec/* && ! -f "$target" ]]; then
      red "CLAUDE.md: broken link to '$target'"
    fi
  done < <(grep -oE '\[.*?\]\([^)]+\.md[^)]*\)' "CLAUDE.md" 2>/dev/null || true)
  green "CLAUDE.md: checked"
  echo ""
fi

echo "========================"
echo "Errors:   $ERRORS"
echo "Warnings: $WARNINGS"

if [[ $ERRORS -gt 0 ]]; then
  exit 1
fi
exit 0
