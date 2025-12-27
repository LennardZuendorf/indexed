#!/usr/bin/env python3
"""Helper script to manage branch-specific benchmark baselines.

This script helps manage baseline files for different branches,
storing them in a structured way that can be committed to the repo.
"""

import json
import sys
from pathlib import Path
from typing import Optional


BASELINE_DIR = Path(".benchmarks/baselines")


def get_baseline_path(branch: str) -> Path:
    """Get the path to a branch's baseline file.

    Args:
        branch: Branch name (e.g., 'main', 'feature-branch')

    Returns:
        Path to baseline file
    """
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    # Sanitize branch name for filesystem
    safe_branch = branch.replace("/", "_").replace("\\", "_")
    return BASELINE_DIR / f"{safe_branch}.json"


def save_baseline(branch: str, benchmark_json_path: Path) -> Path:
    """Save a benchmark result as baseline for a branch.

    Args:
        branch: Branch name
        benchmark_json_path: Path to benchmark results JSON

    Returns:
        Path to saved baseline file
    """
    baseline_path = get_baseline_path(branch)

    # Copy the benchmark results to baseline location
    import shutil

    shutil.copy2(benchmark_json_path, baseline_path)

    # Add metadata about when this baseline was created
    with open(baseline_path) as f:
        baseline_data = json.load(f)

    baseline_data["baseline_info"] = {
        "branch": branch,
        "created_at": baseline_data.get("datetime", ""),
    }

    with open(baseline_path, "w") as f:
        json.dump(baseline_data, f, indent=2)

    return baseline_path


def load_baseline(branch: str) -> Optional[dict]:
    """Load baseline data for a branch.

    Args:
        branch: Branch name

    Returns:
        Baseline data dict, or None if not found
    """
    baseline_path = get_baseline_path(branch)
    if not baseline_path.exists():
        return None

    with open(baseline_path) as f:
        return json.load(f)


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 2:
        print("Usage: benchmark_baseline.py <command> [args...]", file=sys.stderr)
        print("Commands:", file=sys.stderr)
        print(
            "  save <branch> <benchmark-json>  - Save benchmark as baseline for branch",
            file=sys.stderr,
        )
        print(
            "  path <branch>                    - Print path to branch baseline file",
            file=sys.stderr,
        )
        print(
            "  exists <branch>                 - Check if baseline exists (exit 0 if yes, 1 if no)",
            file=sys.stderr,
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "save":
        if len(sys.argv) < 4:
            print(
                "Usage: benchmark_baseline.py save <branch> <benchmark-json>",
                file=sys.stderr,
            )
            sys.exit(1)

        branch = sys.argv[2]
        benchmark_json = Path(sys.argv[3])

        if not benchmark_json.exists():
            print(f"Benchmark file not found: {benchmark_json}", file=sys.stderr)
            sys.exit(1)

        baseline_path = save_baseline(branch, benchmark_json)
        print(f"Saved baseline for branch '{branch}' to {baseline_path}")

    elif command == "path":
        if len(sys.argv) < 3:
            print("Usage: benchmark_baseline.py path <branch>", file=sys.stderr)
            sys.exit(1)

        branch = sys.argv[2]
        baseline_path = get_baseline_path(branch)
        print(baseline_path)

    elif command == "exists":
        if len(sys.argv) < 3:
            print("Usage: benchmark_baseline.py exists <branch>", file=sys.stderr)
            sys.exit(1)

        branch = sys.argv[2]
        baseline_path = get_baseline_path(branch)
        sys.exit(0 if baseline_path.exists() else 1)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
