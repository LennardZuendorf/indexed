"""Convert LSP's default UTF-16 offsets to Python string offsets."""


def utf16_length(text: str) -> int:
    """Count UTF-16 code units without changing the source text."""
    return sum(2 if ord(char) > 0xFFFF else 1 for char in text)


def python_offset(text: str, character: int) -> int:
    """Map a UTF-16 offset to a codepoint boundary, clamped to the line."""
    units = 0
    for index, char in enumerate(text):
        width = 2 if ord(char) > 0xFFFF else 1
        if units + width > character:
            return index
        units += width
    return len(text)
