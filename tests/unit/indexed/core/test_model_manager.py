"""Tests for model_manager — HuggingFace cache-aware model management."""

import fnmatch
import json

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def _make_hf_cache_structure(
    tmp_path: Path, model_name: str = "all-MiniLM-L6-v2"
) -> Path:
    """Create a realistic HuggingFace hub cache directory for a model."""
    repo_dir = tmp_path / f"models--sentence-transformers--{model_name}"
    blobs = repo_dir / "blobs"
    refs = repo_dir / "refs"
    snap = repo_dir / "snapshots" / "abc123deadbeef"

    blobs.mkdir(parents=True)
    refs.mkdir(parents=True)
    snap.mkdir(parents=True)

    (blobs / "fakehash1").write_text("{}")
    (blobs / "fakehash2").write_bytes(b"\x00" * 1024)
    (snap / "config.json").write_text('{"model_type": "bert"}')
    (snap / "model.safetensors").write_bytes(b"\x00" * 2048)
    (refs / "main").write_text("abc123deadbeef")

    return repo_dir


class TestGetHfCacheDir:
    def test_default_location(self):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _get_hf_cache_dir,
        )

        with patch.dict("os.environ", {}, clear=True):
            result = _get_hf_cache_dir()
            assert result == Path.home() / ".cache" / "huggingface" / "hub"

    def test_respects_hf_hub_cache_env(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _get_hf_cache_dir,
        )

        with patch.dict("os.environ", {"HF_HUB_CACHE": str(tmp_path)}):
            assert _get_hf_cache_dir() == tmp_path

    def test_respects_hf_home_env(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _get_hf_cache_dir,
        )

        with patch.dict("os.environ", {"HF_HOME": str(tmp_path)}, clear=True):
            result = _get_hf_cache_dir()
            assert result == tmp_path / "hub"

    def test_hf_hub_cache_takes_priority(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _get_hf_cache_dir,
        )

        custom = tmp_path / "custom"
        with patch.dict(
            "os.environ",
            {"HF_HUB_CACHE": str(custom), "HF_HOME": str(tmp_path / "other")},
        ):
            assert _get_hf_cache_dir() == custom


class TestModelRepoId:
    def test_short_name_gets_prefixed(self):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _model_repo_id,
        )

        assert (
            _model_repo_id("all-MiniLM-L6-v2")
            == "sentence-transformers/all-MiniLM-L6-v2"
        )

    def test_already_qualified_unchanged(self):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _model_repo_id,
        )

        assert _model_repo_id("custom-org/my-model") == "custom-org/my-model"


class TestIsModelCached:
    def test_false_when_nothing_exists(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            is_model_cached,
        )

        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is False

    def test_false_when_dir_exists_but_no_snapshots(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            is_model_cached,
        )

        model_dir = tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2"
        model_dir.mkdir(parents=True)
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is False

    def test_false_when_snapshots_empty(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            is_model_cached,
        )

        model_dir = tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2"
        (model_dir / "snapshots" / "abc123").mkdir(parents=True)
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is False

    def test_true_when_properly_cached(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            is_model_cached,
        )

        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is True

    def test_false_when_snapshot_has_only_config(self, tmp_path):
        """A config-only snapshot is interrupted-download residue, not a cache."""
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            is_model_cached,
        )

        repo = _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        (repo / "snapshots" / "abc123deadbeef" / "model.safetensors").unlink()
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is False

    def test_true_only_when_active_revision_has_weights(self, tmp_path):
        """refs/main names the active revision; a config-only active one is not cached."""
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            is_model_cached,
        )

        repo = _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        (repo / "snapshots" / "rev-b").mkdir()
        (repo / "snapshots" / "rev-b" / "config.json").write_text("{}")
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            # Active revision rev-b is config-only → not cached (stale ignored).
            (repo / "refs" / "main").write_text("rev-b\n")
            assert is_model_cached("all-MiniLM-L6-v2") is False

            # Active revision holds weights → cached.
            (repo / "refs" / "main").write_text("abc123deadbeef")
            assert is_model_cached("all-MiniLM-L6-v2") is True

            # No refs/main → fall back to any snapshot with weights → cached.
            (repo / "refs" / "main").unlink()
            assert is_model_cached("all-MiniLM-L6-v2") is True

    def test_handles_custom_org_model(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            is_model_cached,
        )

        model_dir = tmp_path / "models--custom-org--my-model"
        snap = model_dir / "snapshots" / "abc123"
        snap.mkdir(parents=True)
        (snap / "config.json").write_text("{}")
        (snap / "model.safetensors").write_bytes(b"\x00" * 8)
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("custom-org/my-model") is True


