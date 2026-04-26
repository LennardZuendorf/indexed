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

    def test_detects_uncommitted_modifications(self, git_repo):
        """Uncommitted (unstaged) working-tree changes must be detected via git status."""
        tracker = ChangeTracker(str(git_repo), strategy="git")
        f = git_repo / "initial.txt"
        state = tracker.build_state([str(f)])

        # Modify the file WITHOUT committing
        f.write_text("dirty uncommitted change")

        changes = tracker.detect_changes([str(f)], state)
        statuses = {ch.status for ch in changes}
        assert "modified" in statuses, "Uncommitted change was not detected"

    def test_detects_staged_modifications(self, git_repo):
        """Staged (but not committed) changes must be detected via git status."""
        tracker = ChangeTracker(str(git_repo), strategy="git")
        f = git_repo / "initial.txt"
        state = tracker.build_state([str(f)])

        f.write_text("staged change")
        subprocess.run(
            ["git", "add", str(f)], cwd=str(git_repo), capture_output=True, check=True
        )

        changes = tracker.detect_changes([str(f)], state)
        statuses = {ch.status for ch in changes}
        assert "modified" in statuses, "Staged change was not detected"

    def test_subdirectory_base_path(self, tmp_path):
        """ChangeTracker with base_path as a subdirectory must map git paths correctly."""
        # Create a nested repo: tmp_path/repo/subdir/file.txt
        repo = tmp_path / "repo"
        repo.mkdir()
        subdir = repo / "subdir"
        subdir.mkdir()

        for cmd in [
            ["git", "init"],
            ["git", "config", "user.email", "test@test.com"],
            ["git", "config", "user.name", "Test"],
            ["git", "config", "commit.gpgsign", "false"],
        ]:
            subprocess.run(cmd, cwd=str(repo), capture_output=True)

        f = subdir / "file.txt"
        f.write_text("original")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "commit", "-m", "init"],
            cwd=str(repo),
            capture_output=True,
            check=True,
        )

        # Tracker uses the subdirectory as base_path (not the repo root)
        tracker = ChangeTracker(str(subdir), strategy="git")
        state = tracker.build_state([str(f)])

        # Modify the file and commit
        f.write_text("modified")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "commit", "-m", "modify"],
            cwd=str(repo),
            capture_output=True,
            check=True,
        )

        changes = tracker.detect_changes([str(f)], state)
        assert len(changes) == 1, f"Expected 1 change, got {changes}"
        assert changes[0].status == "modified"
        assert changes[0].path == "file.txt"

    def test_gitignored_file_detected_as_deleted(self, git_repo):
        """File previously indexed but now excluded (e.g. .gitignore) must be 'deleted'."""
        tracker = ChangeTracker(str(git_repo), strategy="git")
        f = git_repo / "initial.txt"
        # State includes initial.txt as indexed
        state = tracker.build_state([str(f)])

        # Simulate the file being gitignored: still on disk, not in the current walk
        # Pass an empty file_paths list (as if the walker skipped it)
        changes = tracker.detect_changes([], state)

        deleted = [ch for ch in changes if ch.status == "deleted"]
        assert len(deleted) == 1
        assert deleted[0].path == "initial.txt"


