"""Unit tests for Trace and Dialog functionality

Tests TraceManager and dialog handlers.
"""
import pytest
import tempfile
import os
from app.tools.browser.services.trace_manager import TraceManager


class TestTraceManager:
    """Test TraceManager functionality"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for traces"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir

    @pytest.fixture
    def manager(self, temp_dir):
        """Create TraceManager with temporary directory"""
        return TraceManager(trace_dir=temp_dir)

    def test_manager_creation(self, temp_dir):
        """Test creating TraceManager instance"""
        manager = TraceManager(trace_dir=temp_dir)
        assert manager is not None
        assert manager.trace_dir == temp_dir
        assert os.path.exists(temp_dir)

    def test_list_traces_empty(self, manager):
        """Test listing traces when directory is empty"""
        traces = manager.list_traces()
        assert traces == []
        assert isinstance(traces, list)

    def test_list_traces_with_files(self, manager, temp_dir):
        """Test listing traces with existing files"""
        # Create dummy trace files
        trace1 = os.path.join(temp_dir, "trace1.zip")
        trace2 = os.path.join(temp_dir, "trace2.zip")

        with open(trace1, 'w') as f:
            f.write("dummy trace content 1")
        with open(trace2, 'w') as f:
            f.write("dummy trace content 2")

        traces = manager.list_traces()

        assert len(traces) == 2
        assert any(t["filename"] == "trace1.zip" for t in traces)
        assert any(t["filename"] == "trace2.zip" for t in traces)

        # Check structure
        for trace_info in traces:
            assert "filename" in trace_info
            assert "path" in trace_info
            assert "size_kb" in trace_info
            assert "created" in trace_info


class TestDialogHandler:
    """Test dialog handler functionality"""

    def test_dialog_handler_import(self):
        """Test dialog handler can be imported"""
        from app.tools.browser.actions.dialog import handle_dialog
        assert handle_dialog is not None

    def test_unknown_action_raises_error(self):
        """Test unknown action raises ValueError"""
        from app.tools.browser.actions.dialog import handle_dialog

        # We need a minimal manager mock
        class MockManager:
            def get_active_page(self, session_id):
                class MockPage:
                    def on(self, event, handler):
                        pass
                return MockPage()

        mock_manager = MockManager()

        with pytest.raises(ValueError) as exc_info:
            handle_dialog(mock_manager, action="unknown")
        assert "Unknown dialog action" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