class TestResolveSnapshotPath:
    def test_resolves_via_refs_main(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _resolve_snapshot_path,
        )

        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            path = _resolve_snapshot_path("all-MiniLM-L6-v2")
            assert "abc123deadbeef" in path

    def test_fallback_to_first_snapshot(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _resolve_snapshot_path,
        )

        repo = _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        (repo / "refs" / "main").unlink()
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            path = _resolve_snapshot_path("all-MiniLM-L6-v2")
            assert Path(path).exists()

    def test_skips_config_only_fallback_snapshot(self, tmp_path):
        """refs/main absent: pick the weighted snapshot, not the first non-empty.

        The selected snapshot must agree with ``is_model_cached`` — otherwise a
        config-only residue (sorts first) would be reported as a cached model.
        """
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _resolve_snapshot_path,
            is_model_cached,
        )

        repo = tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2"
        aaa = repo / "snapshots" / "aaa"
        bbb = repo / "snapshots" / "bbb"
        aaa.mkdir(parents=True)
        (aaa / "config.json").write_text("{}")  # config-only, sorts first
        bbb.mkdir(parents=True)
        (bbb / "model.safetensors").write_bytes(b"\x00" * 8)

        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is True
            path = _resolve_snapshot_path("all-MiniLM-L6-v2")
            assert Path(path).name == "bbb"
            assert (Path(path) / "model.safetensors").exists()

    def test_active_revision_without_weights_is_not_cached(self, tmp_path):
        """refs/main → config-only rev: predicate False AND resolver raises.

        A stale complete alternative revision must not be silently loaded
        (that would be a false cached success for the active revision).
        """
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _resolve_snapshot_path,
            is_model_cached,
        )

        repo = tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2"
        rev_a = repo / "snapshots" / "rev-a"  # complete
        rev_b = repo / "snapshots" / "rev-b"  # config-only (active)
        rev_a.mkdir(parents=True)
        (rev_a / "model.safetensors").write_bytes(b"\x00" * 8)
        rev_b.mkdir(parents=True)
        (rev_b / "config.json").write_text("{}")
        (repo / "refs").mkdir()
        (repo / "refs" / "main").write_text("rev-b\n")

        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is False
            with pytest.raises(FileNotFoundError, match="no valid snapshot"):
                _resolve_snapshot_path("all-MiniLM-L6-v2")

    def test_raises_when_only_config_only_snapshot(self, tmp_path):
        """A config-only cache is not a loadable snapshot — no false success."""
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _resolve_snapshot_path,
            is_model_cached,
        )

        snap = (
            tmp_path
            / "models--sentence-transformers--all-MiniLM-L6-v2"
            / "snapshots"
            / "aaa"
        )
        snap.mkdir(parents=True)
        (snap / "config.json").write_text("{}")

        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            assert is_model_cached("all-MiniLM-L6-v2") is False
            with pytest.raises(FileNotFoundError, match="no valid snapshot"):
                _resolve_snapshot_path("all-MiniLM-L6-v2")

    def test_raises_when_no_valid_snapshot(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _resolve_snapshot_path,
        )

        model_dir = tmp_path / "models--sentence-transformers--broken-model"
        (model_dir / "snapshots").mkdir(parents=True)
        (model_dir / "refs").mkdir(parents=True)
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with pytest.raises(FileNotFoundError, match="no valid snapshot"):
                _resolve_snapshot_path("broken-model")


def _allow_patterns() -> list[str]:
    """The module's download allow-list (the embedder's own file set)."""
    from indexed.core.v1.engine.indexes.embeddings.model_manager import (
        _MODEL_ALLOW_PATTERNS,
    )

    return _MODEL_ALLOW_PATTERNS


# Every path a first `index create` puts in a clean HF cache for
# sentence-transformers/all-MiniLM-L6-v2 (measured 2026-11-16: 88 MB total),
# plus the pooling config that lives one level down. `indexed init` exists to
# leave exactly this cache behind — not the 889 MB full repository snapshot.
_MEASURED_LOADED_FILES = (
    "1_Pooling/config.json",
    "config.json",
    "config_sentence_transformers.json",
    "model.safetensors",
    "modules.json",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)

