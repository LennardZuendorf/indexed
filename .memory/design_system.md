# CLI Design System

## Overview

The Indexed CLI uses a **card-based design language** built with Rich for beautiful, consistent terminal output. All display components follow a unified visual hierarchy and styling system.

## Design Principles

### 1. Card-Based Layout
- **Primary unit**: Bordered panels (cards) containing information
- **Consistency**: All data displays use the same panel style
- **Flexibility**: Cards adapt to content and terminal width
- **Hierarchy**: Progressive disclosure through simple → detailed views

### 2. Visual Language
- **Accent Color**: Cyan (`#00ffff`) for text highlights and emphasis
- **Borders**: Grey (dim) rounded borders on all cards (matching Typer's help style)
- **Text Hierarchy**:
  - Bold Cyan: Labels on the left side (e.g., "Docs", "Chunks")
  - Normal White: Values on the right side (e.g., "13", "174")
  - Bold: Titles and collection names
  - Dim (grey): Helper text and hints
- **Spacing**: Consistent padding (0, 1) inside panels

### 3. Layout Patterns
- **Grid Layout**: Multiple cards side-by-side (2-3 columns)
- **Stack Layout**: Full-width cards for detailed views
- **Compact Layout**: Fixed-width cards for single items

## Core Components

### 1. Info Row
**Purpose**: Consistent label-value pairs with aligned formatting

**Usage**:
```python
from cli.components.info_row import create_info_row

row = create_info_row("Label", "Value")
```

**Appearance**:
```
Label     Value
```
- Label: 10 chars wide, bold cyan style
- Value: Normal/white style, left-aligned

### 2. Info Card
**Purpose**: Bordered panel containing info rows

**Usage**:
```python
from cli.components.cards import create_info_card

card = create_info_card(
    title="Collection Name",
    rows=[
        ("Docs", "13"),
        ("Chunks", "174"),
    ]
)
```

**Appearance**:
```
╭─ Collection Name ─────╮
│ Docs      13          │
│ Chunks    174         │
╰───────────────────────╯
```

### 3. Summary Line
**Purpose**: Totals and aggregate info with cyan accent

**Usage**:
```python
from cli.components.summary import create_summary

summary = create_summary("Total", "39 documents, 539 chunks")
```

**Appearance**:
```
Total: 39 documents, 539 chunks
```

## Color Palette

### Theme Colors
```python
# Primary
ACCENT_COLOR = "cyan"          # Text highlights and emphasis (not borders)
ACCENT_STYLE = "bold cyan"     # Headers, important text

# Text Hierarchy
TITLE_STYLE = "bold"           # Card titles, collection names
LABEL_STYLE = "bold cyan"      # Left-side labels (cyan and bold)
VALUE_STYLE = ""               # Right-side values (white/default)
SECONDARY_STYLE = "dim"        # Helper text, hints

# Status Colors
ERROR_COLOR = "red"            # Error messages
WARNING_COLOR = "yellow"       # Warnings
SUCCESS_COLOR = "green"        # Success messages
```

## Layout Modes

### Simple Grid View
**Use**: Overview of multiple items
**Pattern**: 2-3 cards side-by-side
**Content**: Essential info only (4-5 rows per card)

### Detailed Single View
**Use**: Deep dive into one item
**Pattern**: Single card, left-aligned, fixed width (60 chars)
**Content**: All available information

### Verbose List View
**Use**: Detailed info for all items
**Pattern**: Stacked full-width cards
**Content**: More details than simple view

## Implementation

### File Structure
```
apps/indexed-cli/src/cli/
├── components/           # Reusable Rich components
│   ├── __init__.py
│   ├── cards.py         # Card/panel components
│   ├── info_row.py      # Info row formatter
│   ├── summary.py       # Summary line component
│   └── theme.py         # Color/style constants
├── formatters/          # Command-specific formatters
│   ├── inspect_formatter.py
│   └── ...
└── commands/            # CLI commands
    ├── inspect.py
    └── ...
```

### Component Reusability
1. **Core components** in `cli/components/` - pure Rich rendering logic
2. **Formatters** in `cli/formatters/` - transform data models to components
3. **Commands** in `cli/commands/` - orchestrate data fetching and formatting

## Usage Guidelines

### Do's ✅
- Use `create_info_row()` for all label-value pairs
- Use grey (dim) borders for all cards
- Use bold cyan for labels, white for values
- Use cyan accent color for headlines and emphasis
- Keep cards compact and scannable
- Maintain consistent padding (0, 1)

### Don'ts ❌
- Don't hardcode colors - use theme constants
- Don't use cyan borders - use grey (dim) instead
- Don't mix table boxes with card panels
- Don't create custom label formatting
- Don't use full-width cards for lists
- Don't use white text for labels

## Future Enhancements

### Planned Components
- `create_error_card()` - Styled error messages
- `create_progress_card()` - Operation progress display
- `create_metric_grid()` - Grid of metric cards
- `create_table_card()` - Card wrapping data tables

### Responsive Design
- Auto-adjust columns based on terminal width
- Graceful degradation for narrow terminals
- Mobile-friendly fallbacks

## Examples

### Inspect Command
Uses all core components:
- Grid of info cards (simple view)
- Single info card (detail view)
- Stacked cards (verbose view)
- Summary line (totals)

### Search Command (Future)
Will use:
- Result cards with highlighted matches
- Metric grid for scores
- Summary line for result counts

### Config Command (Future)
Will use:
- Setting cards grouped by category
- Info rows for key-value config
- Success/error cards for feedback
