"""
测试 bash 工具的路径转义修复
"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.utility.bash_tool import BashTool


class TestBashPathNormalization:
    """测试路径标准化功能"""

    @pytest.fixture
    def bash_tool(self):
        """创建 BashTool 实例"""
        return BashTool()

    def test_normalize_double_escaped_paths(self, bash_tool):
        """测试修复双重转义的路径"""
        # 输入：LLM 生成的过度转义路径（4个反斜杠）
        command_with_double_escape = 'dir "D:\\\\溯源\\\\报告模板"'
        normalized = bash_tool._normalize_path_escapes(command_with_double_escape)

        # 期望：标准化为 2 个反斜杠
        assert normalized == 'dir "D:\\溯源\\报告模板"'
        print(f"✅ 双重转义路径已标准化: {normalized}")

    def test_normalize_already_correct_paths(self, bash_tool):
        """测试已经正确的路径不受影响"""
        # 输入：正确的路径（2个反斜杠）
        correct_command = 'dir "D:\\溯源\\报告模板"'
        normalized = bash_tool._normalize_path_escapes(correct_command)

        # 期望：保持不变
        assert normalized == 'dir "D:\\溯源\\报告模板"'
        print(f"✅ 正确路径保持不变: {normalized}")

    def test_normalize_single_quotes_paths(self, bash_tool):
        """测试单引号路径的标准化"""
        # 输入：单引号包裹的过度转义路径
        command = "dir 'D:\\\\溯源\\\\报告模板'"
        normalized = bash_tool._normalize_path_escapes(command)

        # 期望：标准化为 2 个反斜杠
        assert normalized == "dir 'D:\\溯源\\报告模板'"
        print(f"✅ 单引号路径已标准化: {normalized}")

    def test_normalize_multiple_paths(self, bash_tool):
        """测试命令中多个路径的标准化"""
        # 输入：包含多个路径的命令
        command = 'copy "D:\\\\溯源\\\\file1.txt" "D:\\\\溯源\\\\data\\\\file2.txt"'
        normalized = bash_tool._normalize_path_escapes(command)

        # 期望：所有路径都被标准化
        assert normalized == 'copy "D:\\溯源\\file1.txt" "D:\\溯源\\data\\file2.txt"'
        print(f"✅ 多路径命令已标准化: {normalized}")

    def test_no_change_on_non_windows_paths(self, bash_tool):
        """测试非 Windows 路径不受影响"""
        # 输入：Unix 风格路径
        unix_command = 'ls -la /home/user/data'
        normalized = bash_tool._normalize_path_escapes(unix_command)

        # 期望：保持不变
        assert normalized == 'ls -la /home/user/data'
        print(f"✅ Unix 路径不受影响: {normalized}")

    def test_normalize_without_quotes(self, bash_tool):
        """测试不带引号的路径（不匹配模式，应保持不变）"""
        # 输入：不带引号的路径
        command = 'dir D:\\\\溯源\\\\报告模板'
        normalized = bash_tool._normalize_path_escapes(command)

        # 当前实现只处理引号内的路径，不带引号的不处理
        # 这是合理的设计，因为不带引号的路径在 Windows 下通常不合法
        assert normalized == command
        print(f"✅ 不带引号路径保持不变: {normalized}")


class TestBashToolIntegration:
    """集成测试：验证实际执行效果"""

    @pytest.fixture
    def bash_tool(self):
        """创建 BashTool 实例"""
        return BashTool()

    @pytest.mark.asyncio
    async def test_execute_with_double_escaped_path(self, bash_tool):
        """测试执行双重转义路径的命令"""
        # 输入：LLM 可能生成的过度转义路径
        command = 'dir "D:\\\\溯源\\\\报告模板"'

        # 执行命令
        result = await bash_tool.execute(command=command)

        # 验证：命令应该成功执行（如果目录存在）
        # 或者至少路径转义问题已修复
        if result["success"]:
            print(f"✅ 命令执行成功: {result['data']['command']}")
            print(f"   输出: {result['data']['stdout'][:100]}")
        else:
            # 如果目录不存在，至少应该是因为"找不到路径"而不是"路径格式错误"
            print(f"⚠️  命令执行失败: {result['data']['stderr']}")
            # 验证不是路径转义问题导致的失败
            assert "路径无效" not in result.get("data", {}).get("stderr", "")
            assert "path" not in str(result.get("data", {}).get("stderr", "")).lower()

    @pytest.mark.asyncio
    async def test_working_dir_out_of_bounds(self, bash_tool):
        """测试工作目录超出范围的处理"""
        # 输入：尝试使用超出范围的工作目录
        result = await bash_tool.execute(
            command="dir",
            working_dir="D:\\"
        )

        # 验证：应该返回明确的错误信息
        assert result["success"] == False
        assert "超出允许范围" in result["error"]
        assert str(bash_tool.working_dir) in result["error"]
        assert "suggestion" in result["data"]
        print(f"✅ 工作目录越界检测正常: {result['summary']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
