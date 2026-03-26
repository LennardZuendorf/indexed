"""Tests for change_tracker — ChangeTracker and IndexState."""

import subprocess

import pytest

from connectors.files.change_tracker import (
    ChangeTracker,
    IndexState,
)


class TestIndexState:
    def test_roundtrip_json(self):
        state = IndexState(
            last_indexed_commit="abc123",
            file_hashes={"a.txt": "hash1", "b.txt": "hash2"},
            last_indexed_at="2026-01-01T00:00:00",
            indexed_file_count=2,
        )
        json_str = state.to_json()
        restored = IndexState.from_json(json_str)
        assert restored.last_indexed_commit == "abc123"
        assert restored.file_hashes == {"a.txt": "hash1", "b.txt": "hash2"}
        assert restored.indexed_file_count == 2


class TestChangeTrackerNone:
    def test_none_strategy_all_added(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="none")
        changes = tracker.detect_changes([str(f1)], IndexState())
        assert len(changes) == 1
        assert changes[0].status == "added"


class TestChangeTrackerContentHash:
    def test_first_run_all_added(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="content_hash")
        changes = tracker.detect_changes([str(f1)], IndexState())
        assert len(changes) == 1
        assert changes[0].status == "added"

    def test_no_changes(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="content_hash")
        state = tracker.build_state([str(f1)])

        # No changes
        changes = tracker.detect_changes([str(f1)], state)
        assert changes == []

    def test_modified_file(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="content_hash")
        state = tracker.build_state([str(f1)])

        # Modify
        f1.write_text("world")
        changes = tracker.detect_changes([str(f1)], state)
        assert len(changes) == 1
        assert changes[0].status == "modified"

    def test_deleted_file(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="content_hash")
        state = tracker.build_state([str(f1)])

        # Remove file from the list (simulating it's gone)
        changes = tracker.detect_changes([], state)
        assert len(changes) == 1
        assert changes[0].status == "deleted"

    def test_added_file(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="content_hash")
        state = tracker.build_state([str(f1)])

        f2 = tmp_path / "b.txt"
        f2.write_text("new file")
        changes = tracker.detect_changes([str(f1), str(f2)], state)
        assert len(changes) == 1
        assert changes[0].status == "added"
        assert changes[0].path == "b.txt"


class TestChangeTrackerAuto:
    def test_auto_picks_content_hash_without_git(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="auto")
        assert tracker._resolve_strategy() == "content_hash"

    def test_auto_picks_git_with_git_dir(self, tmp_path):
        (tmp_path / ".git").mkdir()
        tracker = ChangeTracker(str(tmp_path), strategy="auto")
        assert tracker._resolve_strategy() == "git"


class TestChangeTrackerGit:
    @staticmethod
    def _git(tmp_path, *args):
        """Run git with signing disabled for test isolation."""
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *args],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a real git repo for testing."""
        subprocess.run(
            ["git", "init"], cwd=str(tmp_path), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"],
            cwd=str(tmp_path),
            capture_output=True,
        )
        f = tmp_path / "initial.txt"
        f.write_text("initial")
        subprocess.run(
            ["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )
        return tmp_path

    def test_first_run_all_added(self, git_repo):
        tracker = ChangeTracker(str(git_repo), strategy="git")
        f = git_repo / "initial.txt"
        changes = tracker.detect_changes([str(f)], IndexState())
        assert len(changes) == 1
        assert changes[0].status == "added"

    def test_same_commit_no_changes(self, git_repo):
        tracker = ChangeTracker(str(git_repo), strategy="git")
        f = git_repo / "initial.txt"
        state = tracker.build_state([str(f)])
        changes = tracker.detect_changes([str(f)], state)
        assert changes == []

    def test_detects_modifications(self, git_repo):
        tracker = ChangeTracker(str(git_repo), strategy="git")
        f = git_repo / "initial.txt"
        state = tracker.build_state([str(f)])

        # Make a new commit with a modification
        f.write_text("modified content")
        subprocess.run(
            ["git", "add", "."], cwd=str(git_repo), capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "modify"],
            cwd=str(git_repo),
            capture_output=True,
            check=True,
        )

        changes = tracker.detect_changes([str(f)], state)
        statuses = {ch.status for ch in changes}
        assert "modified" in statuses
