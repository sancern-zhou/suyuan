"""Integration tests for Browser Tool v2.0

Tests end-to-end functionality of all browser tool features.
"""
import pytest
from app.tools.browser.tool import BrowserTool


class TestBrowserToolIntegration:
    """Test browser tool integration"""

    @pytest.fixture
    def browser_tool(self):
        """Create BrowserTool instance"""
        return BrowserTool()

    def test_tool_creation(self, browser_tool):
        """Test browser tool can be created"""
        assert browser_tool is not None
        assert browser_tool.name == "browser"
        assert browser_tool.version == "2.0.0"

    def test_supported_actions(self, browser_tool):
        """Test all v2.0 actions are supported"""
        schema = browser_tool.get_function_schema()
        action_enum = schema["parameters"]["properties"]["action"]["enum"]

        # Original 12 actions
        assert "start" in action_enum
        assert "stop" in action_enum
        assert "status" in action_enum
        assert "tabs" in action_enum
        assert "open" in action_enum
        assert "navigate" in action_enum
        assert "focus" in action_enum
        assert "close" in action_enum
        assert "snapshot" in action_enum
        assert "screenshot" in action_enum
        assert "extract" in action_enum
        assert "act" in action_enum

        # New v2.0 actions
        assert "console" in action_enum
        assert "pdf" in action_enum
        assert "download" in action_enum
        assert "upload" in action_enum
        assert "list_files" in action_enum
        assert "trace" in action_enum
        assert "dialog" in action_enum

        # Total count should be at least 19 (may vary if some actions have aliases)
        assert len(action_enum) >= 19

    def test_action_handlers_registered(self, browser_tool):
        """Test all action handlers are registered"""
        # Test getting handlers for each action
        actions = [
            "start", "stop", "status",
            "tabs", "open", "navigate", "focus", "close",
            "snapshot", "screenshot", "extract", "act",
            "console", "pdf",
            "download", "upload", "list_files",
            "trace", "dialog"
        ]

        for action in actions:
            try:
                handler = browser_tool._get_action_handler(action)
                assert handler is not None
                assert callable(handler)
            except ValueError as e:
                pytest.fail(f"Failed to get handler for action '{action}': {e}")

    def test_v2_parameters_in_schema(self, browser_tool):
        """Test v2.0 parameters are in function schema"""
        schema = browser_tool.get_function_schema()
        properties = schema["parameters"]["properties"]

        # Original parameters
        assert "url" in properties
        assert "selector" in properties
        assert "text" in properties
        assert "click" in properties
        assert "scroll" in properties
        assert "timeout" in properties
        assert "session_id" in properties

        # New v2.0 parameters
        assert "format" in properties
        assert "max_refs" in properties
        assert "interactive_only" in properties
        assert "console_action" in properties
        assert "pdf_action" in properties
        assert "file_path" in properties
        assert "trace_action" in properties
        assert "dialog_action" in properties

    def test_snapshot_format_values(self, browser_tool):
        """Test snapshot format parameter has correct values"""
        schema = browser_tool.get_function_schema()
        format_param = schema["parameters"]["properties"]["format"]
        assert format_param["type"] == "string"
        assert set(format_param["enum"]) == {"text", "ai", "aria"}

    def test_tool_description_mentions_v2(self, browser_tool):
        """Test tool description mentions v2.0 features"""
        description = browser_tool.description
        assert "v2.0" in description or "2.0" in description
        assert "console" in description
        assert "pdf" in description
        assert "download" in description
        assert "trace" in description


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
