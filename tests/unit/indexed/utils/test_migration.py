"""Comprehensive tests for migration utility module."""

from pathlib import Path
from unittest.mock import Mock, patch
from rich.console import Console

from indexed.utils.migration import (
    _get_legacy_data_path,
    _get_legacy_collections_path,
    _get_legacy_caches_path,
    has_legacy_data,
    get_legacy_collections,
    prompt_migration,
    migrate_legacy_data,
)


class TestLegacyPathFunctions:
    """Test legacy path resolution functions."""

    def test_get_legacy_data_path_returns_cwd_data(self):
        """Should return ./data relative to current working directory."""
        result = _get_legacy_data_path()
        expected = Path.cwd() / "data"
        assert result == expected

    def test_get_legacy_collections_path(self):
        """Should return ./data/collections."""
        result = _get_legacy_collections_path()
        expected = Path.cwd() / "data" / "collections"
        assert result == expected

    def test_get_legacy_caches_path(self):
        """Should return ./data/caches."""
        result = _get_legacy_caches_path()
        expected = Path.cwd() / "data" / "caches"
        assert result == expected


class TestHasLegacyData:
    """Test has_legacy_data detection."""

    def test_returns_false_when_no_data_dir(self, tmp_path):
        """Should return False when data/ directory doesn't exist."""
        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=tmp_path / "nonexistent",
        ):
            assert has_legacy_data() is False

    def test_returns_false_when_data_dir_empty(self, tmp_path):
        """Should return False when data/collections exists but is empty."""
        collections_path = tmp_path / "collections"
        collections_path.mkdir()

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=collections_path,
        ):
            assert has_legacy_data() is False

    def test_returns_false_when_no_manifest_files(self, tmp_path):
        """Should return False when directories exist but have no manifest.json."""
        collections_path = tmp_path / "collections"
        collections_path.mkdir()
        (collections_path / "collection1").mkdir()
        (collections_path / "collection2").mkdir()

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=collections_path,
        ):
            assert has_legacy_data() is False

    def test_returns_true_when_valid_collection_exists(self, tmp_path):
        """Should return True when at least one valid collection with manifest exists."""
        collections_path = tmp_path / "collections"
        collections_path.mkdir()
        collection_dir = collections_path / "my-collection"
        collection_dir.mkdir()
        (collection_dir / "manifest.json").write_text('{"name": "my-collection"}')

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=collections_path,
        ):
            assert has_legacy_data() is True

    def test_ignores_files_in_collections_dir(self, tmp_path):
        """Should ignore non-directory items in collections/."""
        collections_path = tmp_path / "collections"
        collections_path.mkdir()
        (collections_path / "random_file.txt").write_text("not a collection")

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=collections_path,
        ):
            assert has_legacy_data() is False


class TestGetLegacyCollections:
    """Test get_legacy_collections listing."""

    def test_returns_empty_list_when_no_collections_dir(self, tmp_path):
        """Should return empty list when collections directory doesn't exist."""
        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=tmp_path / "nonexistent",
        ):
            result = get_legacy_collections()
            assert result == []

    def test_returns_empty_list_when_no_valid_collections(self, tmp_path):
        """Should return empty list when no directories have manifest.json."""
        collections_path = tmp_path / "collections"
        collections_path.mkdir()
        (collections_path / "dir1").mkdir()
        (collections_path / "dir2").mkdir()

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=collections_path,
        ):
            result = get_legacy_collections()
            assert result == []

    def test_returns_collection_names_with_manifest(self, tmp_path):
        """Should return names of directories containing manifest.json."""
        collections_path = tmp_path / "collections"
        collections_path.mkdir()

        # Valid collections
        for name in ["collection-a", "collection-b", "collection-c"]:
            coll_dir = collections_path / name
            coll_dir.mkdir()
            (coll_dir / "manifest.json").write_text("{}")

        # Invalid collection (no manifest)
        invalid = collections_path / "no-manifest"
        invalid.mkdir()

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=collections_path,
        ):
            result = get_legacy_collections()
            assert result == ["collection-a", "collection-b", "collection-c"]

    def test_returns_sorted_collection_names(self, tmp_path):
        """Should return collection names in sorted order."""
        collections_path = tmp_path / "collections"
        collections_path.mkdir()

        for name in ["zebra", "alpha", "beta"]:
            coll_dir = collections_path / name
            coll_dir.mkdir()
            (coll_dir / "manifest.json").write_text("{}")

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=collections_path,
        ):
            result = get_legacy_collections()
            assert result == ["alpha", "beta", "zebra"]

    def test_ignores_files_only_directories(self, tmp_path):
        """Should only include directories, not files."""
        collections_path = tmp_path / "collections"
        collections_path.mkdir()

        # Valid collection
        valid = collections_path / "valid-coll"
        valid.mkdir()
        (valid / "manifest.json").write_text("{}")

        # File that looks like it has manifest
        (collections_path / "file-coll").write_text("not a dir")

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=collections_path,
        ):
            result = get_legacy_collections()
            assert result == ["valid-coll"]


