"""
测试 WriteFile 工具

验证功能：
1. 创建新文件
2. 覆写已有文件
3. 自动创建父目录
4. 多行内容写入
5. 编码支持
6. 文件大小限制
7. 错误处理（路径是目录、路径非法等）
"""
import pytest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.tools.utility.write_file_tool import WriteFileTool


class TestWriteFileTool:

    @pytest.fixture
    def write_tool(self):
        return WriteFileTool()

    @pytest.fixture
    def test_dir(self):
        """测试目录（在项目内）"""
        test_dir = project_root / "tests" / "write_test_data"
        test_dir.mkdir(exist_ok=True)
        yield test_dir
        # 清理
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 1. 创建新文件
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_new_file(self, write_tool, test_dir):
        file_path = test_dir / "new_file.txt"
        result = await write_tool.execute(
            file_path=str(file_path),
            content="Hello World"
        )
        assert result["success"] is True
        assert result["data"]["created"] is True
        assert file_path.exists()
        assert file_path.read_text() == "Hello World"

    # ------------------------------------------------------------------
    # 2. 覆写已有文件
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_overwrite_existing_file(self, write_tool, test_dir):
        file_path = test_dir / "existing.txt"
        file_path.write_text("old content")

        result = await write_tool.execute(
            file_path=str(file_path),
            content="new content"
        )
        assert result["success"] is True
        assert result["data"]["created"] is False  # 覆写，非新建
        assert file_path.read_text() == "new content"

    # ------------------------------------------------------------------
    # 3. 自动创建父目录
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_parent_dirs(self, write_tool, test_dir):
        file_path = test_dir / "subdir1" / "subdir2" / "file.txt"
        result = await write_tool.execute(
            file_path=str(file_path),
            content="nested file",
            create_dirs=True
        )
        assert result["success"] is True
        assert file_path.exists()
        assert file_path.read_text() == "nested file"

    @pytest.mark.asyncio
    async def test_no_create_dirs(self, write_tool, test_dir):
        file_path = test_dir / "nonexistent_dir" / "file.txt"
        result = await write_tool.execute(
            file_path=str(file_path),
            content="test",
            create_dirs=False
        )
        assert result["success"] is False
        assert "创建父目录失败" in result["summary"] or "No such file" in result["error"]

    # ------------------------------------------------------------------
    # 4. 多行内容
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_multiline_content(self, write_tool, test_dir):
        file_path = test_dir / "multiline.txt"
        content = "Line 1\nLine 2\nLine 3\n"
        result = await write_tool.execute(
            file_path=str(file_path),
            content=content
        )
        assert result["success"] is True
        assert result["data"]["lines"] == 3
        assert file_path.read_text() == content

    # ------------------------------------------------------------------
    # 5. 代码文件写入
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_write_code_file(self, write_tool, test_dir):
        file_path = test_dir / "script.py"
        code = """def hello():
    print("Hello World")

if __name__ == "__main__":
    hello()
"""
        result = await write_tool.execute(
            file_path=str(file_path),
            content=code
        )
        assert result["success"] is True
        assert file_path.read_text() == code
        assert result["data"]["lines"] == 5

    # ------------------------------------------------------------------
    # 6. JSON 文件写入
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_write_json_file(self, write_tool, test_dir):
        file_path = test_dir / "config.json"
        json_content = '{\n  "port": 8000,\n  "host": "localhost"\n}'
        result = await write_tool.execute(
            file_path=str(file_path),
            content=json_content
        )
        assert result["success"] is True
        assert file_path.read_text() == json_content

    # ------------------------------------------------------------------
    # 7. 编码支持
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_encoding_utf8(self, write_tool, test_dir):
        file_path = test_dir / "chinese.txt"
        content = "你好世界\n测试中文"
        result = await write_tool.execute(
            file_path=str(file_path),
            content=content,
            encoding="utf-8"
        )
        assert result["success"] is True
        assert file_path.read_text(encoding="utf-8") == content

    # ------------------------------------------------------------------
    # 8. 文件大小统计
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_file_size_stats(self, write_tool, test_dir):
        file_path = test_dir / "stats.txt"
        content = "A" * 1000  # 1000 字节
        result = await write_tool.execute(
            file_path=str(file_path),
            content=content
        )
        assert result["success"] is True
        assert result["data"]["size"] == 1000
        assert result["data"]["lines"] == 1

    # ------------------------------------------------------------------
    # 9. 空文件
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_empty_file(self, write_tool, test_dir):
        file_path = test_dir / "empty.txt"
        result = await write_tool.execute(
            file_path=str(file_path),
            content=""
        )
        assert result["success"] is True
        assert result["data"]["size"] == 0
        assert result["data"]["lines"] == 0
        assert file_path.read_text() == ""

    # ------------------------------------------------------------------
    # 10. 路径是目录（错误）
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_path_is_directory(self, write_tool, test_dir):
        result = await write_tool.execute(
            file_path=str(test_dir),
            content="test"
        )
        assert result["success"] is False
        assert "目录" in result["error"]

    # ------------------------------------------------------------------
    # 11. 路径非法（超出工作目录）
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_path_outside_workdir(self, write_tool):
        result = await write_tool.execute(
            file_path="C:/Windows/test.txt",
            content="test"
        )
        assert result["success"] is False
        assert "路径" in result["error"]

    # ------------------------------------------------------------------
    # 12. 文件大小限制（模拟）
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_file_size_limit(self, write_tool, test_dir):
        file_path = test_dir / "large.txt"
        # 创建超过 10MB 的内容
        large_content = "A" * (11 * 1024 * 1024)  # 11MB
        result = await write_tool.execute(
            file_path=str(file_path),
            content=large_content
        )
        assert result["success"] is False
        assert "过大" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
