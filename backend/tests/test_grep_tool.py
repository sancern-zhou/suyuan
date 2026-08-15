"""
测试 Grep 工具

验证功能：
1. 基础内容搜索（content 模式）
2. 文件路径模式（files_with_matches）
3. 统计模式（count）
4. 文件类型过滤（type）
5. 上下文行（context / A / B）
6. 大小写不敏感
7. 错误处理（无效正则、路径不存在）
8. head_limit 限制
"""
import pytest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.tools.utility.grep_tool import GrepTool


class TestGrepTool:

    @pytest.fixture
    def grep(self):
        return GrepTool()

    @pytest.fixture(autouse=True)
    def test_files(self):
        """在项目测试目录创建临时测试文件"""
        test_dir = project_root / "tests" / "grep_test_data"
        test_dir.mkdir(exist_ok=True)

        (test_dir / "alpha.py").write_text(
            "class AlphaAgent:\n    def execute(self):\n        return 'alpha'\n\nHELLO = 'world'\n",
            encoding="utf-8"
        )
        (test_dir / "beta.py").write_text(
            "class BetaAgent:\n    def run(self):\n        return 'beta'\n\nHELLO = 'beta'\n",
            encoding="utf-8"
        )
        (test_dir / "config.json").write_text(
            '{"port": 8000, "host": "localhost", "debug": true}\n',
            encoding="utf-8"
        )
        (test_dir / "notes.txt").write_text(
            "Line one\nHELLO world\nLine three\nHELLO again\nLine five\n",
            encoding="utf-8"
        )

        yield test_dir

        # 清理
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 1. files_with_matches 模式
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_files_with_matches(self, grep, test_files):
        result = await grep.execute(
            pattern="class.*Agent",
            path=str(test_files),
            output_mode="files_with_matches"
        )
        assert result["success"] is True
        assert result["data"]["files_matched"] == 2
        assert result["data"]["total_matches"] == 2
        # 结果是文件路径列表
        paths = result["data"]["results"]
        assert any("alpha.py" in p for p in paths)
        assert any("beta.py" in p for p in paths)

    # ------------------------------------------------------------------
    # 2. content 模式
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_content_mode(self, grep, test_files):
        result = await grep.execute(
            pattern="HELLO",
            path=str(test_files),
            output_mode="content"
        )
        assert result["success"] is True
        assert result["data"]["total_matches"] == 4  # alpha.py 1次 + beta.py 1次 + notes.txt 2次
        # output_text 包含匹配行
        assert "HELLO" in result["data"]["output_text"]

    # ------------------------------------------------------------------
    # 3. count 模式
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_count_mode(self, grep, test_files):
        result = await grep.execute(
            pattern="HELLO",
            path=str(test_files),
            output_mode="count"
        )
        assert result["success"] is True
        assert result["data"]["files_matched"] == 3
        assert result["data"]["total_matches"] == 4

    # ------------------------------------------------------------------
    # 4. 文件类型过滤
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_type_filter_py(self, grep, test_files):
        result = await grep.execute(
            pattern="HELLO",
            path=str(test_files),
            output_mode="files_with_matches",
            type="py"
        )
        assert result["success"] is True
        # 只搜索 .py 文件，notes.txt 应被排除
        assert result["data"]["files_matched"] == 2
        for p in result["data"]["results"]:
            assert p.endswith(".py")

    @pytest.mark.asyncio
    async def test_glob_filter(self, grep, test_files):
        result = await grep.execute(
            pattern="port",
            path=str(test_files),
            output_mode="files_with_matches",
            glob="*.json",
            case_insensitive=True
        )
        assert result["success"] is True
        assert result["data"]["files_matched"] == 1
        assert "config.json" in result["data"]["results"][0]

    # ------------------------------------------------------------------
    # 5. 上下文行
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_context_lines(self, grep, test_files):
        result = await grep.execute(
            pattern="HELLO",
            path=str(test_files / "notes.txt"),
            output_mode="content",
            context=1
        )
        assert result["success"] is True
        text = result["data"]["output_text"]
        # 上下文行应包含 "Line one" 和 "Line three"
        assert "Line one" in text
        assert "Line three" in text

    @pytest.mark.asyncio
    async def test_A_B_context(self, grep, test_files):
        result = await grep.execute(
            pattern="HELLO world",
            path=str(test_files / "notes.txt"),
            output_mode="content",
            B=1,
            A=1
        )
        assert result["success"] is True
        text = result["data"]["output_text"]
        assert "Line one" in text   # B=1，匹配行前一行
        assert "Line three" in text  # A=1，匹配行后一行

    # ------------------------------------------------------------------
    # 6. 大小写不敏感
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_case_insensitive(self, grep, test_files):
        result_sensitive = await grep.execute(
            pattern="hello",
            path=str(test_files),
            output_mode="files_with_matches"
        )
        result_insensitive = await grep.execute(
            pattern="hello",
            path=str(test_files),
            output_mode="files_with_matches",
            case_insensitive=True
        )
        # 大小写敏感时不匹配（文件里是 HELLO）
        assert result_sensitive["data"]["files_matched"] == 0
        # 不敏感时匹配
        assert result_insensitive["data"]["files_matched"] == 3

    # ------------------------------------------------------------------
    # 7. head_limit 限制
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_head_limit(self, grep, test_files):
        result = await grep.execute(
            pattern="HELLO",
            path=str(test_files),
            output_mode="files_with_matches",
            head_limit=1
        )
        assert result["success"] is True
        assert len(result["data"]["results"]) == 1

    # ------------------------------------------------------------------
    # 8. 搜索单个文件
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_single_file(self, grep, test_files):
        result = await grep.execute(
            pattern="def execute",
            path=str(test_files / "alpha.py"),
            output_mode="content"
        )
        assert result["success"] is True
        assert result["data"]["total_matches"] == 1
        assert "execute" in result["data"]["output_text"]

    # ------------------------------------------------------------------
    # 9. 无匹配
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_no_match(self, grep, test_files):
        result = await grep.execute(
            pattern="NONEXISTENT_PATTERN_XYZ",
            path=str(test_files)
        )
        assert result["success"] is True
        assert result["data"]["total_matches"] == 0
        assert result["data"]["files_matched"] == 0

    # ------------------------------------------------------------------
    # 10. 无效正则
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_invalid_regex(self, grep, test_files):
        result = await grep.execute(
            pattern="[invalid regex(",
            path=str(test_files)
        )
        assert result["success"] is False
        assert "正则" in result["error"]

    # ------------------------------------------------------------------
    # 11. 路径不存在
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_path_not_found(self, grep):
        result = await grep.execute(
            pattern="test",
            path="D:/溯源/nonexistent_path_xyz"
        )
        assert result["success"] is False

    # ------------------------------------------------------------------
    # 12. 真实代码库搜索
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_real_codebase_search(self, grep):
        result = await grep.execute(
            pattern="class.*Tool",
            path="D:/溯源/backend/app/tools/utility",
            output_mode="files_with_matches",
            type="py"
        )
        assert result["success"] is True
        assert result["data"]["files_matched"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
