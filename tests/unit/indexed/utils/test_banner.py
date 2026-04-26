"""Tests for ASCII art banner."""

from unittest.mock import MagicMock, patch


class TestPrintIndexedBanner:
    """Tests for print_indexed_banner function."""

    @patch("indexed.utils.banner.text2art")
    @patch("indexed.utils.banner.Console")
    def test_banner_runs_without_exception(self, mock_console_cls, mock_text2art):
        """print_indexed_banner should complete without raising."""
        mock_text2art.return_value = "INDEXED\nINDEXED"
        mock_console_cls.return_value = MagicMock()

        from indexed.utils.banner import print_indexed_banner

        print_indexed_banner()

    @patch("indexed.utils.banner.text2art")
    @patch("indexed.utils.banner.Console")
    def test_banner_handles_single_line_art(self, mock_console_cls, mock_text2art):
        """print_indexed_banner handles single-line ASCII art without error."""
        mock_text2art.return_value = "█ INDEXED █"
        mock_console_cls.return_value = MagicMock()

        from indexed.utils.banner import print_indexed_banner

        print_indexed_banner()

    @patch("indexed.utils.banner.text2art")
    @patch("indexed.utils.banner.Console")
    def test_banner_handles_multi_line_art(self, mock_console_cls, mock_text2art):
        """print_indexed_banner handles multi-line ASCII art without error."""
        mock_text2art.return_value = "█ IN █\n█ DE █\n█ XED █"
        mock_console_cls.return_value = MagicMock()

        from indexed.utils.banner import print_indexed_banner

        print_indexed_banner()

    @patch("indexed.utils.banner.text2art")
    @patch("indexed.utils.banner.Console")
    def test_banner_handles_art_with_block_characters(
        self, mock_console_cls, mock_text2art
    ):
        """print_indexed_banner handles mix of block and non-block characters."""
        mock_text2art.return_value = "█|INDEXED|█"
        mock_console_cls.return_value = MagicMock()

        from indexed.utils.banner import print_indexed_banner

        print_indexed_banner()
