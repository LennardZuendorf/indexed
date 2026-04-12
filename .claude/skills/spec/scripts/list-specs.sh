#!/usr/bin/env bash
# List all spec files with their type, scope, and area

set -euo pipefail

if [ ! -d ".spec" ]; then
  echo "No .spec/ directory found in current project"
  exit 0
fi

shopt -s nullglob

area_from_name() {
  local name="$1"
  case "$name" in
    product.md|product-*)
      echo "product"
      ;;
    tech.md|tech-*)
      echo "tech"
      ;;
    plan.md|plan-*)
      echo "plan"
      ;;
    design.md|design-*)
      echo "design"
      ;;
    lessons.md)
      echo "lessons"
      ;;
    *)
      echo "unknown"
      ;;
  esac
}

format_spec() {
  local f="$1"
  local display="$2"
  local name type scope area

  name=$(basename "$f")
  type=$(grep -m1 "^type:" "$f" 2>/dev/null | sed 's/type: //' || true)
  scope=$(grep -m1 "^scope:" "$f" 2>/dev/null | sed 's/scope: //' || true)
  area=$(area_from_name "$name")

  echo "- $display [$area] ($type: $scope)"
}

specs=(.spec/*.md)
feature_dirs=(.spec/features/*/)

if [ ${#specs[@]} -eq 0 ] && { [ ! -d ".spec/features" ] || [ ${#feature_dirs[@]} -eq 0 ]; }; then
  echo "No spec files found in .spec/"
  exit 0
fi

for f in "${specs[@]}"; do
  format_spec "$f" "$(basename "$f")"
done

if [ -d ".spec/features" ] && [ ${#feature_dirs[@]} -gt 0 ]; then
  echo ""
  echo "## Features"
  for dir in "${feature_dirs[@]}"; do
    [ -d "$dir" ] || continue
    feature_name=$(basename "$dir")
    echo ""
    echo "### $feature_name"
    feature_specs=("$dir"*.md)
    if [ ${#feature_specs[@]} -eq 0 ]; then
      echo "- (no docs)"
      continue
    fi
    for f in "${feature_specs[@]}"; do
      format_spec "$f" "${f#.spec/}"
    done
  done
fi
