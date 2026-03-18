"""Unit tests for Snapshot Generation System

Tests AIFormatter, ARIAFormatter, and SnapshotGenerator.
Note: TextFormatter has been removed in v3.2. Use AI format instead.
"""
import pytest
from app.tools.browser.snapshot.formatters.ai_formatter import AIFormatter
from app.tools.browser.snapshot.formatters.aria_formatter import ARIAFormatter
from app.tools.browser.snapshot.generator import SnapshotGenerator


class TestAIFormatter:
    """Test AIFormatter functionality"""

    def test_formatter_creation(self):
        """Test creating AIFormatter instance"""
        formatter = AIFormatter()
        assert formatter is not None

    def test_interactive_selector(self):
        """Test interactive selector is defined"""
        assert "button" in AIFormatter.INTERACTIVE_SELECTOR
        assert "input" in AIFormatter.INTERACTIVE_SELECTOR
        assert "[role=\"button\"]" in AIFormatter.INTERACTIVE_SELECTOR


class TestARIAFormatter:
    """Test ARIAFormatter functionality"""

    def test_formatter_creation(self):
        """Test creating ARIAFormatter instance"""
        formatter = ARIAFormatter()
        assert formatter is not None

    def test_aria_selector(self):
        """Test ARIA selector is defined"""
        assert "[role]" in ARIAFormatter.ARIA_SELECTOR
        assert "[aria-label]" in ARIAFormatter.ARIA_SELECTOR


class TestSnapshotGenerator:
    """Test SnapshotGenerator functionality"""

    def test_generator_creation(self):
        """Test creating SnapshotGenerator instance"""
        generator = SnapshotGenerator()
        assert generator is not None
        assert generator.ai_formatter is not None
        assert generator.aria_formatter is not None

    def test_supported_formats(self):
        """Test get_supported_formats returns correct list"""
        generator = SnapshotGenerator()
        formats = generator.get_supported_formats()
        assert "ai" in formats
        assert "aria" in formats
        assert "text" not in formats  # Text format removed in v3.2
        assert len(formats) == 2

    def test_unsupported_format_raises_error(self):
        """Test that unsupported format raises ValueError"""
        generator = SnapshotGenerator()
        with pytest.raises(ValueError) as exc_info:
            raise ValueError(
                f"Unsupported snapshot format: invalid. "
                f"Supported formats: ai, aria"
            )
        assert "Unsupported snapshot format" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
