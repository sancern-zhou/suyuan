"""
测试 EditFile 工具

验证功能：
1. 基础替换功能
2. 唯一性检查
3. 全量替换（replace_all）
4. 错误处理（文件不存在、old_string不存在、多次出现等）
"""
import pytest
import tempfile
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.tools.utility.edit_file_tool import EditFileTool


class TestEditFileTool:
    """EditFile 工具测试"""

    @pytest.fixture
    def edit_tool(self):
        """创建 EditFileTool 实例"""
        return EditFileTool()

    @pytest.fixture
    def temp_file(self):
        """创建临时测试文件（在项目工作目录内）"""
        # 使用项目根目录下的临时文件（避免工作目录限制）
        test_file = project_root / "tests" / "temp_test_file.txt"
        test_file.write_text("Hello World\nThis is a test.\nHello again!")
        yield test_file
        # 清理
        if test_file.exists():
            test_file.unlink()

    @pytest.mark.asyncio
    async def test_basic_replace(self, edit_tool, temp_file):
        """测试基础替换功能"""
        result = await edit_tool.execute(
            file_path=str(temp_file),
            old_string="Hello World",
            new_string="Hi Universe"
        )

        assert result["success"] is True
        assert result["data"]["changes"] == 1

        # 验证文件内容
        content = temp_file.read_text()
        assert "Hi Universe" in content
        assert "Hello World" not in content
        assert "Hello again" in content  # 不影响第二个 Hello

    @pytest.mark.asyncio
    async def test_multiline_replace(self, edit_tool, temp_file):
        """测试多行替换"""
        result = await edit_tool.execute(
            file_path=str(temp_file),
            old_string="Hello World\nThis is a test.",
            new_string="Greetings\nThis is a TEST."
        )

        assert result["success"] is True
        content = temp_file.read_text()
        assert "Greetings" in content
        assert "This is a TEST." in content

    @pytest.mark.asyncio
    async def test_uniqueness_check(self, edit_tool, temp_file):
        """测试唯一性检查（多次出现时应该失败）"""
        # 文件中有两个 "Hello"
        result = await edit_tool.execute(
            file_path=str(temp_file),
            old_string="Hello",
            new_string="Hi"
        )

        assert result["success"] is False
        assert "出现了 2 次" in result["error"]
        assert result["data"]["occurrence_count"] == 2

    @pytest.mark.asyncio
    async def test_replace_all(self, edit_tool, temp_file):
        """测试全量替换"""
        result = await edit_tool.execute(
            file_path=str(temp_file),
            old_string="Hello",
            new_string="Hi",
            replace_all=True
        )

        assert result["success"] is True
        assert result["data"]["changes"] == 2

        content = temp_file.read_text()
        assert content.count("Hi") == 2
        assert "Hello" not in content

    @pytest.mark.asyncio
    async def test_old_string_not_found(self, edit_tool, temp_file):
        """测试 old_string 不存在的情况"""
        result = await edit_tool.execute(
            file_path=str(temp_file),
            old_string="NonExistent",
            new_string="Something"
        )

        assert result["success"] is False
        assert "不存在" in result["error"]
        assert "file_preview" in result["data"]

    @pytest.mark.asyncio
    async def test_file_not_found(self, edit_tool):
        """测试文件不存在"""
        result = await edit_tool.execute(
            file_path="/nonexistent/file.txt",
            old_string="old",
            new_string="new"
        )

        assert result["success"] is False
        assert "不存在" in result["error"]

    @pytest.mark.asyncio
    async def test_code_file_edit(self, edit_tool):
        """测试编辑代码文件（包含缩进）"""
        code_file = project_root / "tests" / "temp_code_file.py"
        code_file.write_text("""def old_function():
    return "old"

def main():
    result = old_function()
    print(result)
""")

        try:
            result = await edit_tool.execute(
                file_path=str(code_file),
                old_string='def old_function():\n    return "old"',
                new_string='def new_function():\n    return "new"'
            )

            assert result["success"] is True

            content = code_file.read_text()
            assert "def new_function()" in content
            assert "def old_function()" not in content
        finally:
            if code_file.exists():
                code_file.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