# Tokenizer artifacts for other tokenizer classes: a repo ships the one its
# tokenizer needs, and a filter that only knows tokenizer.json/vocab.txt
# leaves a sentencepiece-only repo cached-but-unloadable.
_OTHER_TOKENIZER_ARTIFACTS = (
    "merges.txt",
    "sentencepiece.bpe.model",
    "spiece.model",
    "spm.model",
    "tokenizer.model",
    "vocab.json",
)

# Module payload shapes: sentence-transformers module dirs are named per model
# (1_Pooling, 2_Dense, ...), so the filter must cover any of them, not just
# the default model's layout.
_MODULE_PAYLOADS = (
    "1_Pooling/config.json",
    "2_Dense/config.json",
    "2_Dense/model.safetensors",
    "2_Dense/pytorch_model.bin",
)

# Runtime variants in the same repository that no Indexed code path loads.
_UNUSED_VARIANTS = (
    "onnx/model.onnx",
    "onnx/model_qint8_avx512.onnx",
    "openvino/openvino_model.xml",
    "tf_model.h5",
    "rust_model.ot",
    "pytorch_model.bin",
    "data_config.json",
    "train_script.py",
    "README.md",  # documentation only: no code path reads it
)


def _matches_any(path: str, patterns: list[str]) -> bool:
    """Hub's pattern semantics: fnmatch over the repo-relative path."""
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


class TestDownloadAllowPatterns:
    def test_covers_the_files_a_first_create_downloads(self):
        """The allow-list must match every file the embedder really loads."""
        missing = [
            f for f in _MEASURED_LOADED_FILES if not _matches_any(f, _allow_patterns())
        ]
        assert missing == []

    def test_excludes_runtime_variants_nobody_loads(self):
        """ONNX / OpenVINO / TF / Rust / torch-.bin variants stay out."""
        leaked = [f for f in _UNUSED_VARIANTS if _matches_any(f, _allow_patterns())]
        assert leaked == []

    def test_weights_are_fetched_in_a_form_the_predicate_accepts(self):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _WEIGHT_FILES,
        )

        assert any(_matches_any(w, _allow_patterns()) for w in _WEIGHT_FILES)

    def test_covers_every_tokenizer_artifact_class(self):
        """A sentencepiece-only repo must not come back cached-but-unloadable."""
        missing = [
            f
            for f in _OTHER_TOKENIZER_ARTIFACTS
            if not _matches_any(f, _allow_patterns())
        ]
        assert missing == []

    def test_covers_module_payloads_under_any_module_name(self):
        """The filter follows module payload shapes, not one model's layout."""
        missing = [
            f for f in _MODULE_PAYLOADS if not _matches_any(f, _allow_patterns())
        ]
        assert missing == []

    def test_patterns_are_non_empty_strings(self):
        patterns = _allow_patterns()
        assert patterns
        assert all(isinstance(p, str) and p for p in patterns)


def _weighted_snapshot(base: Path, model_name: str = "all-MiniLM-L6-v2") -> Path:
    """A bare snapshot holding weights (no refs/main, not under a cache dir)."""
    snap = base / "snapshot" / f"models--sentence-transformers--{model_name}"
    snap.mkdir(parents=True)
    (snap / "model.safetensors").write_bytes(b"\x00" * 8)
    return snap


def _snapshot_with(base: Path, files: dict[str, str | bytes]) -> Path:
    """A snapshot laid out exactly like the hub's: one symlink-free file tree."""
    snap = base / "snapshot"
    for rel, content in files.items():
        target = snap / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content)
    return snap


def _modules_json(*paths: str) -> str:
    return json.dumps(
        [
            {"idx": i, "name": str(i), "path": path, "type": "module"}
            for i, path in enumerate(paths)
        ]
    )


