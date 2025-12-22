"""Comprehensive tests for safe_getattr utility module."""

from unittest.mock import MagicMock
import pytest

from utils.safe_getattr import safe_str_attr


class TestSafeStrAttr:
    """Test safe_str_attr function."""

    def test_returns_string_attribute(self):
        """Should return string attribute when it exists."""

        class TestObj:
            name = "test_value"

        result = safe_str_attr(TestObj(), "name", "default")
        assert result == "test_value"

    def test_returns_default_when_attribute_missing(self):
        """Should return default when attribute doesn't exist."""

        class TestObj:
            pass

        result = safe_str_attr(TestObj(), "missing", "default_value")
        assert result == "default_value"

    def test_returns_default_when_attribute_not_string(self):
        """Should return default when attribute exists but is not a string."""

        class TestObj:
            number = 42
            boolean = True
            none_val = None

        assert safe_str_attr(TestObj(), "number", "default") == "default"
        assert safe_str_attr(TestObj(), "boolean", "default") == "default"
        assert safe_str_attr(TestObj(), "none_val", "default") == "default"

    def test_handles_magic_mock(self):
        """Should handle MagicMock objects safely."""
        mock_obj = MagicMock()
        mock_obj.some_attr = MagicMock()

        result = safe_str_attr(mock_obj, "some_attr", "default")
        # MagicMock is not a string, should return default
        assert result == "default"

    def test_returns_mock_string_attribute(self):
        """Should return string from mock when it's actually a string."""
        mock_obj = MagicMock()
        mock_obj.url = "https://example.com"

        result = safe_str_attr(mock_obj, "url", "default")
        assert result == "https://example.com"

    def test_handles_property(self):
        """Should handle properties that return strings."""

        class TestObj:
            @property
            def computed(self):
                return "computed_value"

        result = safe_str_attr(TestObj(), "computed", "default")
        assert result == "computed_value"

    def test_handles_property_returning_non_string(self):
        """Should return default when property returns non-string."""

        class TestObj:
            @property
            def computed(self):
                return 123

        result = safe_str_attr(TestObj(), "computed", "default")
        assert result == "default"

    def test_handles_empty_string(self):
        """Should return empty string if that's the attribute value."""

        class TestObj:
            empty = ""

        result = safe_str_attr(TestObj(), "empty", "default")
        assert result == ""

    def test_handles_none_object(self):
        """Should handle None object gracefully."""
        result = safe_str_attr(None, "anything", "default")
        assert result == "default"

    def test_handles_dict_like_object(self):
        """Should work with dict-like objects."""
        obj = {"name": "value"}
        # getattr on dict won't find key, should return default
        result = safe_str_attr(obj, "name", "default")
        assert result == "default"

    def test_handles_class_attribute(self):
        """Should access class attributes, not just instance attributes."""

        class TestClass:
            class_attr = "class_value"

        result = safe_str_attr(TestClass(), "class_attr", "default")
        assert result == "class_value"

    def test_different_default_values(self):
        """Should respect different default values."""

        class TestObj:
            pass

        assert safe_str_attr(TestObj(), "missing", "default1") == "default1"
        assert safe_str_attr(TestObj(), "missing", "default2") == "default2"
        assert safe_str_attr(TestObj(), "missing", "") == ""


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_handles_attribute_with_side_effects(self):
        """Should handle attributes that have side effects."""

        class TestObj:
            call_count = 0

            @property
            def side_effect_prop(self):
                TestObj.call_count += 1
                return "value"

        obj = TestObj()
        result = safe_str_attr(obj, "side_effect_prop", "default")
        assert result == "value"
        assert TestObj.call_count == 1

    def test_handles_property_raising_exception(self):
        """Should handle properties that raise exceptions."""

        class TestObj:
            @property
            def broken(self):
                raise RuntimeError("Property error")

        # getattr will raise the exception
        with pytest.raises(RuntimeError):
            safe_str_attr(TestObj(), "broken", "default")

    def test_handles_callable_attribute(self):
        """Should return default for callable attributes (methods)."""

        class TestObj:
            def method(self):
                return "method result"

        result = safe_str_attr(TestObj(), "method", "default")
        # Methods are not strings
        assert result == "default"

    def test_handles_special_attributes(self):
        """Should handle special (__X__) attributes."""

        class TestObj:
            __special__ = "special_value"

        result = safe_str_attr(TestObj(), "__special__", "default")
        assert result == "special_value"

    def test_handles_unicode_strings(self):
        """Should handle unicode strings correctly."""

        class TestObj:
            unicode_attr = "Hello 世界 🌍"

        result = safe_str_attr(TestObj(), "unicode_attr", "default")
        assert result == "Hello 世界 🌍"

    def test_handles_multiline_strings(self):
        """Should handle multiline strings."""

        class TestObj:
            multiline = "line1\nline2\nline3"

        result = safe_str_attr(TestObj(), "multiline", "default")
        assert result == "line1\nline2\nline3"

    def test_mock_spec_object(self):
        """Should handle MagicMock with spec."""

        class RealClass:
            url: str

        mock = MagicMock(spec=RealClass)
        mock.url = "https://example.com"

        result = safe_str_attr(mock, "url", "default")
        assert result == "https://example.com"

    def test_nested_attribute_access(self):
        """Should only access direct attributes, not nested."""

        class Inner:
            value = "inner_value"

        class Outer:
            inner = Inner()

        # Can't access nested with single call
        result = safe_str_attr(Outer(), "inner.value", "default")
        assert result == "default"

        # But can access first level
        result = safe_str_attr(Outer(), "inner", "default")
        # inner is not a string, should return default
        assert result == "default"

    def test_bytes_attribute_returns_default(self):
        """Should return default for bytes attributes."""

        class TestObj:
            bytes_attr = b"bytes value"

        result = safe_str_attr(TestObj(), "bytes_attr", "default")
        # bytes is not str
        assert result == "default"

    def test_list_attribute_returns_default(self):
        """Should return default for list attributes."""

        class TestObj:
            list_attr = ["item1", "item2"]

        result = safe_str_attr(TestObj(), "list_attr", "default")
        assert result == "default"

    def test_works_with_dataclass(self):
        """Should work with dataclass instances."""
        from dataclasses import dataclass

        @dataclass
        class Config:
            url: str
            port: int

        config = Config(url="https://example.com", port=8080)

        assert safe_str_attr(config, "url", "default") == "https://example.com"
        assert safe_str_attr(config, "port", "default") == "default"

    def test_works_with_named_tuple(self):
        """Should work with namedtuple instances."""
        from collections import namedtuple

        Config = namedtuple("Config", ["url", "port"])
        config = Config(url="https://example.com", port=8080)

        assert safe_str_attr(config, "url", "default") == "https://example.com"
        assert safe_str_attr(config, "port", "default") == "default"