class TestParseDiffNameStatus:
    """Unit tests for _parse_diff_name_status without a real git repo."""

    def test_added_file(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "A\tnew_file.txt\n"
        result = tracker._parse_diff_name_status(output, None, {"new_file.txt"})
        assert result == {"new_file.txt": "added"}

    def test_modified_file(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "M\texisting.txt\n"
        result = tracker._parse_diff_name_status(output, None, {"existing.txt"})
        assert result == {"existing.txt": "modified"}

    def test_deleted_file(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "D\tremoved.txt\n"
        result = tracker._parse_diff_name_status(output, None, set())
        assert result == {"removed.txt": "deleted"}

    def test_renamed_file(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "R100\told_name.txt\tnew_name.txt\n"
        result = tracker._parse_diff_name_status(output, None, {"new_name.txt"})
        assert result["old_name.txt"] == "deleted"
        assert result["new_name.txt"] == "added"

    def test_added_file_not_in_current_rel_ignored(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "A\tnew_file.txt\n"
        result = tracker._parse_diff_name_status(output, None, set())
        assert result == {}

    def test_empty_output(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        result = tracker._parse_diff_name_status("", None, set())
        assert result == {}

    def test_multiple_changes(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "A\ta.txt\nM\tb.txt\nD\tc.txt\n"
        result = tracker._parse_diff_name_status(output, None, {"a.txt", "b.txt"})
        assert result == {"a.txt": "added", "b.txt": "modified", "c.txt": "deleted"}

    def test_with_git_toplevel(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        tracker = ChangeTracker(str(sub), strategy="git")
        output = "M\tsubdir/file.txt\n"
        result = tracker._parse_diff_name_status(output, str(tmp_path), {"file.txt"})
        assert result == {"file.txt": "modified"}

    def test_path_outside_base_ignored(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        tracker = ChangeTracker(str(sub), strategy="git")
        output = "M\tother/file.txt\n"
        result = tracker._parse_diff_name_status(output, str(tmp_path), {"file.txt"})
        assert result == {}


class TestParseStatusPorcelain:
    """Unit tests for _parse_status_porcelain."""

    def test_modified_staged(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "M  file.txt\n"
        result = tracker._parse_status_porcelain(output, None, {"file.txt"})
        assert result == {"file.txt": "modified"}

    def test_modified_unstaged(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = " M file.txt\n"
        result = tracker._parse_status_porcelain(output, None, {"file.txt"})
        assert result == {"file.txt": "modified"}

    def test_untracked_file(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "?? new_file.txt\n"
        result = tracker._parse_status_porcelain(output, None, {"new_file.txt"})
        assert result == {"new_file.txt": "added"}

    def test_deleted_file(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "D  removed.txt\n"
        result = tracker._parse_status_porcelain(output, None, set())
        assert result == {"removed.txt": "deleted"}

    def test_deleted_unstaged(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = " D removed.txt\n"
        result = tracker._parse_status_porcelain(output, None, set())
        assert result == {"removed.txt": "deleted"}

    def test_renamed_file(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "R  old.txt -> new.txt\n"
        result = tracker._parse_status_porcelain(output, None, {"new.txt"})
        assert result["old.txt"] == "deleted"
        assert result["new.txt"] == "added"

    def test_added_staged(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "A  added.txt\n"
        result = tracker._parse_status_porcelain(output, None, {"added.txt"})
        assert result == {"added.txt": "added"}

    def test_short_line_skipped(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        output = "ab\n"
        result = tracker._parse_status_porcelain(output, None, set())
        assert result == {}

    def test_empty_output(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        result = tracker._parse_status_porcelain("", None, set())
        assert result == {}

    def test_path_outside_base_ignored(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        tracker = ChangeTracker(str(sub), strategy="git")
        output = " M other/file.txt\n"
        result = tracker._parse_status_porcelain(output, str(tmp_path), {"file.txt"})
        assert result == {}


class TestChangeTrackerMtime:
    """Tests for the mtime change detection strategy."""

    def test_first_run_all_added(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="mtime")
        changes = tracker.detect_changes([str(f1)], IndexState())
        assert len(changes) == 1
        assert changes[0].status == "added"

    def test_no_changes_when_not_modified(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="mtime")
        state = tracker.build_state([str(f1)])
        changes = tracker.detect_changes([str(f1)], state)
        assert changes == []

    def test_modified_file_detected(self, tmp_path):
        import time

        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="mtime")
        state = tracker.build_state([str(f1)])

        # Ensure mtime changes
        time.sleep(0.05)
        f1.write_text("world")

        changes = tracker.detect_changes([str(f1)], state)
        assert len(changes) == 1
        assert changes[0].status == "modified"

    def test_deleted_file_detected(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="mtime")
        state = tracker.build_state([str(f1)])

        changes = tracker.detect_changes([], state)
        assert len(changes) == 1
        assert changes[0].status == "deleted"

    def test_invalid_last_indexed_at(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="mtime")
        state = IndexState(
            file_hashes={"a.txt": "somehash"},
            last_indexed_at="not-a-valid-date",
        )
        # Should not crash, cutoff becomes None so no modifications detected
        changes = tracker.detect_changes([str(f1)], state)
        assert changes == []


class TestChangeTrackerBuildState:
    """Tests for build_state method."""

    def test_build_state_returns_hashes(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        tracker = ChangeTracker(str(tmp_path), strategy="content_hash")
        state = tracker.build_state([str(f1)])
        assert state.file_hashes is not None
        assert "a.txt" in state.file_hashes
        assert state.indexed_file_count == 1
        assert state.last_indexed_at is not None

    def test_build_state_skips_unreadable(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="content_hash")
        state = tracker.build_state([str(tmp_path / "nonexistent.txt")])
        assert state.file_hashes == {}
        assert state.indexed_file_count == 1

    def test_build_state_multiple_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("aaa")
        f2.write_text("bbb")
        tracker = ChangeTracker(str(tmp_path), strategy="content_hash")
        state = tracker.build_state([str(f1), str(f2)])
        assert len(state.file_hashes) == 2
        assert state.indexed_file_count == 2


class TestGitPathToRel:
    """Tests for _git_path_to_rel."""

    def test_with_toplevel(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        tracker = ChangeTracker(str(sub), strategy="git")
        result = tracker._git_path_to_rel("sub/file.txt", str(tmp_path))
        assert result == "file.txt"

    def test_without_toplevel(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="git")
        result = tracker._git_path_to_rel("file.txt", None)
        assert result == "file.txt"

    def test_outside_base_returns_none(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        tracker = ChangeTracker(str(sub), strategy="git")
        result = tracker._git_path_to_rel("other/file.txt", str(tmp_path))
        assert result is None


class TestChangeTrackerHashOSError:
    """Test hash strategy handles OS errors on read."""

    def test_oserror_on_read_skips_file(self, tmp_path):
        tracker = ChangeTracker(str(tmp_path), strategy="content_hash")
        # Pass a path that doesn't exist
        changes = tracker.detect_changes([str(tmp_path / "missing.txt")], IndexState())
        assert changes == []
