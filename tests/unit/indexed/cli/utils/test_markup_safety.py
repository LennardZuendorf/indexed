"""R7: Rich markup safety for user-controlled CLI output.

The shared CLI `console` (`indexed.cli.utils.console.console`) has Rich
markup parsing enabled — required for the app's own intentional style tags
(`[dim]...[/dim]`, `[{style}]...[/{style}]` in cards/init).
User-controlled or content-derived strings (search query, collection name,
config values, file paths, model names) must never reach a markup-parsed
sink as a raw `str`: bracket characters (e.g. `list[int]`) are parsed as
style tags and silently dropped, or raise `rich.errors.MarkupError`.

Each test below renders through the *real* Rich renderer (a recording
`Console`) rather than mocking, so a regression shows up as either a raised
exception or as the bracketed text going missing from the captured output.
"""

from __future__ import annotations

from rich.console import Console as RichConsole


class TestRenderUserText:
    """Unit tests for the `render_user_text` helper itself."""

    def test_renders_brackets_literally(self):
        from indexed.cli.utils.console import render_user_text

        rec = RichConsole(record=True, force_terminal=True, width=100)
        rec.print(render_user_text("list[int]"))
        assert rec.export_text().strip() == "list[int]"

    def test_applies_style_without_parsing_value(self):
        from indexed.cli.utils.console import render_user_text

        text = render_user_text("a[b]/[c]", style="bold")
        assert text.plain == "a[b]/[c]"
        assert text.style == "bold"

    def test_non_string_values_are_stringified(self):
        from indexed.cli.utils.console import render_user_text

        text = render_user_text(42)
        assert text.plain == "42"


class TestProgressBarLabelSafety:
    """progress_bar.py — build_search_phase_label (search query/collection)."""

    def test_query_and_collection_brackets_render_literally(self, monkeypatch):
        from indexed.cli.utils import progress_bar
        from indexed.cli.utils.progress_bar import (
            RichPhasedProgress,
            build_search_phase_label,
        )

        rec = RichConsole(record=True, force_terminal=True, width=120)
        monkeypatch.setattr(progress_bar, "console", rec)

        label = build_search_phase_label("list[int]", "my[coll]")
        progress = RichPhasedProgress(show_bar=False)
        with progress:
            progress.start_phase(label)
            progress.finish_phase(label)

        text = rec.export_text()
        assert "list[int]" in text
        assert "my[coll]" in text


class TestBuildProgressTitleSafety:
    """progress_bar.py — build_progress_title (collection name in section
    title), reached on the normal ``index create``/``index remove``
    interactive path via ``RichPhasedProgress.__enter__``."""

    def test_collection_with_brackets_renders_literally(self, monkeypatch):
        from indexed.cli.utils import progress_bar
        from indexed.cli.utils.progress_bar import (
            RichPhasedProgress,
            build_progress_title,
        )

        rec = RichConsole(record=True, force_terminal=True, width=120)
        monkeypatch.setattr(progress_bar, "console", rec)

        title = build_progress_title("Creating", "my[coll]", "Local Files")
        with RichPhasedProgress(title=title, show_bar=False):
            pass

        text = rec.export_text()
        assert "my[coll]" in text


class TestProgressBarLogSafety:
    """progress_bar.py — RichPhasedProgress.log(), reached via
    init.py's "already cached" status message which embeds the user's
    ``--model`` value."""

    def test_log_message_with_brackets_renders_literally(self, monkeypatch):
        from indexed.cli.utils import progress_bar
        from indexed.cli.utils.progress_bar import RichPhasedProgress

        rec = RichConsole(record=True, force_terminal=True, width=120)
        monkeypatch.setattr(progress_bar, "console", rec)

        with RichPhasedProgress(show_bar=False) as progress:
            progress.log("org/model[v2] already cached")

        text = rec.export_text()
        assert "org/model[v2] already cached" in text


