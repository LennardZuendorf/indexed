"""ASCII art banner for Indexed MCP server.

Provides a colored ASCII art banner that displays when the MCP server starts.
Uses Rich library for gradient coloring and art library for solid Unicode block characters.
"""

from art import text2art
from rich.console import Console
from rich.text import Text


def print_indexed_banner() -> None:
    """Display the INDEXED ASCII art banner with gradient coloring.
    
    Prints a colored banner to stderr using Rich's Console. The banner uses
    a gradient from dark blue through lighter blue to cyan, creating a modern
    tech aesthetic.
    
    The banner uses the art library's tarty1 font to generate solid Unicode
    block characters (█), and is displayed left-aligned.
    """
    console = Console(stderr=True)
    
    # Generate ASCII art with art library using 'tarty1' font for solid Unicode blocks
    ascii_art = text2art("INDEXED", font="tarty1")
    
    # Split the ASCII art into lines
    lines = ascii_art.strip().split('\n')

    # Create gradient colors from moderately dark blue -> blue -> teal -> cyan
    # Using a progression of color codes for the gradient effect
    colors = [
        "#005087",  # Dark blue (but lighter, more visible)
        "#1565A3",  # Blue
        "#2581C4",  # Medium blue
        "#21A5CF",  # Lighter blue-teal
        "#31CFCF",  # Teal-cyan
        "#00FFFF",  # Cyan (end)
    ]

    # Apply gradient across all lines from top to bottom
    colored_text = Text()
    num_lines = len(lines)

    for line_idx, line in enumerate(lines):
        # Calculate color progression for this line
        # First line gets dark blue, last line gets cyan
        if num_lines > 1:
            line_position = line_idx / (num_lines - 1)
        else:
            line_position = 0.5
        
        # Determine which color to use for this line
        color_float = line_position * (len(colors) - 1)
        color_idx = int(color_float)
        color_idx = min(color_idx, len(colors) - 1)
        
        # Apply gradient only to solid block characters (█), not box-drawing chars
        # This preserves the gray/white appearance of structural characters
        for char in line:
            if char == '█':  # Solid block character
                colored_text.append(char, style=colors[color_idx])
            else:  # Box-drawing and other characters - no color
                colored_text.append(char)
        
        # Add newline after each line except the last
        if line_idx < len(lines) - 1:
            colored_text.append('\n')

    # Print with spacing, left-aligned
    console.print()
    console.print(colored_text)
    console.print()
