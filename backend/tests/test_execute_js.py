"""测试execute_js功能

验证execute_js action能够正确执行JavaScript代码
"""
import pytest
from unittest.mock import Mock, MagicMock, patch


class TestExecuteJS:
    """测试execute_js action"""

    def test_handle_execute_js_basic(self):
        """测试基本JavaScript执行"""
        from app.tools.browser.actions.execute_js import handle_execute_js

        # 创建模拟manager和page
        mock_manager = Mock()
        mock_page = Mock()
        mock_manager.get_active_page.return_value = mock_page

        # 模拟evaluate返回值
        mock_page.evaluate.return_value = "Click successful"

        # 执行
        result = handle_execute_js(
            mock_manager,
            code='document.querySelector("a").click()',
            session_id="test"
        )

        # 验证
        assert result["code"] == 'document.querySelector("a").click()'
        assert result["result"] == "Click successful"
        assert result["type"] == "string"
        mock_page.evaluate.assert_called_once()
        mock_manager.get_active_page.assert_called_once_with("test")

    def test_handle_execute_js_number_result(self):
        """测试返回数字结果"""
        from app.tools.browser.actions.execute_js import handle_execute_js

        mock_manager = Mock()
        mock_page = Mock()
        mock_manager.get_active_page.return_value = mock_page
        mock_page.evaluate.return_value = 42

        result = handle_execute_js(mock_manager, code="1 + 41")

        assert result["result"] == 42
        assert result["type"] == "number"

    def test_handle_execute_js_boolean_result(self):
        """测试返回布尔结果"""
        from app.tools.browser.actions.execute_js import handle_execute_js

        mock_manager = Mock()
        mock_page = Mock()
        mock_manager.get_active_page.return_value = mock_page
        mock_page.evaluate.return_value = True

        result = handle_execute_js(mock_manager, code="true")

        assert result["result"] is True
        assert result["type"] == "boolean"

    def test_handle_execute_js_null_result(self):
        """测试返回null结果"""
        from app.tools.browser.actions.execute_js import handle_execute_js

        mock_manager = Mock()
        mock_page = Mock()
        mock_manager.get_active_page.return_value = mock_page
        mock_page.evaluate.return_value = None

        result = handle_execute_js(mock_manager, code="null")

        assert result["result"] is None
        assert result["type"] == "null"

    def test_handle_execute_js_array_result(self):
        """测试返回数组结果"""
        from app.tools.browser.actions.execute_js import handle_execute_js

        mock_manager = Mock()
        mock_page = Mock()
        mock_manager.get_active_page.return_value = mock_page
        mock_page.evaluate.return_value = [1, 2, 3]

        result = handle_execute_js(mock_manager, code="[1, 2, 3]")

        assert result["result"] == [1, 2, 3]
        assert result["type"] == "array"

    def test_handle_execute_js_object_result(self):
        """测试返回对象结果"""
        from app.tools.browser.actions.execute_js import handle_execute_js

        mock_manager = Mock()
        mock_page = Mock()
        mock_manager.get_active_page.return_value = mock_page
        mock_page.evaluate.return_value = {"key": "value"}

        result = handle_execute_js(mock_manager, code='({"key": "value"})')

        assert result["result"] == {"key": "value"}
        assert result["type"] == "object"

    def test_handle_execute_js_error(self):
        """测试JavaScript执行错误"""
        from app.tools.browser.actions.execute_js import handle_execute_js

        mock_manager = Mock()
        mock_page = Mock()
        mock_manager.get_active_page.return_value = mock_page
        mock_page.evaluate.side_effect = Exception("SyntaxError")

        result = handle_execute_js(mock_manager, code="invalid javascript")

        assert result["type"] == "error"
        assert "error" in result
        assert result["result"] is None

    def test_handle_execute_js_click_element(self):
        """测试使用JavaScript点击元素"""
        from app.tools.browser.actions.execute_js import handle_execute_js

        mock_manager = Mock()
        mock_page = Mock()
        mock_manager.get_active_page.return_value = mock_page
        mock_page.evaluate.return_value = None  # click()返回undefined

        result = handle_execute_js(
            mock_manager,
            code='document.querySelector("a:has-text(\\"实时预览\\")").click()'
        )

        assert result["type"] == "null"
        # 验证代码被正确包装
        args = mock_page.evaluate.call_args
        assert "document.querySelector" in str(args)

    def test_handle_execute_js_remove_dialogs(self):
        """测试移除对话框"""
        from app.tools.browser.actions.execute_js import handle_execute_js

        mock_manager = Mock()
        mock_page = Mock()
        mock_manager.get_active_page.return_value = mock_page
        mock_page.evaluate.return_value = 5  # 删除了5个对话框

        result = handle_execute_js(
            mock_manager,
            code='document.querySelectorAll(".el-dialog").forEach(d=>d.remove())'
        )

        assert result["type"] == "number"
        assert result["result"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
