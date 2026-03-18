"""
Test suite for browser wait conditions functionality.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from app.tools.browser.actions.waiting import handle_wait, _normalize_timeout
from app.tools.browser.config import config


def _setup_mock_config(mock_config):
    """Helper to setup mock config with all required values"""
    mock_config.WAIT_FN_ENABLED = False
    mock_config.WAIT_DEFAULT_TIMEOUT = 20000
    mock_config.WAIT_MIN_TIMEOUT = 500
    mock_config.WAIT_MAX_TIMEOUT = 120000
    return mock_config


class TestNormalizeTimeout:
    """Test timeout normalization"""

    def test_default_timeout(self):
        """Test default timeout when None is provided"""
        result = _normalize_timeout(None)
        assert result == 20000

    def test_min_timeout_bounds(self):
        """Test minimum timeout is enforced"""
        result = _normalize_timeout(100)
        assert result == 500

    def test_max_timeout_bounds(self):
        """Test maximum timeout is enforced"""
        result = _normalize_timeout(150000)
        assert result == 120000

    def test_valid_timeout(self):
        """Test valid timeout is returned as-is"""
        result = _normalize_timeout(10000)
        assert result == 10000

    def test_boundary_values(self):
        """Test boundary values"""
        assert _normalize_timeout(500) == 500
        assert _normalize_timeout(120000) == 120000


class TestWaitTimeMs:
    """Test time_ms wait condition"""

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_time_ms(self, mock_config):
        """Test waiting for fixed time"""
        _setup_mock_config(mock_config)

        # Mock manager and page
        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        result = handle_wait(manager, time_ms=1000)

        # Verify wait_for_timeout was called
        page.wait_for_timeout.assert_called_once_with(1000)
        assert "timeMs(1000ms)" in result["conditions_applied"]

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_time_ms_negative(self, mock_config):
        """Test waiting with negative time (should be clamped to 0)"""
        _setup_mock_config(mock_config)

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        result = handle_wait(manager, time_ms=-500)

        # Verify wait_for_timeout was called with 0 (max(0, -500))
        page.wait_for_timeout.assert_called_once_with(0)
        assert result["success"] is True


class TestWaitText:
    """Test text wait conditions"""

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_text_appear(self, mock_config):
        """Test waiting for text to appear"""
        _setup_mock_config(mock_config)

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        # Mock get_by_text chain
        text_locator = Mock()
        page.get_by_text.return_value.first = text_locator

        result = handle_wait(manager, text="Login Success")

        # Verify text wait was called
        page.get_by_text.assert_called_once_with("Login Success")
        text_locator.wait_for.assert_called_once_with(state="visible", timeout=20000)
        assert "text('Login Success')" in result["conditions_applied"]

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_text_gone(self, mock_config):
        """Test waiting for text to disappear"""
        _setup_mock_config(mock_config)

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        # Mock get_by_text chain
        text_locator = Mock()
        page.get_by_text.return_value.first = text_locator

        result = handle_wait(manager, text_gone="Loading...")

        # Verify text wait was called
        page.get_by_text.assert_called_once_with("Loading...")
        text_locator.wait_for.assert_called_once_with(state="hidden", timeout=20000)
        assert "textGone('Loading...')" in result["conditions_applied"]


class TestWaitSelector:
    """Test selector wait condition"""

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_selector(self, mock_config):
        """Test waiting for element visibility"""
        _setup_mock_config(mock_config)

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        # Mock locator chain
        element_locator = Mock()
        page.locator.return_value.first = element_locator

        result = handle_wait(manager, selector=".dashboard-panel")

        # Verify selector wait was called
        page.locator.assert_called_once_with(".dashboard-panel")
        element_locator.wait_for.assert_called_once_with(state="visible", timeout=20000)
        assert "selector('.dashboard-panel')" in result["conditions_applied"]


class TestWaitUrl:
    """Test URL wait condition"""

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_url(self, mock_config):
        """Test waiting for URL change"""
        _setup_mock_config(mock_config)

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        result = handle_wait(manager, url="*dashboard*")

        # Verify URL wait was called
        page.wait_for_url.assert_called_once_with("*dashboard*", timeout=20000)
        assert "url('*dashboard*')" in result["conditions_applied"]


class TestWaitLoadState:
    """Test load state wait condition"""

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_load_state_valid(self, mock_config):
        """Test waiting for valid load states"""
        _setup_mock_config(mock_config)

        for state in ["load", "domcontentloaded", "networkidle"]:
            manager = Mock()
            page = Mock()
            manager.get_active_page.return_value = page

            result = handle_wait(manager, load_state=state)

            # Verify load state wait was called
            page.wait_for_load_state.assert_called_once_with(state, timeout=20000)
            assert f"loadState('{state}')" in result["conditions_applied"]

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_load_state_invalid(self, mock_config):
        """Test waiting for invalid load state raises error"""
        _setup_mock_config(mock_config)

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        with pytest.raises(RuntimeError, match="Invalid loadState"):
            handle_wait(manager, load_state="invalid_state")


class TestWaitMultipleConditions:
    """Test multiple wait conditions executed sequentially"""

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_multiple_conditions(self, mock_config):
        """Test waiting for multiple conditions"""
        _setup_mock_config(mock_config)

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        # Mock chains
        text_locator = Mock()
        page.get_by_text.return_value.first = text_locator
        element_locator = Mock()
        page.locator.return_value.first = element_locator

        result = handle_wait(
            manager,
            time_ms=1000,
            text="Loaded",
            selector=".panel"
        )

        # Verify all conditions were executed
        assert page.wait_for_timeout.called
        assert page.get_by_text.called
        assert page.locator.called
        assert len(result["conditions_applied"]) == 3


class TestWaitNoCondition:
    """Test error when no condition is specified"""

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_no_condition_error(self, mock_config):
        """Test that error is raised when no condition is specified"""
        mock_config.WAIT_FN_ENABLED = False
        mock_config.WAIT_DEFAULT_TIMEOUT = 20000
        mock_config.WAIT_MIN_TIMEOUT = 500
        mock_config.WAIT_MAX_TIMEOUT = 120000

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        with pytest.raises(RuntimeError, match="At least one wait condition"):
            handle_wait(manager)


class TestWaitJavaScriptFunction:
    """Test JavaScript function wait condition"""

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_fn_disabled(self, mock_config):
        """Test that fn wait raises error when disabled"""
        _setup_mock_config(mock_config)

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        with pytest.raises(RuntimeError, match="wait fn is disabled by config"):
            handle_wait(manager, fn="() => true")

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_fn_enabled(self, mock_config):
        """Test that fn wait works when enabled"""
        _setup_mock_config(mock_config)
        mock_config.WAIT_FN_ENABLED = True

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        fn_body = "() => document.title.includes('Done')"
        result = handle_wait(manager, fn=fn_body)

        # Verify fn wait was called
        page.wait_for_function.assert_called_once_with(fn_body, timeout=20000)
        assert result["success"] is True


class TestWaitTimeoutErrors:
    """Test timeout error handling"""

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_timeout_error(self, mock_config):
        """Test that timeout error is properly formatted"""
        _setup_mock_config(mock_config)

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        # Mock timeout error
        page.locator.return_value.first.wait_for.side_effect = Exception("Timeout 20000ms exceeded")

        with pytest.raises(RuntimeError, match="Wait timeout after 20000ms"):
            handle_wait(manager, selector=".timeout-element")

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_strict_mode_error(self, mock_config):
        """Test that strict mode violation is properly formatted"""
        _setup_mock_config(mock_config)

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        # Mock strict mode error
        page.locator.return_value.first.wait_for.side_effect = Exception("strict mode violation")

        with pytest.raises(RuntimeError, match="Multiple elements matched"):
            handle_wait(manager, selector=".multiple-elements")


class TestWaitCustomTimeout:
    """Test custom timeout handling"""

    @patch('app.tools.browser.actions.waiting.config')
    def test_wait_custom_timeout(self, mock_config):
        """Test custom timeout is applied"""
        mock_config.WAIT_FN_ENABLED = False
        mock_config.WAIT_DEFAULT_TIMEOUT = 20000
        mock_config.WAIT_MIN_TIMEOUT = 500
        mock_config.WAIT_MAX_TIMEOUT = 120000

        manager = Mock()
        page = Mock()
        manager.get_active_page.return_value = page

        element_locator = Mock()
        page.locator.return_value.first = element_locator

        result = handle_wait(manager, selector=".element", timeout=5000)

        # Verify custom timeout was used
        element_locator.wait_for.assert_called_once_with(state="visible", timeout=5000)
        assert result["timeout_ms"] == 5000


class TestGetWaitSummary:
    """Test wait summary generation"""

    def test_get_wait_summary(self):
        """Test summary generation"""
        from app.tools.browser.actions.waiting import get_wait_summary

        result = {
            "conditions_applied": ["text('Loaded')", "selector('.panel')"],
            "timeout_ms": 10000
        }

        summary = get_wait_summary(result)

        assert "2 condition" in summary
        assert "10000ms" in summary
        assert "text('Loaded')" in summary
        assert "selector('.panel')" in summary

    def test_get_wait_summary_no_conditions(self):
        """Test summary with no conditions"""
        from app.tools.browser.actions.waiting import get_wait_summary

        result = {}
        summary = get_wait_summary(result)

        assert "Wait operation completed" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