class TestPromptMigration:
    """Test prompt_migration interactive prompt."""

    @patch("indexed.utils.migration.Confirm.ask")
    @patch("indexed.utils.migration.has_legacy_data", return_value=True)
    @patch(
        "indexed.utils.migration.get_legacy_collections",
        return_value=["coll-a", "coll-b"],
    )
    def test_shows_collections_to_user(
        self, mock_get_collections, mock_has_legacy, mock_confirm, tmp_path
    ):
        """Should display list of collections to user."""
        mock_console = Mock(spec=Console)
        target_root = tmp_path / "target"
        mock_confirm.return_value = False

        prompt_migration(mock_console, target_root)

        # Should have printed to console
        assert mock_console.print.called

    @patch("indexed.utils.migration.Confirm.ask")
    @patch("indexed.utils.migration.migrate_legacy_data", return_value=True)
    @patch("indexed.utils.migration.has_legacy_data", return_value=True)
    @patch("indexed.utils.migration.get_legacy_collections", return_value=["coll-a"])
    def test_returns_true_when_user_confirms(
        self, mock_get_collections, mock_has_legacy, mock_migrate, mock_confirm
    ):
        """Should return True when user confirms migration."""
        mock_console = Mock(spec=Console)
        target_root = Path("/tmp/target")
        mock_confirm.return_value = True

        result = prompt_migration(mock_console, target_root)

        assert result is True

    @patch("indexed.utils.migration.Confirm.ask")
    @patch("indexed.utils.migration.has_legacy_data", return_value=True)
    @patch("indexed.utils.migration.get_legacy_collections", return_value=["coll-a"])
    def test_returns_false_when_user_declines(
        self, mock_get_collections, mock_has_legacy, mock_confirm
    ):
        """Should return False when user declines migration."""
        mock_console = Mock(spec=Console)
        target_root = Path("/tmp/target")
        mock_confirm.return_value = False

        result = prompt_migration(mock_console, target_root)

        assert result is False

    @patch("indexed.utils.migration.has_legacy_data", return_value=False)
    def test_handles_empty_collection_list(self, mock_has_legacy):
        """Should handle empty collection list gracefully."""
        mock_console = Mock(spec=Console)
        target_root = Path("/tmp/target")

        result = prompt_migration(mock_console, target_root)

        assert result is True  # Returns True when no legacy data

    @patch("indexed.utils.migration.has_legacy_data", return_value=True)
    def test_target_already_has_data_skips_prompt(self, mock_has_legacy, tmp_path):
        """Should inform user and return True when target already has collections."""
        mock_console = Mock(spec=Console)
        target_root = tmp_path / "target"
        target_collections = target_root / "data" / "collections"
        target_collections.mkdir(parents=True)
        # Put something in the target so any() returns True
        (target_collections / "existing-coll").mkdir()

        result = prompt_migration(mock_console, target_root)

        assert result is True
        # Should have printed a note about existing data (no Confirm.ask called)
        printed = " ".join(str(c) for c in mock_console.print.call_args_list)
        assert "already has collections" in printed


