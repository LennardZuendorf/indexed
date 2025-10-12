"""Reusable Rich Components for CLI Design System.

This package provides centralized, reusable components for building
consistent and beautiful terminal UIs with Rich.

All components follow the card-based design language with cyan accents
and consistent spacing/typography.
"""

from .theme import (    
    # Helpers
    get_error_style,
    get_warning_style,
    get_success_style,
    get_accent_style,
    get_label_style,
    get_title_style,
    get_heading_style,
    get_help_theme_styles,
    get_default_style,
    get_secondary_style,
    get_card_border_style,
    get_card_padding,
    get_detail_card_width,
    get_info_row_label_width,
    get_grid_card_min_width,
    get_value_style,
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
    "get_error_style",
    "get_warning_style",
    "get_success_style",
    "get_accent_style",
    "get_label_style",
    "get_title_style",
    "get_heading_style",
    "get_help_theme_styles",
    "get_default_style",
    "get_secondary_style",
    "get_card_border_style",
    "get_card_padding",
    "get_detail_card_width",
    "get_info_row_label_width",
    "get_grid_card_min_width",
    "get_value_style",
    
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
