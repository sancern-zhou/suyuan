"""
测试 ListDirectory 工具

验证功能：
1. 列出目录内容
2. 递归列出子目录
3. 隐藏文件过滤
4. 排序（名称/大小/时间）
5. limit 限制
6. 错误处理
"""
import pytest
import sys
from pathlib import Path
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.tools.utility.list_directory_tool import ListDirectoryTool


class TestListDirectoryTool:

    @pytest.fixture
    def list_tool(self):
        return ListDirectoryTool()

    @pytest.fixture
    def test_dir(self):
        """创建测试目录结构"""
        test_dir = project_root / "tests" / "list_dir_test_data"
        test_dir.mkdir(exist_ok=True)

        # 创建文件
        (test_dir / "file1.txt").write_text("content 1")
        (test_dir / "file2.py").write_text("# Python file")
        (test_dir / "large.txt").write_text("A" * 10000)  # 10KB
        (test_dir / ".hidden").write_text("hidden file")

        # 创建子目录
        subdir = test_dir / "subdir"
        subdir.mkdir(exist_ok=True)
        (subdir / "nested.txt").write_text("nested content")

        yield test_dir

        # 清理
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 1. 基础列出
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_basic(self, list_tool, test_dir):
        result = await list_tool.execute(path=str(test_dir))
        assert result["success"] is True
        assert result["data"]["count"] >= 3  # file1.txt, file2.py, large.txt, subdir
        entries = result["data"]["entries"]
        assert any(e["name"] == "file1.txt" for e in entries)
        assert any(e["name"] == "subdir" and e["type"] == "directory" for e in entries)

    # ------------------------------------------------------------------
    # 2. 递归列出
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_recursive(self, list_tool, test_dir):
        result = await list_tool.execute(
            path=str(test_dir),
            recursive=True
        )
        assert result["success"] is True
        entries = result["data"]["entries"]
        # 应该包含子目录中的文件
        assert any("nested.txt" in e["path"] for e in entries)

    # ------------------------------------------------------------------
    # 3. 隐藏文件过滤
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_show_hidden_false(self, list_tool, test_dir):
        result = await list_tool.execute(
            path=str(test_dir),
            show_hidden=False
        )
        assert result["success"] is True
        entries = result["data"]["entries"]
        # 不应包含 .hidden
        assert not any(e["name"] == ".hidden" for e in entries)

    @pytest.mark.asyncio
    async def test_show_hidden_true(self, list_tool, test_dir):
        result = await list_tool.execute(
            path=str(test_dir),
            show_hidden=True
        )
        assert result["success"] is True
        entries = result["data"]["entries"]
        # 应该包含 .hidden
        assert any(e["name"] == ".hidden" for e in entries)

    # ------------------------------------------------------------------
    # 4. 排序
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_sort_by_name(self, list_tool, test_dir):
        result = await list_tool.execute(
            path=str(test_dir),
            sort_by="name"
        )
        assert result["success"] is True
        entries = result["data"]["entries"]
        # 目录应该在前面
        first_entry = entries[0]
        assert first_entry["type"] == "directory" or first_entry["name"] < entries[1]["name"]

    @pytest.mark.asyncio
    async def test_sort_by_size(self, list_tool, test_dir):
        result = await list_tool.execute(
            path=str(test_dir),
            sort_by="size"
        )
        assert result["success"] is True
        entries = result["data"]["entries"]
        # large.txt (10KB) 应该在前面
        files = [e for e in entries if e["type"] == "file"]
        if len(files) >= 2:
            assert files[0].get("size", 0) >= files[1].get("size", 0)

    @pytest.mark.asyncio
    async def test_sort_by_time(self, list_tool, test_dir):
        # 创建两个文件，间隔时间
        old_file = test_dir / "old.txt"
        new_file = test_dir / "new.txt"
        old_file.write_text("old")
        time.sleep(0.1)
        new_file.write_text("new")

        result = await list_tool.execute(
            path=str(test_dir),
            sort_by="time"
        )
        assert result["success"] is True
        entries = result["data"]["entries"]
        # 最新的文件应该在前面
        new_idx = next((i for i, e in enumerate(entries) if e["name"] == "new.txt"), None)
        old_idx = next((i for i, e in enumerate(entries) if e["name"] == "old.txt"), None)
        if new_idx is not None and old_idx is not None:
            assert new_idx < old_idx

    # ------------------------------------------------------------------
    # 5. limit 限制
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_limit(self, list_tool, test_dir):
        result = await list_tool.execute(
            path=str(test_dir),
            limit=2
        )
        assert result["success"] is True
        assert result["data"]["count"] == 2
        assert result["data"]["truncated"] is True

    # ------------------------------------------------------------------
    # 6. 文件元信息
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_file_metadata(self, list_tool, test_dir):
        result = await list_tool.execute(path=str(test_dir))
        assert result["success"] is True
        entries = result["data"]["entries"]

        # 检查文件条目
        file_entry = next((e for e in entries if e["name"] == "file1.txt"), None)
        assert file_entry is not None
        assert file_entry["type"] == "file"
        assert "size" in file_entry
        assert "modified" in file_entry
        assert file_entry["size"] > 0

        # 检查目录条目
        dir_entry = next((e for e in entries if e["name"] == "subdir"), None)
        assert dir_entry is not None
        assert dir_entry["type"] == "directory"
        assert "modified" in dir_entry

    # ------------------------------------------------------------------
    # 7. 空目录
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_empty_directory(self, list_tool, test_dir):
        empty_dir = test_dir / "empty"
        empty_dir.mkdir(exist_ok=True)

        result = await list_tool.execute(path=str(empty_dir))
        assert result["success"] is True
        assert result["data"]["count"] == 0

    # ------------------------------------------------------------------
    # 8. 路径不存在
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_path_not_found(self, list_tool):
        result = await list_tool.execute(
            path="D:/溯源/nonexistent_path_xyz"
        )
        assert result["success"] is False
        assert "不存在" in result["error"]

    # ------------------------------------------------------------------
    # 9. 路径不是目录
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_path_not_directory(self, list_tool, test_dir):
        file_path = test_dir / "file1.txt"
        result = await list_tool.execute(path=str(file_path))
        assert result["success"] is False
        assert "不是目录" in result["error"]

    # ------------------------------------------------------------------
    # 10. 真实目录测试
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_real_directory(self, list_tool):
        result = await list_tool.execute(
            path="D:/溯源/backend/app/tools/utility"
        )
        assert result["success"] is True
        assert result["data"]["count"] > 0
        entries = result["data"]["entries"]
        # 应该包含我们创建的工具文件
        assert any("_tool.py" in e["name"] for e in entries)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
