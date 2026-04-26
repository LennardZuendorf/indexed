"""Sample Python module for testing code chunking."""

from typing import List


class Calculator:
    """A simple calculator class."""

    def __init__(self, name: str = "calc") -> None:
        self.name = name
        self.history: List[float] = []

    def add(self, a: float, b: float) -> float:
        """Add two numbers."""
        result = a + b
        self.history.append(result)
        return result

    def multiply(self, a: float, b: float) -> float:
        """Multiply two numbers."""
        result = a * b
        self.history.append(result)
        return result


def standalone_function(x: int) -> int:
    """A standalone function outside any class."""
    return x * 2 + 1


CONSTANT_VALUE = 42
