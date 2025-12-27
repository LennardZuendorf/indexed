#!/usr/bin/env python3
"""Helper script to manage branch-specific benchmark baselines.

This script helps manage baseline files for different branches and nodes,
storing them in a structured way that can be committed to the repo.
"""

import json
import sys
from pathlib import Path
from typing import Optional


BASELINE_DIR = Path(".benchmarks/baselines")


def sanitize_name(name: str) -> str:
    """Sanitize a name for use in filesystem paths.

    Args:
        name: Name to sanitize (branch or node name)

    Returns:
        Sanitized name safe for filesystem
    """
    # Replace problematic characters with underscores
    return name.replace("/", "_").replace("\\", "_").replace(" ", "_").replace(".", "_")


def get_baseline_path(branch: str, node: Optional[str] = None) -> Path:
    """Get the path to a branch's baseline file.

    Args:
        branch: Branch name (e.g., 'main', 'feature-branch')
        node: Optional node name. If provided, creates node-specific baseline.
              If None, returns path without node (for backward compatibility)

    Returns:
        Path to baseline file
    """
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    # Sanitize branch name for filesystem
    safe_branch = sanitize_name(branch)

    if node:
        safe_node = sanitize_name(node)
        return BASELINE_DIR / f"{safe_branch}_{safe_node}.json"
    else:
        # Legacy path without node (for backward compatibility)
        return BASELINE_DIR / f"{safe_branch}.json"


def save_baseline(
    branch: str, benchmark_json_path: Path, node: Optional[str] = None
) -> Path:
    """Save a benchmark result as baseline for a branch and optionally a specific node.

    Args:
        branch: Branch name
        benchmark_json_path: Path to benchmark results JSON
        node: Optional node name. If None, extracts from benchmark JSON.

    Returns:
        Path to saved baseline file
    """
    # Load benchmark data to extract node if not provided
    with open(benchmark_json_path) as f:
        benchmark_data = json.load(f)

    # Extract node from benchmark data if not provided
    if node is None:
        node = benchmark_data.get("machine_info", {}).get("node")

    # Get the appropriate baseline path
    baseline_path = get_baseline_path(branch, node)

    # Add metadata about when this baseline was created
    benchmark_data["baseline_info"] = {
        "branch": branch,
        "node": node,
        "created_at": benchmark_data.get("datetime", ""),
    }

    # Write the benchmark data with baseline info to baseline location
    with open(baseline_path, "w") as f:
        json.dump(benchmark_data, f, indent=2)

    return baseline_path


def load_baseline(branch: str, node: Optional[str] = None) -> Optional[dict]:
    """Load baseline data for a branch and optionally a specific node.

    Args:
        branch: Branch name
        node: Optional node name. If provided, loads node-specific baseline.
              If None, tries to find any baseline for the branch (for backward compatibility)

    Returns:
        Baseline data dict, or None if not found
    """
    baseline_path = get_baseline_path(branch, node)
    if baseline_path.exists():
        with open(baseline_path) as f:
            return json.load(f)

    # If node-specific baseline not found and node was provided, return None
    if node:
        return None

    # For backward compatibility: if no node specified, try to find any baseline
    # This allows finding node-specific baselines when node is None
    safe_branch = sanitize_name(branch)
    pattern = f"{safe_branch}_*.json"
    matches = list(BASELINE_DIR.glob(pattern))

    if matches:
        # Return the first match (could be improved to return most recent)
        with open(matches[0]) as f:
            return json.load(f)

    return None


def find_baseline_for_node(branch: str, node: str) -> Optional[Path]:
    """Find the baseline path for a specific branch and node.

    Args:
        branch: Branch name
        node: Node name

    Returns:
        Path to baseline file, or None if not found
    """
    baseline_path = get_baseline_path(branch, node)
    return baseline_path if baseline_path.exists() else None


