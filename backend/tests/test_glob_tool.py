"""
测试 Glob 工具 (search_files)

验证功能：
1. 基础 glob 模式（*.py）
2. 递归搜索（**/*.json）
3. 复杂模式（test_*.py）
4. 文件/目录过滤
5. 按时间排序
6. limit 限制
7. 错误处理
"""
import pytest
import sys
from pathlib import Path
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.tools.utility.glob_tool import GlobTool


class TestGlobTool:

    @pytest.fixture
    def glob_tool(self):
        return GlobTool()

    @pytest.fixture
    def test_dir(self):
        """创建测试目录结构"""
        test_dir = project_root / "tests" / "glob_test_data"
        test_dir.mkdir(exist_ok=True)

        # 创建测试文件
        (test_dir / "file1.py").write_text("# Python file 1")
        (test_dir / "file2.py").write_text("# Python file 2")
        (test_dir / "config.json").write_text('{"key": "value"}')
        (test_dir / "data.txt").write_text("text data")
        (test_dir / "test_alpha.py").write_text("# Test file alpha")
        (test_dir / "test_beta.py").write_text("# Test file beta")

        # 创建子目录
        subdir = test_dir / "subdir"
        subdir.mkdir(exist_ok=True)
        (subdir / "nested.py").write_text("# Nested Python file")
        (subdir / "config.json").write_text('{"nested": true}')

        yield test_dir

        # 清理
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 1. 基础 glob 模式
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_simple_pattern(self, glob_tool, test_dir):
        result = await glob_tool.execute(
            pattern="*.py",
            path=str(test_dir)
        )
        assert result["success"] is True
        assert result["data"]["count"] >= 4  # file1.py, file2.py, test_alpha.py, test_beta.py
        assert any("file1.py" in f for f in result["data"]["files"])

    @pytest.mark.asyncio
    async def test_json_pattern(self, glob_tool, test_dir):
        result = await glob_tool.execute(
            pattern="*.json",
            path=str(test_dir)
        )
        assert result["success"] is True
        assert result["data"]["count"] == 1  # 只有顶层的 config.json
        assert "config.json" in result["data"]["files"]

    # ------------------------------------------------------------------
    # 2. 递归搜索
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_recursive_pattern(self, glob_tool, test_dir):
        result = await glob_tool.execute(
            pattern="**/*.json",
            path=str(test_dir)
        )
        assert result["success"] is True
        assert result["data"]["count"] == 2  # config.json + subdir/config.json
        files = result["data"]["files"]
        assert any("config.json" in f for f in files)
        assert any("subdir" in f and "config.json" in f for f in files)

    @pytest.mark.asyncio
    async def test_recursive_py(self, glob_tool, test_dir):
        result = await glob_tool.execute(
            pattern="**/*.py",
            path=str(test_dir)
        )
        assert result["success"] is True
        assert result["data"]["count"] >= 5  # 顶层4个 + subdir/nested.py

    # ------------------------------------------------------------------
    # 3. 复杂模式
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_prefix_pattern(self, glob_tool, test_dir):
        result = await glob_tool.execute(
            pattern="test_*.py",
            path=str(test_dir)
        )
        assert result["success"] is True
        assert result["data"]["count"] == 2  # test_alpha.py, test_beta.py
        files = result["data"]["files"]
        assert any("test_alpha.py" in f for f in files)
        assert any("test_beta.py" in f for f in files)

    @pytest.mark.asyncio
    async def test_wildcard_pattern(self, glob_tool, test_dir):
        result = await glob_tool.execute(
            pattern="*config*",
            path=str(test_dir)
        )
        assert result["success"] is True
        assert result["data"]["count"] >= 1
        assert any("config" in f for f in result["data"]["files"])

    # ------------------------------------------------------------------
    # 4. 文件/目录过滤
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_files_only(self, glob_tool, test_dir):
        result = await glob_tool.execute(
            pattern="*",
            path=str(test_dir),
            files_only=True
        )
        assert result["success"] is True
        # 所有结果应该是文件，不包含 subdir
        assert all("subdir" != f for f in result["data"]["files"])

    @pytest.mark.asyncio
    async def test_include_dirs(self, glob_tool, test_dir):
        result = await glob_tool.execute(
            pattern="*",
            path=str(test_dir),
            files_only=False
        )
        assert result["success"] is True
        # 应该包含 subdir 目录
        assert any("subdir" == f for f in result["data"]["files"])

    # ------------------------------------------------------------------
    # 5. limit 限制
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_limit(self, glob_tool, test_dir):
        result = await glob_tool.execute(
            pattern="*.py",
            path=str(test_dir),
            limit=2
        )
        assert result["success"] is True
        assert result["data"]["count"] == 2
        assert result["data"]["truncated"] is True
        assert result["data"]["total_matches"] >= 4

    # ------------------------------------------------------------------
    # 6. 按时间排序
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_sort_by_time(self, glob_tool, test_dir):
        # 创建两个文件，间隔时间
        file_old = test_dir / "old.txt"
        file_new = test_dir / "new.txt"

        file_old.write_text("old")
        time.sleep(0.1)
        file_new.write_text("new")

        result = await glob_tool.execute(
            pattern="*.txt",
            path=str(test_dir),
            sort_by_time=True
        )
        assert result["success"] is True
        files = result["data"]["files"]
        # 最新的文件应该在前面
        new_idx = next(i for i, f in enumerate(files) if "new.txt" in f)
        old_idx = next(i for i, f in enumerate(files) if "old.txt" in f)
        assert new_idx < old_idx

    # ------------------------------------------------------------------
    # 7. 无匹配
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_no_match(self, glob_tool, test_dir):
        result = await glob_tool.execute(
            pattern="*.nonexistent",
            path=str(test_dir)
        )
        assert result["success"] is True
        assert result["data"]["count"] == 0

    # ------------------------------------------------------------------
    # 8. 路径不存在
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_path_not_found(self, glob_tool):
        result = await glob_tool.execute(
            pattern="*.py",
            path="D:/溯源/nonexistent_path_xyz"
        )
        assert result["success"] is False
        assert "不存在" in result["error"]

    # ------------------------------------------------------------------
    # 9. 真实代码库搜索
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_real_codebase_search(self, glob_tool):
        result = await glob_tool.execute(
            pattern="*_tool.py",
            path="D:/溯源/backend/app/tools/utility"
        )
        assert result["success"] is True
        assert result["data"]["count"] >= 4  # read, edit, grep, write, glob
        files = result["data"]["files"]
        assert any("read_file_tool.py" in f for f in files)
        assert any("edit_file_tool.py" in f for f in files)

    @pytest.mark.asyncio
    async def test_recursive_real_search(self, glob_tool):
        result = await glob_tool.execute(
            pattern="**/*.json",
            path="D:/溯源/backend/app",
            limit=10
        )
        assert result["success"] is True
        # 应该找到一些 JSON 文件


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