class TestMigrateLegacyData:
    """Test migrate_legacy_data function."""

    def test_copies_collections_to_new_location(self, tmp_path):
        """Should copy collections from legacy to new storage location."""
        # Setup legacy structure
        legacy_root = tmp_path / "legacy"
        legacy_collections = legacy_root / "data" / "collections"
        legacy_collections.mkdir(parents=True)

        coll_dir = legacy_collections / "my-coll"
        coll_dir.mkdir()
        (coll_dir / "manifest.json").write_text('{"name": "my-coll"}')
        (coll_dir / "data.txt").write_text("collection data")

        # New location
        new_root = tmp_path / "new"
        new_collections = new_root / "data" / "collections"

        mock_console = Mock(spec=Console)
        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            with patch(
                "indexed.utils.migration.get_legacy_collections",
                return_value=["my-coll"],
            ):
                migrate_legacy_data(new_root, mock_console)

        # Check files were copied
        assert (new_collections / "my-coll" / "manifest.json").exists()
        assert (new_collections / "my-coll" / "data.txt").exists()

    def test_creates_target_directory_if_missing(self, tmp_path):
        """Should create target directory if it doesn't exist."""
        legacy_root = tmp_path / "legacy"
        legacy_collections = legacy_root / "data" / "collections"
        legacy_collections.mkdir(parents=True)

        coll_dir = legacy_collections / "coll1"
        coll_dir.mkdir()
        (coll_dir / "manifest.json").write_text("{}")

        new_root = tmp_path / "new"

        mock_console = Mock(spec=Console)
        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            with patch(
                "indexed.utils.migration.get_legacy_collections", return_value=["coll1"]
            ):
                migrate_legacy_data(new_root, mock_console)

        new_collections = new_root / "data" / "collections"
        assert new_collections.exists()
        assert (new_collections / "coll1").exists()

    def test_preserves_directory_structure(self, tmp_path):
        """Should preserve nested directory structure within collections."""
        legacy_collections = tmp_path / "legacy" / "collections"
        legacy_collections.mkdir(parents=True)

        coll_dir = legacy_collections / "nested-coll"
        coll_dir.mkdir()
        (coll_dir / "manifest.json").write_text("{}")

        nested = coll_dir / "subdir" / "deep"
        nested.mkdir(parents=True)
        (nested / "file.txt").write_text("nested data")

        new_root = tmp_path / "new"
        mock_console = Mock(spec=Console)

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            with patch(
                "indexed.utils.migration.get_legacy_collections",
                return_value=["nested-coll"],
            ):
                migrate_legacy_data(new_root, mock_console)

        new_collections = new_root / "data" / "collections"
        assert (
            new_collections / "nested-coll" / "subdir" / "deep" / "file.txt"
        ).exists()

    def test_skips_collections_without_manifest(self, tmp_path):
        """Should only migrate collections with valid manifest.json."""
        legacy_collections = tmp_path / "legacy" / "collections"
        legacy_collections.mkdir(parents=True)

        # Valid collection
        valid = legacy_collections / "valid"
        valid.mkdir()
        (valid / "manifest.json").write_text("{}")

        # Invalid (no manifest)
        invalid = legacy_collections / "invalid"
        invalid.mkdir()
        (invalid / "data.txt").write_text("data")

        new_root = tmp_path / "new"
        mock_console = Mock(spec=Console)

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            with patch(
                "indexed.utils.migration.get_legacy_collections", return_value=["valid"]
            ):
                migrate_legacy_data(new_root, mock_console)

        new_collections = new_root / "data" / "collections"
        assert (new_collections / "valid").exists()
        assert not (new_collections / "invalid").exists()

    def test_handles_empty_collections_directory(self, tmp_path):
        """Should handle empty collections directory without error."""
        legacy_collections = tmp_path / "legacy" / "collections"
        legacy_collections.mkdir(parents=True)

        new_root = tmp_path / "new"
        mock_console = Mock(spec=Console)

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            with patch(
                "indexed.utils.migration.get_legacy_collections", return_value=[]
            ):
                # Should not raise
                migrate_legacy_data(new_root, mock_console)

    def test_reports_progress_to_console(self, tmp_path):
        """Should report migration progress via Rich console."""
        legacy_collections = tmp_path / "legacy" / "collections"
        legacy_collections.mkdir(parents=True)

        for name in ["coll1", "coll2"]:
            coll = legacy_collections / name
            coll.mkdir()
            (coll / "manifest.json").write_text("{}")

        new_root = tmp_path / "new"
        mock_console = Mock(spec=Console)

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            with patch(
                "indexed.utils.migration.get_legacy_collections",
                return_value=["coll1", "coll2"],
            ):
                migrate_legacy_data(new_root, mock_console)

        # Should have printed progress
        assert mock_console.print.called

    def test_dry_run_returns_true_without_copying(self, tmp_path):
        """dry_run=True should print message and return True without copying files."""
        legacy_collections = tmp_path / "legacy" / "collections"
        legacy_collections.mkdir(parents=True)
        coll_dir = legacy_collections / "coll1"
        coll_dir.mkdir()
        (coll_dir / "manifest.json").write_text("{}")

        new_root = tmp_path / "new"
        mock_console = Mock(spec=Console)

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            with patch(
                "indexed.utils.migration.get_legacy_collections",
                return_value=["coll1"],
            ):
                result = migrate_legacy_data(new_root, mock_console, dry_run=True)

        assert result is True
        # Target collections should NOT have been created
        assert not (new_root / "data" / "collections").exists()
        # Should have printed dry run message
        printed = " ".join(str(c) for c in mock_console.print.call_args_list)
        assert "ry run" in printed

    @patch("indexed.utils.migration.print_warning")
    def test_skips_collection_already_at_target(self, mock_warn, tmp_path):
        """Should skip and warn when collection already exists at target."""
        legacy_collections = tmp_path / "legacy" / "collections"
        legacy_collections.mkdir(parents=True)
        coll_dir = legacy_collections / "existing"
        coll_dir.mkdir()
        (coll_dir / "manifest.json").write_text("{}")
        (coll_dir / "data.txt").write_text("data")

        new_root = tmp_path / "new"
        # Pre-create the target so the skip branch is taken
        target_coll = new_root / "data" / "collections" / "existing"
        target_coll.mkdir(parents=True)

        mock_console = Mock(spec=Console)

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            with patch(
                "indexed.utils.migration.get_legacy_collections",
                return_value=["existing"],
            ):
                result = migrate_legacy_data(new_root, mock_console)

        assert result is True
        assert mock_warn.call_count >= 2
        all_calls = str(mock_warn.call_args_list)
        assert "existing" in all_calls

    def test_copies_cache_directory_items(self, tmp_path):
        """Should copy directory and file items from legacy caches directory."""
        legacy_collections = tmp_path / "legacy" / "collections"
        legacy_collections.mkdir(parents=True)
        coll_dir = legacy_collections / "coll"
        coll_dir.mkdir()
        (coll_dir / "manifest.json").write_text("{}")

        # Legacy caches as directory with mixed contents
        legacy_caches = tmp_path / "legacy" / "caches"
        legacy_caches.mkdir(parents=True)
        cache_subdir = legacy_caches / "cache_dir"
        cache_subdir.mkdir()
        (cache_subdir / "cache.dat").write_text("cache data")
        (legacy_caches / "cache_file.dat").write_text("file cache")

        new_root = tmp_path / "new"
        mock_console = Mock(spec=Console)

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            with patch(
                "indexed.utils.migration._get_legacy_caches_path",
                return_value=legacy_caches,
            ):
                with patch(
                    "indexed.utils.migration.get_legacy_collections",
                    return_value=["coll"],
                ):
                    result = migrate_legacy_data(new_root, mock_console)

        assert result is True
        target_caches = new_root / "data" / "caches"
        assert (target_caches / "cache_dir").exists()
        assert (target_caches / "cache_file.dat").exists()

    def test_copies_cache_file_directly(self, tmp_path):
        """Should copy legacy caches file directly when caches path is a file."""
        legacy_collections = tmp_path / "legacy" / "collections"
        legacy_collections.mkdir(parents=True)
        coll_dir = legacy_collections / "coll"
        coll_dir.mkdir()
        (coll_dir / "manifest.json").write_text("{}")

        # Legacy caches is a FILE (not a directory)
        legacy_caches = tmp_path / "legacy" / "caches.dat"
        legacy_caches.write_text("cache file data")

        new_root = tmp_path / "new"
        mock_console = Mock(spec=Console)

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            with patch(
                "indexed.utils.migration._get_legacy_caches_path",
                return_value=legacy_caches,
            ):
                with patch(
                    "indexed.utils.migration.get_legacy_collections",
                    return_value=["coll"],
                ):
                    result = migrate_legacy_data(new_root, mock_console)

        assert result is True
        assert (new_root / "data" / "caches" / "caches.dat").exists()


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_handles_permission_errors_gracefully(self, tmp_path):
        """Should handle permission errors during migration."""
        legacy_collections = tmp_path / "legacy" / "collections"
        legacy_collections.mkdir(parents=True)

        coll = legacy_collections / "protected"
        coll.mkdir()
        (coll / "manifest.json").write_text("{}")

        new_root = tmp_path / "new"
        mock_console = Mock(spec=Console)

        with patch("shutil.copytree", side_effect=PermissionError("Access denied")):
            with patch(
                "indexed.utils.migration._get_legacy_collections_path",
                return_value=legacy_collections,
            ):
                with patch(
                    "indexed.utils.migration.get_legacy_collections",
                    return_value=["protected"],
                ):
                    # Function catches exceptions and returns False, doesn't re-raise
                    result = migrate_legacy_data(new_root, mock_console)
                    assert result is False

    def test_handles_corrupted_manifest_json(self, tmp_path):
        """Should handle corrupted manifest.json gracefully."""
        legacy_collections = tmp_path / "legacy" / "collections"
        legacy_collections.mkdir(parents=True)

        # Collection with invalid JSON manifest
        coll = legacy_collections / "corrupted"
        coll.mkdir()
        (coll / "manifest.json").write_text("{ invalid json }")

        # Should still detect as collection (we only check file exists, not parse it)
        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            collections = get_legacy_collections()
            assert "corrupted" in collections

    def test_handles_symlinks_in_collections(self, tmp_path):
        """Should handle symlinked collections appropriately."""
        legacy_collections = tmp_path / "legacy" / "collections"
        legacy_collections.mkdir(parents=True)

        # Create actual collection
        actual = tmp_path / "actual"
        actual.mkdir()
        (actual / "manifest.json").write_text("{}")

        # Create symlink to it
        link = legacy_collections / "linked"
        link.symlink_to(actual)

        with patch(
            "indexed.utils.migration._get_legacy_collections_path",
            return_value=legacy_collections,
        ):
            collections = get_legacy_collections()
            # Should detect symlinked collection if it has manifest
            assert "linked" in collections
