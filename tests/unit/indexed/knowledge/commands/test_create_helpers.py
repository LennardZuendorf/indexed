"""Tests for create command helpers."""

from unittest.mock import Mock, patch, MagicMock
import pytest
import typer

from indexed.knowledge.commands._create_helpers import execute_create_command
from indexed_config import ValidationResult
from core.v1.engine.services import SourceConfig


class TestExecuteCreateCommand:
    """Test execute_create_command function."""

    @patch("indexed.knowledge.commands._create_helpers.setup_root_logger")
    @patch("indexed.knowledge.commands._create_helpers.ConfigService")
    @patch("indexed.knowledge.commands._create_helpers.is_verbose_mode")
    @patch("indexed.knowledge.commands._create_helpers.svc_create")
    @patch("indexed.knowledge.commands._create_helpers.svc_status")
    @patch("indexed.knowledge.commands._create_helpers.print_success")
    def test_execute_with_all_fields_present(
        self,
        mock_print_success,
        mock_status,
        mock_create,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should create collection when all required fields are present."""
        mock_config = Mock()
        mock_config.validate_requirements.return_value = ValidationResult(
            present={"path": "/test", "include_patterns": ["*"]},
            missing=[],
            field_info={},
        )
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        mock_status_item = MagicMock()
        mock_status_item.number_of_documents = 10
        mock_status_item.updated_time = "2024-01-01T00:00:00"
        mock_status.return_value = [mock_status_item]

        def build_source_config(present, coll_name):
            return SourceConfig(
                name=coll_name,
                type="localFiles",
                base_url_or_path=present["path"],
                indexer="default",
            )

        execute_create_command(
            collection="test-collection",
            source_type="localFiles",
            config_class=Mock,
            namespace="sources.files",
            cli_overrides={},
            prompt_missing_fields=lambda v, c, n: None,
            build_source_config=build_source_config,
            success_message_suffix="from files",
            verbose=False,
            json_logs=False,
            log_level=None,
            use_cache=True,
            force=False,
        )

        mock_create.assert_called_once()
        mock_status.assert_called_once_with(["test-collection"], collections_path=None)
        mock_print_success.assert_called_once()

    @patch("indexed.knowledge.commands._create_helpers.setup_root_logger")
    @patch("indexed.knowledge.commands._create_helpers.ConfigService")
    @patch("indexed.knowledge.commands._create_helpers.is_verbose_mode")
    @patch("indexed.knowledge.commands._create_helpers.svc_create")
    @patch("indexed.knowledge.commands._create_helpers.svc_status")
    @patch("indexed.knowledge.commands._create_helpers.print_error")
    def test_execute_prompts_for_missing_fields(
        self,
        mock_print_error,
        mock_status,
        mock_create,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should prompt for missing fields."""
        mock_config = Mock()
        mock_config.validate_requirements.return_value = ValidationResult(
            present={},
            missing=["path"],
            field_info={"path": {"sensitive": False}},
        )
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        prompt_called = []

        def prompt_missing_fields(validation, config, namespace):
            prompt_called.append(True)
            validation.present["path"] = "/prompted/path"
            validation.missing.clear()

        def build_source_config(present, coll_name):
            return SourceConfig(
                name=coll_name,
                type="localFiles",
                base_url_or_path=present.get("path", ""),
                indexer="default",
            )

        mock_status_item = MagicMock()
        mock_status_item.number_of_documents = 5
        mock_status_item.updated_time = "2024-01-01T00:00:00"
        mock_status.return_value = [mock_status_item]

        execute_create_command(
            collection="test-collection",
            source_type="localFiles",
            config_class=Mock,
            namespace="sources.files",
            cli_overrides={},
            prompt_missing_fields=prompt_missing_fields,
            build_source_config=build_source_config,
            success_message_suffix="from files",
            verbose=False,
            json_logs=False,
            log_level=None,
            use_cache=True,
            force=False,
        )

        assert len(prompt_called) == 1
        mock_create.assert_called_once()

    @patch("indexed.knowledge.commands._create_helpers.setup_root_logger")
    @patch("indexed.knowledge.commands._create_helpers.ConfigService")
    @patch("indexed.knowledge.commands._create_helpers.is_verbose_mode")
    @patch("indexed.knowledge.commands._create_helpers.svc_create")
    @patch("indexed.knowledge.commands._create_helpers.print_error")
    def test_execute_handles_creation_error(
        self,
        mock_print_error,
        mock_create,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should handle creation errors gracefully."""
        mock_config = Mock()
        mock_config.validate_requirements.return_value = ValidationResult(
            present={"path": "/test"},
            missing=[],
            field_info={},
        )
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False
        mock_create.side_effect = Exception("Creation failed")

        def build_source_config(present, coll_name):
            return SourceConfig(
                name=coll_name,
                type="localFiles",
                base_url_or_path=present["path"],
                indexer="default",
            )

        with pytest.raises(typer.Exit):
            execute_create_command(
                collection="test-collection",
                source_type="localFiles",
                config_class=Mock,
                namespace="sources.files",
                cli_overrides={},
                prompt_missing_fields=lambda v, c, n: None,
                build_source_config=build_source_config,
                success_message_suffix="from files",
                verbose=False,
                json_logs=False,
                log_level=None,
                use_cache=True,
                force=False,
            )

        mock_print_error.assert_called()

    @patch("indexed.knowledge.commands._create_helpers.setup_root_logger")
    @patch("indexed.knowledge.commands._create_helpers.ConfigService")
    @patch("indexed.knowledge.commands._create_helpers.is_verbose_mode")
    @patch("indexed.knowledge.commands._create_helpers.svc_create")
    @patch("indexed.knowledge.commands._create_helpers.svc_status")
    @patch("indexed.knowledge.commands._create_helpers.print_error")
    def test_execute_handles_invalid_collection_verification(
        self,
        mock_print_error,
        mock_status,
        mock_create,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should handle invalid collection verification."""
        mock_config = Mock()
        mock_config.validate_requirements.return_value = ValidationResult(
            present={"path": "/test"},
            missing=[],
            field_info={},
        )
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        # Return empty list (collection not found)
        mock_status.return_value = []

        def build_source_config(present, coll_name):
            return SourceConfig(
                name=coll_name,
                type="localFiles",
                base_url_or_path=present["path"],
                indexer="default",
            )

        with pytest.raises(typer.Exit):
            execute_create_command(
                collection="test-collection",
                source_type="localFiles",
                config_class=Mock,
                namespace="sources.files",
                cli_overrides={},
                prompt_missing_fields=lambda v, c, n: None,
                build_source_config=build_source_config,
                success_message_suffix="from files",
                verbose=False,
                json_logs=False,
                log_level=None,
                use_cache=True,
                force=False,
            )

        mock_print_error.assert_called()

    @patch("indexed.knowledge.commands._create_helpers.setup_root_logger")
    @patch("indexed.knowledge.commands._create_helpers.ConfigService")
    @patch("indexed.knowledge.commands._create_helpers.is_verbose_mode")
    @patch("indexed.knowledge.commands._create_helpers.svc_create")
    @patch("indexed.knowledge.commands._create_helpers.svc_status")
    @patch("indexed.knowledge.commands._create_helpers.print_error")
    def test_execute_handles_collection_without_updated_time(
        self,
        mock_print_error,
        mock_status,
        mock_create,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should handle collection without updated_time."""
        mock_config = Mock()
        mock_config.validate_requirements.return_value = ValidationResult(
            present={"path": "/test"},
            missing=[],
            field_info={},
        )
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False

        mock_status_item = MagicMock()
        mock_status_item.number_of_documents = 0
        mock_status_item.updated_time = None  # No updated_time
        mock_status.return_value = [mock_status_item]

        def build_source_config(present, coll_name):
            return SourceConfig(
                name=coll_name,
                type="localFiles",
                base_url_or_path=present["path"],
                indexer="default",
            )

        with pytest.raises(typer.Exit):
            execute_create_command(
                collection="test-collection",
                source_type="localFiles",
                config_class=Mock,
                namespace="sources.files",
                cli_overrides={},
                prompt_missing_fields=lambda v, c, n: None,
                build_source_config=build_source_config,
                success_message_suffix="from files",
                verbose=False,
                json_logs=False,
                log_level=None,
                use_cache=True,
                force=False,
            )

        mock_print_error.assert_called()

    @patch("indexed.knowledge.commands._create_helpers.setup_root_logger")
    @patch("indexed.knowledge.commands._create_helpers.ConfigService")
    @patch("indexed.knowledge.commands._create_helpers.is_verbose_mode")
    @patch("indexed.knowledge.commands._create_helpers.logger")
    @patch("indexed.knowledge.commands._create_helpers.svc_create")
    @patch("indexed.knowledge.commands._create_helpers.svc_status")
    @patch("indexed.knowledge.commands._create_helpers.print_success")
    def test_execute_verbose_mode_logging(
        self,
        mock_print_success,
        mock_status,
        mock_create,
        mock_logger,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should log verbose information in verbose mode."""
        mock_config = Mock()
        mock_config.validate_requirements.return_value = ValidationResult(
            present={"path": "/test"},
            missing=[],
            field_info={"path": {"sensitive": False}},
        )
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = True

        mock_status_item = MagicMock()
        mock_status_item.number_of_documents = 10
        mock_status_item.updated_time = "2024-01-01T00:00:00"
        mock_status.return_value = [mock_status_item]

        def build_source_config(present, coll_name):
            return SourceConfig(
                name=coll_name,
                type="localFiles",
                base_url_or_path=present["path"],
                indexer="default",
            )

        execute_create_command(
            collection="test-collection",
            source_type="localFiles",
            config_class=Mock,
            namespace="sources.files",
            cli_overrides={},
            prompt_missing_fields=lambda v, c, n: None,
            build_source_config=build_source_config,
            success_message_suffix="from files",
            verbose=True,
            json_logs=False,
            log_level=None,
            use_cache=True,
            force=False,
        )

        # Should have logged verbose information
        assert mock_logger.info.called

    @patch("indexed.knowledge.commands._create_helpers.setup_root_logger")
    @patch("indexed.knowledge.commands._create_helpers.ConfigService")
    @patch("indexed.knowledge.commands._create_helpers.is_verbose_mode")
    @patch("indexed.knowledge.commands._create_helpers.svc_create")
    @patch("indexed.knowledge.commands._create_helpers.svc_status")
    @patch("indexed.knowledge.commands._create_helpers.print_success")
    def test_execute_calls_verbose_pre_creation_log(
        self,
        mock_print_success,
        mock_status,
        mock_create,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should call verbose_pre_creation_log callback when provided."""
        mock_config = Mock()
        mock_config.validate_requirements.return_value = ValidationResult(
            present={"url": "https://test.com", "query": "test"},
            missing=[],
            field_info={},
        )
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = True

        mock_status_item = MagicMock()
        mock_status_item.number_of_documents = 10
        mock_status_item.updated_time = "2024-01-01T00:00:00"
        mock_status.return_value = [mock_status_item]

        pre_creation_log_called = []

        def verbose_pre_creation_log(present):
            pre_creation_log_called.append(present)

        def build_source_config(present, coll_name):
            return SourceConfig(
                name=coll_name,
                type="jiraCloud",
                base_url_or_path=present["url"],
                query=present["query"],
                indexer="default",
            )

        execute_create_command(
            collection="test-collection",
            source_type="jiraCloud",
            config_class=Mock,
            namespace="sources.jira",
            cli_overrides={},
            prompt_missing_fields=lambda v, c, n: None,
            build_source_config=build_source_config,
            success_message_suffix="from Jira",
            verbose=True,
            json_logs=False,
            log_level=None,
            use_cache=True,
            force=False,
            verbose_pre_creation_log=verbose_pre_creation_log,
        )

        assert len(pre_creation_log_called) == 1
        assert pre_creation_log_called[0]["url"] == "https://test.com"

    @patch("indexed.knowledge.commands._create_helpers.setup_root_logger")
    @patch("indexed.knowledge.commands._create_helpers.ConfigService")
    @patch("indexed.knowledge.commands._create_helpers.is_verbose_mode")
    @patch("indexed.knowledge.commands._create_helpers.svc_create")
    @patch("indexed.knowledge.commands._create_helpers.svc_status")
    @patch("indexed.knowledge.commands._create_helpers.print_error")
    def test_execute_handles_status_exception(
        self,
        mock_print_error,
        mock_status,
        mock_create,
        mock_verbose,
        mock_config_service,
        mock_setup_logger,
    ):
        """Should handle Exception raised by svc_status during verification."""
        mock_config = Mock()
        mock_config.validate_requirements.return_value = ValidationResult(
            present={"path": "/test"},
            missing=[],
            field_info={},
        )
        mock_config_service.instance.return_value = mock_config
        mock_verbose.return_value = False
        mock_status.side_effect = Exception("Status lookup failed")

        def build_source_config(present, coll_name):
            return SourceConfig(
                name=coll_name,
                type="localFiles",
                base_url_or_path=present["path"],
                indexer="default",
            )

        with pytest.raises(typer.Exit):
            execute_create_command(
                collection="test-collection",
                source_type="localFiles",
                config_class=Mock,
                namespace="sources.files",
                cli_overrides={},
                prompt_missing_fields=lambda v, c, n: None,
                build_source_config=build_source_config,
                success_message_suffix="from files",
                verbose=False,
                json_logs=False,
                log_level=None,
                use_cache=True,
                force=False,
            )

        mock_print_error.assert_called()
        assert "Failed to verify" in str(mock_print_error.call_args)


class TestBuildV2Connector:
    """Tests for the _build_v2_connector helper."""

    def test_local_files_instantiates_filesystem_connector(self) -> None:
        """localFiles type creates FileSystemConnector directly."""
        from indexed.knowledge.commands._create_helpers import _build_v2_connector
        from core.v1.engine.services import SourceConfig

        cfg = SourceConfig(
            name="docs",
            type="localFiles",
            base_url_or_path="/tmp/docs",
            indexer="default",
        )

        with patch("connectors.files.connector.FileSystemConnector") as mock_cls:
            mock_cls.return_value = MagicMock()
            _build_v2_connector(cfg, MagicMock())

        mock_cls.assert_called_once_with(
            path="/tmp/docs",
            include_patterns=["*"],
            exclude_patterns=[],
            fail_fast=False,
        )

    def test_local_files_forwards_reader_opts(self) -> None:
        """includePatterns and excludePatterns from reader_opts are forwarded."""
        from indexed.knowledge.commands._create_helpers import _build_v2_connector
        from core.v1.engine.services import SourceConfig

        cfg = SourceConfig(
            name="docs",
            type="localFiles",
            base_url_or_path="/tmp/docs",
            indexer="default",
            reader_opts={
                "includePatterns": ["*.md", "*.txt"],
                "excludePatterns": ["*.tmp"],
                "failFast": True,
            },
        )

        with patch("connectors.files.connector.FileSystemConnector") as mock_cls:
            mock_cls.return_value = MagicMock()
            _build_v2_connector(cfg, MagicMock())

        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["include_patterns"] == ["*.md", "*.txt"]
        assert call_kwargs["exclude_patterns"] == ["*.tmp"]
        assert call_kwargs["fail_fast"] is True

    def test_remote_connector_uses_from_config(self) -> None:
        """Non-localFiles types delegate to get_connector_class().from_config()."""
        from indexed.knowledge.commands._create_helpers import _build_v2_connector
        from core.v1.engine.services import SourceConfig

        cfg = SourceConfig(
            name="j",
            type="jira",
            base_url_or_path="https://jira.example.com",
            indexer="default",
        )
        mock_cs = MagicMock()
        mock_connector_class = MagicMock()

        with patch(
            "connectors.registry.get_connector_class", return_value=mock_connector_class
        ):
            _build_v2_connector(cfg, mock_cs)

        mock_connector_class.from_config.assert_called_once_with(mock_cs)


class TestExecuteCreateCommandV2:
    """Tests for the v2 engine path in execute_create_command."""

    @patch("core.v2.services.create")
    @patch("core.v2.services.status")
    @patch("indexed.knowledge.commands._create_helpers.ConfigService")
    @patch("indexed.knowledge.commands._create_helpers.setup_root_logger")
    @patch("indexed.knowledge.commands._create_helpers.is_verbose_mode")
    def test_v2_engine_calls_v2_create(
        self,
        mock_verbose: Mock,
        mock_setup_logger: Mock,
        mock_config_service: Mock,
        mock_v2_status: Mock,
        mock_v2_create: Mock,
    ) -> None:
        """engine='v2' creates the collection via core.v2.services.create."""
        from core.v1.engine.services import SourceConfig
        from core.v2.config import CoreV2EmbeddingConfig, CoreV2StorageConfig

        mock_verbose.return_value = True  # verbose → NoOpContext path (simpler)
        mock_config = Mock()
        mock_config.validate_requirements.return_value = ValidationResult(
            present={"path": "/tmp/test"},
            missing=[],
            field_info={},
        )
        mock_status_item = MagicMock()
        mock_status_item.number_of_documents = 5
        mock_status_item.updated_time = "2025-01-01T00:00:00"
        mock_v2_status.return_value = [mock_status_item]

        mock_provider = MagicMock()
        mock_provider.get.side_effect = lambda cls: (
            CoreV2EmbeddingConfig()
            if cls == CoreV2EmbeddingConfig
            else CoreV2StorageConfig()
        )
        mock_config.bind.return_value = mock_provider
        mock_config_service.instance.return_value = mock_config

        def build_source_config(present, coll_name):  # type: ignore[no-untyped-def]
            return SourceConfig(
                name=coll_name,
                type="localFiles",
                base_url_or_path=present["path"],
                indexer="default",
            )

        with patch("connectors.files.connector.FileSystemConnector") as mock_fsc:
            mock_fsc.return_value = MagicMock()
            execute_create_command(
                collection="v2-test",
                source_type="localFiles",
                config_class=Mock,
                namespace="sources.files",
                cli_overrides={},
                prompt_missing_fields=lambda v, c, n: None,
                build_source_config=build_source_config,
                success_message_suffix="from files",
                verbose=True,
                json_logs=False,
                log_level=None,
                use_cache=True,
                force=True,
                engine="v2",
            )

        mock_v2_create.assert_called_once()
        call_kwargs = mock_v2_create.call_args.kwargs
        assert "embed_model_name" in call_kwargs
        assert "store_type" in call_kwargs

    @patch("core.v2.services.create")
    @patch("core.v2.services.status")
    @patch("indexed.knowledge.commands._create_helpers.ConfigService")
    @patch("indexed.knowledge.commands._create_helpers.setup_root_logger")
    @patch("indexed.knowledge.commands._create_helpers.is_verbose_mode")
    def test_v2_engine_verifies_via_v2_status(
        self,
        mock_verbose: Mock,
        mock_setup_logger: Mock,
        mock_config_service: Mock,
        mock_v2_status: Mock,
        mock_v2_create: Mock,
    ) -> None:
        """engine='v2' uses core.v2.services.status for post-creation verification."""
        from core.v1.engine.services import SourceConfig
        from core.v2.config import CoreV2EmbeddingConfig, CoreV2StorageConfig

        mock_verbose.return_value = True
        mock_config = Mock()
        mock_config.validate_requirements.return_value = ValidationResult(
            present={"path": "/tmp/test"},
            missing=[],
            field_info={},
        )
        mock_status_item = MagicMock()
        mock_status_item.number_of_documents = 3
        mock_status_item.updated_time = "2025-06-01T00:00:00"
        mock_v2_status.return_value = [mock_status_item]

        mock_provider = MagicMock()
        mock_provider.get.side_effect = lambda cls: (
            CoreV2EmbeddingConfig()
            if cls == CoreV2EmbeddingConfig
            else CoreV2StorageConfig()
        )
        mock_config.bind.return_value = mock_provider
        mock_config_service.instance.return_value = mock_config

        def build_source_config(present, coll_name):  # type: ignore[no-untyped-def]
            return SourceConfig(
                name=coll_name,
                type="localFiles",
                base_url_or_path="/tmp",
                indexer="default",
            )

        with patch("connectors.files.connector.FileSystemConnector") as mock_fsc:
            mock_fsc.return_value = MagicMock()
            execute_create_command(
                collection="v2-verify",
                source_type="localFiles",
                config_class=Mock,
                namespace="sources.files",
                cli_overrides={},
                prompt_missing_fields=lambda v, c, n: None,
                build_source_config=build_source_config,
                success_message_suffix="from files",
                verbose=True,
                json_logs=False,
                log_level=None,
                use_cache=True,
                force=True,
                engine="v2",
            )

        # v2_status called at least once (verification step, after creation)
        assert mock_v2_status.call_count >= 1