class TestSnapshotLoadSet:
    """The registry the loader reads, not a hardcoded model shape, decides."""

    @pytest.mark.parametrize(
        ("modules", "expected"),
        [
            (None, []),  # no modules.json: nothing to verify against
            ("not json", []),  # unreadable registry is the repo's bug
            ('{"modules": []}', []),  # wrong shape
            (
                '[{"path": ""}, {"path": "/"}, {"path": "1_Pooling"},'
                ' {"path": "2_Dense/"}, {"path": 3}, "x"]',
                ["1_Pooling", "2_Dense"],
            ),
        ],
    )
    def test_referenced_module_dirs(self, tmp_path, modules, expected):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _referenced_module_dirs,
        )

        if modules is not None:
            (tmp_path / "modules.json").write_text(modules)
        assert _referenced_module_dirs(tmp_path) == expected

    def test_tokenizer_artifacts(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            _tokenizer_missing,
        )

        assert _tokenizer_missing(tmp_path) is False  # no tokenizer declared
        (tmp_path / "tokenizer_config.json").write_text("{}")
        assert _tokenizer_missing(tmp_path) is True  # declared, nothing landed
        (tmp_path / "vocab.txt").write_text("x")
        assert _tokenizer_missing(tmp_path) is False


class TestEnsureModel:
    def test_skips_download_when_cached(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import ensure_model

        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            path = ensure_model("all-MiniLM-L6-v2", force=False)
            assert "abc123deadbeef" in path

    def test_downloads_when_not_cached(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import ensure_model

        snap = _weighted_snapshot(tmp_path)
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path / "empty",
        ):
            with patch(
                "huggingface_hub.snapshot_download",
                return_value=str(snap),
            ) as mock_dl:
                path = ensure_model("all-MiniLM-L6-v2", force=False)
                mock_dl.assert_called_once_with(
                    repo_id="sentence-transformers/all-MiniLM-L6-v2",
                    allow_patterns=_allow_patterns(),
                )
                assert path == str(snap)

    def test_force_downloads_even_when_cached(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import ensure_model

        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        snap = _weighted_snapshot(tmp_path)
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "huggingface_hub.snapshot_download",
                return_value=str(snap),
            ) as mock_dl:
                ensure_model("all-MiniLM-L6-v2", force=True)
                mock_dl.assert_called_once()

    def test_transient_failure_is_bounded_and_actionable(self, tmp_path):
        """Injected network failure: 3 attempts, one actionable diagnostic."""
        import indexed.core.model_acquisition as ma
        from indexed.core.errors import ModelAcquisitionError
        from indexed.core.v1.engine.indexes.embeddings.model_manager import ensure_model

        def boom(*a, **k):
            raise ConnectionError("Failed to resolve 'huggingface.co'")

        slept: list[float] = []
        with (
            patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
                return_value=tmp_path,
            ),
            patch("huggingface_hub.snapshot_download", side_effect=boom) as mock_dl,
            patch.object(ma, "_sleep", lambda s: slept.append(s)),
        ):
            with pytest.raises(ModelAcquisitionError) as excinfo:
                ensure_model("all-MiniLM-L6-v2", force=False)

        assert mock_dl.call_count == ma.MAX_ATTEMPTS  # bounded retry budget
        assert slept == [1.0, 2.0]  # exponential backoff, no third sleep
        err = excinfo.value
        assert err.category == ma.NETWORK
        assert err.attempts == ma.MAX_ATTEMPTS
        message = str(err)
        assert "all-MiniLM-L6-v2" in message  # names the model
        assert str(tmp_path) in message  # names the cache
        assert "indexed init" in message  # honest remedy

    def test_auth_failure_is_not_retried(self, tmp_path):
        import indexed.core.model_acquisition as ma
        from indexed.core.errors import ModelAcquisitionError
        from indexed.core.v1.engine.indexes.embeddings.model_manager import ensure_model

        class HfHubHTTPError(Exception):
            def __init__(self) -> None:
                self.response = type("R", (), {"status_code": 401})()

        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "huggingface_hub.snapshot_download",
                side_effect=HfHubHTTPError(),
            ) as mock_dl:
                with pytest.raises(ModelAcquisitionError) as excinfo:
                    ensure_model("all-MiniLM-L6-v2", force=False)

        assert mock_dl.call_count == 1  # permanent failure → no retry
        assert excinfo.value.category == ma.AUTH
        assert excinfo.value.attempts == 1

    def test_weightless_download_is_not_false_success(self, tmp_path):
        """A 'successful' call with no weights must raise, never report cached."""
        from indexed.core.errors import ModelAcquisitionError
        from indexed.core.v1.engine.indexes.embeddings.model_manager import ensure_model

        empty = tmp_path / "downloaded"
        empty.mkdir()
        (empty / "config.json").write_text("{}")  # config-only residue

        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path / "empty",
        ):
            with patch("huggingface_hub.snapshot_download", return_value=str(empty)):
                with pytest.raises(ModelAcquisitionError) as excinfo:
                    ensure_model("all-MiniLM-L6-v2", force=False)

        assert excinfo.value.category == "corrupt"
        assert "indexed init --force" in str(excinfo.value)

    def test_falls_back_to_full_snapshot_when_filtered_set_has_no_weights(
        self, tmp_path
    ):
        """A repo publishing only an unprefetched variant must still initialize.

        The allow-list is bandwidth, not a correctness gate: when the filtered
        snapshot carries no weights, retry once without patterns instead of
        calling a perfectly downloadable custom model corrupt.
        """
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            ensure_model,
        )

        filtered = tmp_path / "filtered"
        filtered.mkdir()
        (filtered / "config.json").write_text("{}")  # no weights yet
        full = _weighted_snapshot(tmp_path)

        with (
            patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
                return_value=tmp_path / "empty",
            ),
            patch(
                "huggingface_hub.snapshot_download",
                side_effect=[str(filtered), str(full)],
            ) as mock_dl,
        ):
            path = ensure_model("custom-org/bin-only-model", force=False)

        assert path == str(full)
        assert mock_dl.call_count == 2
        first, second = (call.kwargs for call in mock_dl.call_args_list)
        assert first["allow_patterns"] == _allow_patterns()
        assert "allow_patterns" not in second  # last resort: whole repository

    def test_fetches_the_module_dirs_the_repo_modules_json_names(self, tmp_path):
        """A multi-module model gets its head, not just root weights.

        ``distiluse-base-multilingual-cased-v2`` and ``LaBSE`` ship root
        weights plus a ``2_Dense`` head. A filter that matched only the
        default model's ``1_Pooling`` left the head out — root weights made
        the cache predicate pass, so init said "setup complete" and every load
        raised "corrupt", with a --force remedy that rebuilt the same
        snapshot. The repo's own modules.json names the missing directory, so
        it is fetched before success is reported.
        """
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            ensure_model,
        )

        registry = _modules_json("", "1_Pooling", "2_Dense")
        filtered = _snapshot_with(
            tmp_path / "filtered",
            {
                "model.safetensors": b"\x00" * 8,
                "modules.json": registry,
                "1_Pooling/config.json": "{}",
                "tokenizer.json": "{}",
                "tokenizer_config.json": "{}",
            },
        )
        completed = _snapshot_with(
            tmp_path / "completed",
            {
                "model.safetensors": b"\x00" * 8,
                "modules.json": registry,
                "1_Pooling/config.json": "{}",
                "2_Dense/config.json": "{}",
                "2_Dense/model.safetensors": b"\x00" * 4,
                "tokenizer.json": "{}",
                "tokenizer_config.json": "{}",
            },
        )

        with (
            patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
                return_value=tmp_path / "empty",
            ),
            patch(
                "huggingface_hub.snapshot_download",
                side_effect=[str(filtered), str(completed)],
            ) as mock_dl,
        ):
            path = ensure_model("custom-org/distiluse-like", force=False)

        assert path == str(completed)
        assert (Path(path) / "2_Dense" / "model.safetensors").exists()
        assert mock_dl.call_count == 2
        first, second = (call.kwargs for call in mock_dl.call_args_list)
        assert first["allow_patterns"] == _allow_patterns()
        assert second["allow_patterns"] == _allow_patterns() + ["2_Dense/*"]

    def test_parameterless_module_dir_is_not_a_gap(self, tmp_path):
        """2_Normalize holds no files: no full re-download, no false corrupt.

        The default model's modules.json names ``2_Normalize``, which no
        repository populates. Treating an absent module dir as a gap would
        either loop (the full snapshot has no such dir either) or reject the
        cache for every user; the repo answered "no files there" when the
        module pattern matched nothing, and the snapshot is complete.
        """
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            ensure_model,
        )

        snapshot = _snapshot_with(
            tmp_path / "filtered",
            {
                "model.safetensors": b"\x00" * 8,
                "modules.json": _modules_json("", "1_Pooling", "2_Normalize"),
                "1_Pooling/config.json": "{}",
                "vocab.txt": "x",
                "tokenizer_config.json": "{}",
            },
        )

        with (
            patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
                return_value=tmp_path / "empty",
            ),
            patch(
                "huggingface_hub.snapshot_download",
                side_effect=[str(snapshot), str(snapshot)],
            ) as mock_dl,
        ):
            assert ensure_model("all-MiniLM-L6-v2", force=False) == str(snapshot)

        assert mock_dl.call_count == 2
        first, second = (call.kwargs for call in mock_dl.call_args_list)
        assert first["allow_patterns"] == _allow_patterns()
        # Still filtered: the full 889 MB repository is never the answer here.
        assert second["allow_patterns"] == _allow_patterns() + ["2_Normalize/*"]

    def test_declared_tokenizer_without_artifacts_falls_back(self, tmp_path):
        """A tokenizer layout the filter cannot name still gets one retry."""
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            ensure_model,
        )

        filtered = _snapshot_with(
            tmp_path / "filtered",
            {"model.safetensors": b"\x00" * 8, "tokenizer_config.json": "{}"},
        )
        full = _snapshot_with(
            tmp_path / "full",
            {
                "model.safetensors": b"\x00" * 8,
                "tokenizer_config.json": "{}",
                "tokenizer/tokenizer.json": "{}",
            },
        )

        with (
            patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
                return_value=tmp_path / "empty",
            ),
            patch(
                "huggingface_hub.snapshot_download",
                side_effect=[str(filtered), str(full)],
            ) as mock_dl,
        ):
            assert ensure_model("custom-org/exotic-tokenizer", force=False) == str(full)

        assert mock_dl.call_count == 2
        first, second = (call.kwargs for call in mock_dl.call_args_list)
        assert first["allow_patterns"] == _allow_patterns()
        assert "allow_patterns" not in second