def list_baselines_for_branch(branch: str) -> list[Path]:
    """List all baseline files for a branch (across all nodes).

    Args:
        branch: Branch name

    Returns:
        List of paths to baseline files for this branch
    """
    safe_branch = sanitize_name(branch)
    # Match both node-specific and legacy baselines
    pattern1 = f"{safe_branch}_*.json"
    pattern2 = f"{safe_branch}.json"

    baselines = list(BASELINE_DIR.glob(pattern1))
    legacy_path = BASELINE_DIR / pattern2
    if legacy_path.exists():
        baselines.append(legacy_path)

    return sorted(baselines)


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 2:
        print("Usage: benchmark_baseline.py <command> [args...]", file=sys.stderr)
        print("Commands:", file=sys.stderr)
        print(
            "  save <branch> <benchmark-json> [--node=<node>]  - Save benchmark as baseline",
            file=sys.stderr,
        )
        print(
            "  path <branch> [--node=<node>]                    - Print path to baseline file",
            file=sys.stderr,
        )
        print(
            "  path-for-node <branch> <node>                    - Print path for specific node",
            file=sys.stderr,
        )
        print(
            "  exists <branch> [--node=<node>]                 - Check if baseline exists",
            file=sys.stderr,
        )
        print(
            "  list <branch>                                    - List all baselines for branch",
            file=sys.stderr,
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "save":
        if len(sys.argv) < 4:
            print(
                "Usage: benchmark_baseline.py save <branch> <benchmark-json> [--node=<node>]",
                file=sys.stderr,
            )
            sys.exit(1)

        branch = sys.argv[2]
        benchmark_json = Path(sys.argv[3])
        node = None

        # Parse optional --node argument
        for arg in sys.argv[4:]:
            if arg.startswith("--node="):
                node = arg.split("=", 1)[1]

        if not benchmark_json.exists():
            print(f"Benchmark file not found: {benchmark_json}", file=sys.stderr)
            sys.exit(1)

        baseline_path = save_baseline(branch, benchmark_json, node)
        node_info = f" (node: {node})" if node else ""
        print(f"Saved baseline for branch '{branch}'{node_info} to {baseline_path}")

    elif command == "path":
        if len(sys.argv) < 3:
            print(
                "Usage: benchmark_baseline.py path <branch> [--node=<node>]",
                file=sys.stderr,
            )
            sys.exit(1)

        branch = sys.argv[2]
        node = None

        # Parse optional --node argument
        for arg in sys.argv[3:]:
            if arg.startswith("--node="):
                node = arg.split("=", 1)[1]

        baseline_path = get_baseline_path(branch, node)
        print(baseline_path)

    elif command == "path-for-node":
        if len(sys.argv) < 4:
            print(
                "Usage: benchmark_baseline.py path-for-node <branch> <node>",
                file=sys.stderr,
            )
            sys.exit(1)

        branch = sys.argv[2]
        node = sys.argv[3]
        baseline_path = get_baseline_path(branch, node)
        print(baseline_path)

    elif command == "exists":
        if len(sys.argv) < 3:
            print(
                "Usage: benchmark_baseline.py exists <branch> [--node=<node>]",
                file=sys.stderr,
            )
            sys.exit(1)

        branch = sys.argv[2]
        node = None

        # Parse optional --node argument
        for arg in sys.argv[3:]:
            if arg.startswith("--node="):
                node = arg.split("=", 1)[1]

        baseline_path = get_baseline_path(branch, node)
        sys.exit(0 if baseline_path.exists() else 1)

    elif command == "list":
        if len(sys.argv) < 3:
            print("Usage: benchmark_baseline.py list <branch>", file=sys.stderr)
            sys.exit(1)

        branch = sys.argv[2]
        baselines = list_baselines_for_branch(branch)

        if baselines:
            print(f"Found {len(baselines)} baseline(s) for branch '{branch}':")
            for baseline_path in baselines:
                # Try to extract node info from filename or file content
                node_info = ""
                if baseline_path.exists():
                    try:
                        with open(baseline_path) as f:
                            data = json.load(f)
                            node = data.get("baseline_info", {}).get(
                                "node"
                            ) or data.get("machine_info", {}).get("node")
                            if node:
                                node_info = f" (node: {node})"
                    except (json.JSONDecodeError, KeyError):
                        pass
                print(f"  - {baseline_path}{node_info}")
        else:
            print(f"No baselines found for branch '{branch}'")
            sys.exit(1)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