class TestInitPhaseNameSafety:
    """init.py — the download-phase name embeds the user's ``--model`` value
    (``init.py:101-102``), reaching ``RichPhasedProgress.start_phase()`` /
    ``finish_phase()``: a Progress task description re-parsed as markup by
    ``TextColumn`` (same sink family as ``build_search_phase_label``)."""

    def test_model_name_with_brackets_renders_literally(self, monkeypatch):
        from unittest.mock import patch as mock_patch

        from typer.testing import CliRunner

        from indexed.cli.app import app
        from indexed.cli.utils import progress_bar

        rec = RichConsole(record=True, force_terminal=True, width=120)
        monkeypatch.setattr(progress_bar, "console", rec)
        monkeypatch.setattr(progress_bar, "is_interactive", lambda: True)

        runner = CliRunner()
        with (
            mock_patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager.is_model_cached",
                return_value=False,
            ),
            mock_patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager.ensure_model",
                return_value="/tmp/hf/snap",
            ),
            mock_patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager.get_cache_info",
                return_value={
                    "cache_dir": "/tmp/hf",
                    "models": [],
                    "total_size_mb": 0,
                },
            ),
        ):
            result = runner.invoke(app, ["init", "--model", "org/model[v2]"])

        assert result.exit_code == 0, result.output
        assert "org/model[v2]" in rec.export_text()


class TestKeyValuePanelSafety:
    """key_value_panel.py — grid cell values (config values/paths)."""

    def test_value_with_brackets_renders_literally(self):
        from indexed.cli.utils.components.key_value_panel import (
            create_key_value_panel,
        )

        panel = create_key_value_panel(
            "Sources",
            [("files", "path", "/data/proj[ects]/docs")],
            category_width=10,
            key_width=10,
        )
        rec = RichConsole(record=True, force_terminal=True, width=100)
        rec.print(panel)
        text = rec.export_text()
        assert "/data/proj[ects]/docs" in text

    def test_two_column_value_with_brackets_renders_literally(self):
        from indexed.cli.utils.components.key_value_panel import (
            create_simple_key_value_panel,
        )

        panel = create_simple_key_value_panel(
            "Workspace",
            [("mode", "local[override]")],
            key_width=15,
        )
        rec = RichConsole(record=True, force_terminal=True, width=100)
        rec.print(panel)
        text = rec.export_text()
        assert "local[override]" in text

    def test_category_and_key_columns_with_brackets_render_literally(self):
        """category/key are dot-path segments a user can set to an arbitrary
        string via ``indexed config set <key> <value>`` — only the value
        column was wrapped previously; category/key must be too."""
        from indexed.cli.utils.components.key_value_panel import (
            create_key_value_panel,
        )

        panel = create_key_value_panel(
            "Sources",
            [("weird[cat]", "weird[key]", "v")],
            category_width=14,
            key_width=14,
        )
        rec = RichConsole(record=True, force_terminal=True, width=100)
        rec.print(panel)
        text = rec.export_text()
        assert "weird[cat]" in text
        assert "weird[key]" in text


class TestCardsTitleSafety:
    """cards.py — card title (values already Text()-wrapped upstream)."""

    def test_detail_card_title_with_brackets_renders_literally(self):
        from indexed.cli.utils.components.cards import create_detail_card

        card = create_detail_card(title="coll[ection]", rows=[("k", "v")])
        rec = RichConsole(record=True, force_terminal=True, width=100)
        rec.print(card)
        text = rec.export_text()
        assert "coll[ection]" in text

    def test_info_card_title_with_subtitle_and_brackets_renders_literally(self):
        from indexed.cli.utils.components.cards import create_info_card

        card = create_info_card(
            title="coll[ection]", rows=[("k", "v")], subtitle="src[type]"
        )
        rec = RichConsole(record=True, force_terminal=True, width=100)
        rec.print(card)
        text = rec.export_text()
        assert "coll[ection]" in text
        assert "src[type]" in text


class TestInitModelNameSafety:
    """init.py — model name / cache dir in the setup-complete summary."""

    def test_model_name_and_cache_dir_with_brackets_render_literally(self):
        from unittest.mock import patch

        from typer.testing import CliRunner

        from indexed.cli.app import app

        runner = CliRunner()
        with (
            patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager.is_model_cached",
                return_value=True,
            ),
            patch(
                "indexed.core.v1.engine.indexes.embeddings.model_manager.get_cache_info",
                return_value={
                    "cache_dir": "/tmp/hf/cache[x]",
                    "models": [{"name": "org/model[v2]", "size_mb": 80, "path": "/p"}],
                    "total_size_mb": 80,
                },
            ),
        ):
            result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert "org/model[v2]" in result.output
        assert "/tmp/hf/cache[x]" in result.output