class TestLoadModel:
    def test_loads_with_local_files_only_when_cached(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import load_model

        load_model.cache_clear()
        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        mock_model = MagicMock()
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "sentence_transformers.SentenceTransformer",
                return_value=mock_model,
            ) as mock_cls:
                result = load_model("all-MiniLM-L6-v2")
                # Loads the VALIDATED snapshot path (not the repo id), offline.
                args, kwargs = mock_cls.call_args
                assert args[0].endswith("abc123deadbeef")
                assert kwargs == {"local_files_only": True, "backend": "onnx"}
                mock_cls.assert_called_once()
                assert result is mock_model

    def test_falls_back_to_default_backend_when_onnx_fails(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import load_model

        load_model.cache_clear()
        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        mock_model = MagicMock()
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "sentence_transformers.SentenceTransformer",
                side_effect=[RuntimeError("ONNX not available"), mock_model],
            ) as mock_cls:
                result = load_model("all-MiniLM-L6-v2")
                assert mock_cls.call_count == 2
                # Second call falls back to default backend on the same snapshot
                args, kwargs = mock_cls.call_args
                assert args[0].endswith("abc123deadbeef")
                assert kwargs == {"local_files_only": True}
                assert result is mock_model

    def test_loads_the_weighted_snapshot_not_config_only_residue(self, tmp_path):
        """Loader snapshot must equal the one the cache predicate approved."""
        from indexed.core.v1.engine.indexes.embeddings.model_manager import load_model

        load_model.cache_clear()
        repo = tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2"
        aaa = repo / "snapshots" / "aaa"  # config-only, sorts first
        bbb = repo / "snapshots" / "bbb"
        aaa.mkdir(parents=True)
        (aaa / "config.json").write_text("{}")
        bbb.mkdir(parents=True)
        (bbb / "model.safetensors").write_bytes(b"\x00" * 8)

        mock_model = MagicMock()
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "sentence_transformers.SentenceTransformer",
                return_value=mock_model,
            ) as mock_cls:
                result = load_model("all-MiniLM-L6-v2")
                args, _ = mock_cls.call_args
                assert Path(args[0]).name == "bbb"
                assert result is mock_model

    def test_warns_and_downloads_when_not_cached(self, tmp_path, caplog):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import load_model

        load_model.cache_clear()
        mock_model = MagicMock()
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "sentence_transformers.SentenceTransformer",
                return_value=mock_model,
            ) as mock_cls:
                import logging

                with caplog.at_level(logging.WARNING):
                    load_model("not-cached-model")
                assert "not found in cache" in caplog.text
                # First attempts ONNX backend for download too
                mock_cls.assert_called_once_with(
                    "sentence-transformers/not-cached-model",
                    backend="onnx",
                )

    def test_download_failure_is_actionable(self, tmp_path):
        """Uncached download failure: bounded retry + one actionable error."""
        import indexed.core.model_acquisition as ma
        from indexed.core.errors import ModelAcquisitionError
        from indexed.core.v1.engine.indexes.embeddings.model_manager import load_model

        load_model.cache_clear()
        with (
            patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
                return_value=tmp_path,
            ),
            patch(
                "sentence_transformers.SentenceTransformer",
                side_effect=ConnectionError("Failed to resolve 'huggingface.co'"),
            ),
            patch.object(ma, "_sleep", lambda s: None),
        ):
            with pytest.raises(ModelAcquisitionError) as excinfo:
                load_model("all-MiniLM-L6-v2")
        load_model.cache_clear()

        assert excinfo.value.category == ma.NETWORK
        assert excinfo.value.attempts == ma.MAX_ATTEMPTS
        assert "all-MiniLM-L6-v2" in str(excinfo.value)

    def test_cached_but_unloadable_is_corrupt(self, tmp_path):
        """Cached yet unloadable must blame the snapshot, not the network."""
        from indexed.core.errors import ModelAcquisitionError
        from indexed.core.v1.engine.indexes.embeddings.model_manager import load_model

        load_model.cache_clear()
        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        with (
            patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
                return_value=tmp_path,
            ),
            patch(
                "sentence_transformers.SentenceTransformer",
                side_effect=OSError("broken weights"),
            ),
        ):
            with pytest.raises(ModelAcquisitionError) as excinfo:
                load_model("all-MiniLM-L6-v2")
        load_model.cache_clear()

        assert excinfo.value.category == "corrupt"
        assert "indexed init --force" in str(excinfo.value)

    def test_lru_cache_returns_same_instance(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import load_model

        load_model.cache_clear()
        _make_hf_cache_structure(tmp_path, "all-MiniLM-L6-v2")
        mock_model = MagicMock()
        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch(
                "sentence_transformers.SentenceTransformer",
                return_value=mock_model,
            ):
                m1 = load_model("all-MiniLM-L6-v2")
                m2 = load_model("all-MiniLM-L6-v2")
                assert m1 is m2


class TestGetCacheInfo:
    def test_empty_cache(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            get_cache_info,
        )

        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            info = get_cache_info()
            assert info["models"] == []
            assert info["total_size_mb"] == 0

    def test_reports_cached_models_via_scan(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            get_cache_info,
        )

        mock_repo = MagicMock()
        mock_repo.repo_type = "model"
        mock_repo.repo_id = "sentence-transformers/all-MiniLM-L6-v2"
        mock_repo.size_on_disk = 80 * 1024 * 1024
        mock_repo.revisions = [MagicMock()]
        mock_repo.last_modified = 1711000000.0
        mock_repo.repo_path = (
            tmp_path / "models--sentence-transformers--all-MiniLM-L6-v2"
        )

        mock_cache = MagicMock()
        mock_cache.repos = [mock_repo]

        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch("huggingface_hub.scan_cache_dir", return_value=mock_cache):
                info = get_cache_info()
                assert len(info["models"]) == 1
                assert (
                    info["models"][0]["name"]
                    == "sentence-transformers/all-MiniLM-L6-v2"
                )
                assert info["models"][0]["size_mb"] == 80.0

    def test_filters_non_st_models(self, tmp_path):
        from indexed.core.v1.engine.indexes.embeddings.model_manager import (
            get_cache_info,
        )

        st_repo = MagicMock()
        st_repo.repo_type = "model"
        st_repo.repo_id = "sentence-transformers/all-MiniLM-L6-v2"
        st_repo.size_on_disk = 80 * 1024 * 1024
        st_repo.revisions = [MagicMock()]
        st_repo.last_modified = 1711000000.0
        st_repo.repo_path = tmp_path / "st"

        other_repo = MagicMock()
        other_repo.repo_type = "model"
        other_repo.repo_id = "openai/whisper-large"
        other_repo.size_on_disk = 3000 * 1024 * 1024

        mock_cache = MagicMock()
        mock_cache.repos = [st_repo, other_repo]

        with patch(
            "indexed.core.v1.engine.indexes.embeddings.model_manager._get_hf_cache_dir",
            return_value=tmp_path,
        ):
            with patch("huggingface_hub.scan_cache_dir", return_value=mock_cache):
                info = get_cache_info()
                assert len(info["models"]) == 1
