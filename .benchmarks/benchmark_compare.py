#!/usr/bin/env python3
"""Helper script to find latest benchmark and compare.

This script helps GitHub Actions find the latest benchmark file
and set up comparison for pytest-benchmark.
"""

import json
import sys
from pathlib import Path
from typing import Optional


def find_latest_benchmark(benchmark_dir: Path) -> Optional[Path]:
    """Find the latest benchmark JSON file in the directory structure.

    Args:
        benchmark_dir: Path to .benchmarks directory

    Returns:
        Path to latest benchmark file, or None if none found
    """
    if not benchmark_dir.exists():
        return None

    latest_file = None
    latest_num = -1

    # Look in machine-specific subdirectories
    for machine_dir in benchmark_dir.iterdir():
        if not machine_dir.is_dir():
            continue

        for bench_file in machine_dir.glob("*.json"):
            # Extract number from filename (e.g., "0001_..." -> 1)
            try:
                num_str = bench_file.name.split("_")[0]
                num = int(num_str)
                if num > latest_num:
                    latest_num = num
                    latest_file = bench_file
            except (ValueError, IndexError):
                continue

    return latest_file


def compare_json_files(
    baseline_path: Path, current_path: Path, tolerance: float = 20.0
) -> bool:
    """Compare two benchmark JSON files and check for regressions.

    Args:
        baseline_path: Path to baseline benchmark JSON
        current_path: Path to current benchmark JSON
        tolerance: Percentage tolerance for mean time increase (default: 20%)

    Returns:
        True if comparison passed, False if regression detected
    """
    with open(baseline_path) as f:
        baseline = json.load(f)
    with open(current_path) as f:
        current = json.load(f)

    # Check that both benchmarks are from the same node
    baseline_node = baseline.get("machine_info", {}).get("node")
    current_node = current.get("machine_info", {}).get("node")

    if baseline_node and current_node and baseline_node != current_node:
        print(
            "❌ ERROR: Cannot compare benchmarks from different nodes!",
            file=sys.stderr,
        )
        print(
            f"   Baseline node: {baseline_node}",
            file=sys.stderr,
        )
        print(
            f"   Current node:   {current_node}",
            file=sys.stderr,
        )
        print(
            "   Benchmarks must be run on the same machine for accurate comparison.",
            file=sys.stderr,
        )
        return False

    # Create a map of benchmark names to their stats
    baseline_map = {b["name"]: b["stats"] for b in baseline.get("benchmarks", [])}
    current_map = {b["name"]: b["stats"] for b in current.get("benchmarks", [])}

    all_passed = True
    print(
        f"\n{'Benchmark':<40} {'Baseline':<12} {'Current':<12} {'Change':<12} {'Status':<10}"
    )
    print("-" * 90)

    for name in sorted(set(baseline_map.keys()) | set(current_map.keys())):
        if name not in baseline_map:
            print(
                f"{name:<40} {'N/A':<12} {current_map[name]['mean']:.6f}s {'NEW':<12} {'OK':<10}"
            )
            continue
        if name not in current_map:
            print(
                f"{name:<40} {baseline_map[name]['mean']:.6f}s {'N/A':<12} {'MISSING':<12} {'FAIL':<10}"
            )
            all_passed = False
            continue

        baseline_mean = baseline_map[name]["mean"]
        current_mean = current_map[name]["mean"]
        change_pct = ((current_mean - baseline_mean) / baseline_mean) * 100

        # Check if regression exceeds tolerance
        if change_pct > tolerance:
            status = "❌ FAIL"
            all_passed = False
        else:
            status = "✅ PASS"

        change_str = f"{change_pct:+.1f}%"
        print(
            f"{name:<40} {baseline_mean:.6f}s {current_mean:.6f}s {change_str:<12} {status:<10}"
        )

    return all_passed


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 2:
        print("Usage: benchmark_compare.py <command> [args...]", file=sys.stderr)
        print("Commands:", file=sys.stderr)
        print(
            "  find-latest <benchmark-dir>  - Print path to latest benchmark",
            file=sys.stderr,
        )
        print(
            "  compare-id <benchmark-dir>    - Print pytest-benchmark compare ID",
            file=sys.stderr,
        )
        print(
            "  compare-json <baseline> <current> [--tolerance=<percent>]  - Compare two JSON files",
            file=sys.stderr,
        )
        sys.exit(1)

    command = sys.argv[1]
    benchmark_dir = Path(".benchmarks")

    if len(sys.argv) > 2:
        benchmark_dir = Path(sys.argv[2])

    if command == "find-latest":
        latest = find_latest_benchmark(benchmark_dir)
        if latest:
            print(latest)
        else:
            print("No benchmark files found", file=sys.stderr)
            sys.exit(1)

    elif command == "compare-id":
        latest = find_latest_benchmark(benchmark_dir)
        if latest:
            # Extract the ID from filename (e.g., "0001_..." -> "0001")
            bench_id = latest.name.split("_")[0]
            print(bench_id)
        else:
            print("No benchmark files found", file=sys.stderr)
            sys.exit(1)

    elif command == "compare-json":
        if len(sys.argv) < 4:
            print(
                "Usage: benchmark_compare.py compare-json <baseline> <current> [--tolerance=<percent>]",
                file=sys.stderr,
            )
            sys.exit(1)

        baseline_path = Path(sys.argv[2])
        current_path = Path(sys.argv[3])
        tolerance = 20.0

        # Parse tolerance if provided
        for arg in sys.argv[4:]:
            if arg.startswith("--tolerance="):
                tolerance = float(arg.split("=")[1])

        if not baseline_path.exists():
            print(f"Baseline file not found: {baseline_path}", file=sys.stderr)
            sys.exit(1)
        if not current_path.exists():
            print(f"Current file not found: {current_path}", file=sys.stderr)
            sys.exit(1)

        passed = compare_json_files(baseline_path, current_path, tolerance)
        sys.exit(0 if passed else 1)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
