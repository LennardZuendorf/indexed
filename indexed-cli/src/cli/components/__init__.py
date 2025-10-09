"""Reusable Rich Components for CLI Design System.

This package provides centralized, reusable components for building
consistent and beautiful terminal UIs with Rich.

All components follow the card-based design language with cyan accents
and consistent spacing/typography.
"""

from .theme import (
    # Colors
    ACCENT_COLOR,
    ACCENT_STYLE,
    ERROR_COLOR,
    WARNING_COLOR,
    SUCCESS_COLOR,
    INFO_COLOR,
    
    # Styles
    TITLE_STYLE,
    LABEL_STYLE,
    VALUE_STYLE,
    SECONDARY_STYLE,
    
    # Layout
    CARD_PADDING,
    INFO_ROW_LABEL_WIDTH,
    DETAIL_CARD_WIDTH,
    CARD_BORDER_STYLE,
    
    # Helpers
    get_error_style,
    get_warning_style,
    get_success_style,
    get_accent_style,
    get_label_style,
    get_title_style,
    get_help_theme_styles,
)

from .info_row import (
    create_info_row,
    create_info_rows,
)

from .cards import (
    create_info_card,
    create_detail_card,
    create_grid_cards,
)

from .summary import (
    create_summary,
    create_count_summary,
    create_total_summary,
)

from .status import (
    OperationStatus,
    SearchStatus,  # Backwards compatibility
)

__all__ = [
    # Theme
    "ACCENT_COLOR",
    "ACCENT_STYLE",
    "ERROR_COLOR",
    "WARNING_COLOR",
    "SUCCESS_COLOR",
    "INFO_COLOR",
    "TITLE_STYLE",
    "LABEL_STYLE",
    "VALUE_STYLE",
    "SECONDARY_STYLE",
    "CARD_PADDING",
    "INFO_ROW_LABEL_WIDTH",
    "DETAIL_CARD_WIDTH",
    "CARD_BORDER_STYLE",
    "get_error_style",
    "get_warning_style",
    "get_success_style",
    "get_accent_style",
    "get_label_style",
    "get_title_style",
    "get_help_theme_styles",
    
    # Info Rows
    "create_info_row",
    "create_info_rows",
    
    # Cards
    "create_info_card",
    "create_detail_card",
    "create_grid_cards",
    
    # Summary
    "create_summary",
    "create_count_summary",
    "create_total_summary",
    
    # Status
    "OperationStatus",
    "SearchStatus",  # Backwards compatibility
]
