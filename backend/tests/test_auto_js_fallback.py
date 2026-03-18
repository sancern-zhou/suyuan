"""测试JavaScript自动重试功能

验证当元素被阻挡时，系统自动使用JavaScript重试
"""
import pytest
from unittest.mock import Mock, MagicMock, patch


class TestAutoJSFallback:
    """测试自动JavaScript重试机制"""

    def test_convert_has_text_selector(self):
        """测试将Playwright的:has-text选择器转换为JavaScript"""
        from app.tools.browser.actions.interaction import _convert_selector_to_js

        js_code = _convert_selector_to_js('a:has-text("实时预览")')

        # 验证生成的JavaScript代码包含正确的逻辑
        assert 'querySelectorAll' in js_code
        assert 'includes' in js_code
        assert '实时预览' in js_code
        assert 'el.click()' in js_code

    def test_convert_text_selector(self):
        """测试text=选择器转换"""
        from app.tools.browser.actions.interaction import _convert_selector_to_js

        js_code = _convert_selector_to_js('text="Login"')

        # 验证生成的JavaScript代码
        assert 'querySelectorAll' in js_code
        assert "textContent.trim() === 'Login'" in js_code

    def test_convert_standard_selector(self):
        """测试标准CSS选择器转换"""
        from app.tools.browser.actions.interaction import _convert_selector_to_js

        js_code = _convert_selector_to_js('#my-button')

        # 验证使用了querySelector
        assert 'querySelector' in js_code
        assert '#my-button' in js_code

    def test_try_js_click_with_has_text_selector(self):
        """测试使用:has-text选择器的JavaScript点击"""
        from app.tools.browser.actions.interaction import _try_js_click

        mock_page = Mock()
        # 模拟成功的JavaScript执行
        mock_page.evaluate.return_value = {"success": True}

        result = _try_js_click(mock_page, selector='a:has-text("实时预览")')

        assert result["success"] is True
        assert result["error"] is None
        # 验证evaluate被调用
        mock_page.evaluate.assert_called_once()

    def test_try_js_click_with_selector(self):
        """测试使用selector的JavaScript点击"""
        from app.tools.browser.actions.interaction import _try_js_click

        mock_page = Mock()
        # 模拟成功的JavaScript执行
        mock_page.evaluate.return_value = {"success": True}

        result = _try_js_click(mock_page, selector="a:has-text('Click me')")

        assert result["success"] is True
        assert result["error"] is None
        mock_page.evaluate.assert_called_once()

    def test_try_js_click_element_not_found(self):
        """测试JavaScript找不到元素"""
        from app.tools.browser.actions.interaction import _try_js_click

        mock_page = Mock()
        mock_page.evaluate.return_value = {"success": False, "error": "Element not found"}

        result = _try_js_click(mock_page, selector="button:has-text('Not exist')")

        assert result["success"] is False
        assert "Element not found" in result["error"]

    def test_try_js_click_javascript_error(self):
        """测试JavaScript执行错误"""
        from app.tools.browser.actions.interaction import _try_js_click

        mock_page = Mock()
        mock_page.evaluate.side_effect = Exception("Syntax error")

        result = _try_js_click(mock_page, selector="button")

        assert result["success"] is False
        assert "Syntax error" in result["error"]

    def test_handle_act_auto_fallback_on_blocked(self):
        """测试点击被阻挡时自动使用JavaScript重试"""
        from app.tools.browser.actions.interaction import handle_act

        mock_manager = Mock()
        mock_page = Mock()
        mock_manager.get_active_page.return_value = mock_page

        # 模拟locator第一次点击失败（被阻挡）
        mock_locator = Mock()
        mock_locator.click.side_effect = Exception("Timeout: Element is blocked")

        # 模拟JavaScript重试成功
        mock_page.evaluate.return_value = {"success": True}

        # Mock _get_locator
        with patch('app.tools.browser.actions.interaction._get_locator', return_value=mock_locator):
            result = handle_act(
                mock_manager,
                selector="a:has-text('实时预览')",
                click=True
            )

        # 验证返回成功结果
        assert result["action"] == "click"
        assert "JavaScript fallback" in result["result"]
        assert result["ref"] == "N/A"

        # 验证JavaScript被执行
        assert mock_page.evaluate.call_count >= 1

    def test_handle_act_both_methods_fail(self):
        """测试正常点击和JavaScript都失败的情况"""
        from app.tools.browser.actions.interaction import handle_act

        mock_manager = Mock()
        mock_page = Mock()
        mock_manager.get_active_page.return_value = mock_page

        # 模拟locator第一次点击失败（被阻挡）
        mock_locator = Mock()
        mock_locator.click.side_effect = Exception("Timeout: Element is blocked")

        # 模拟JavaScript重试也失败
        mock_page.evaluate.return_value = {"success": False, "error": "Still blocked"}

        # Mock _get_locator and _detect_obstacles
        with patch('app.tools.browser.actions.interaction._get_locator', return_value=mock_locator):
            with patch('app.tools.browser.actions.interaction._detect_obstacles', return_value={'dialogs': 1}):
                with patch('app.tools.browser.actions.interaction._take_screenshot_for_analysis', return_value=None):
                    # 应该抛出RuntimeError
                    with pytest.raises(RuntimeError) as exc_info:
                        handle_act(
                            mock_manager,
                            selector="button",
                            click=True
                        )

                    # 验证错误消息包含JavaScript失败信息
                    error_msg = str(exc_info.value)
                    assert "JavaScript fallback also failed" in error_msg

    def test_try_js_click_no_params(self):
        """测试没有提供selector或ref"""
        from app.tools.browser.actions.interaction import _try_js_click

        mock_page = Mock()
        result = _try_js_click(mock_page)

        assert result["success"] is False
        assert "No selector or ref provided" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
