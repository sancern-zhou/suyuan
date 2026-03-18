"""
测试 Grep 和 Edit 工具对不同文件格式的支持

验证：
1. Markdown (.md)
2. JSON (.json)
3. YAML (.yaml)
4. XML (.xml)
5. HTML (.html)
6. CSS (.css)
7. SQL (.sql)
8. 配置文件 (.ini, .toml, .env)
"""
import pytest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.tools.utility.grep_tool import GrepTool
from app.tools.utility.edit_file_tool import EditFileTool


class TestFileFormatSupport:

    @pytest.fixture
    def grep_tool(self):
        return GrepTool()

    @pytest.fixture
    def edit_tool(self):
        return EditFileTool()

    @pytest.fixture
    def test_dir(self):
        """创建各种格式的测试文件"""
        test_dir = project_root / "tests" / "format_test_data"
        test_dir.mkdir(exist_ok=True)

        # Markdown
        (test_dir / "README.md").write_text("""# 项目标题

## 功能特性

- 特性1：数据分析
- 特性2：可视化
- 特性3：报告生成

## 安装

```bash
pip install package
```
""", encoding="utf-8")

        # JSON
        (test_dir / "config.json").write_text("""{
  "name": "test-project",
  "version": "1.0.0",
  "port": 8000
}""", encoding="utf-8")

        # YAML
        (test_dir / "config.yaml").write_text("""name: test-project
version: 1.0.0
database:
  host: localhost
  port: 5432
""", encoding="utf-8")

        # XML
        (test_dir / "data.xml").write_text("""<?xml version="1.0"?>
<root>
  <item id="1">Item One</item>
  <item id="2">Item Two</item>
</root>""", encoding="utf-8")

        # HTML
        (test_dir / "index.html").write_text("""<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
</head>
<body>
    <h1>Welcome</h1>
    <p>This is a test page.</p>
</body>
</html>""", encoding="utf-8")

        # CSS
        (test_dir / "style.css").write_text(""".container {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
}

.button {
  background-color: blue;
  color: white;
}""", encoding="utf-8")

        # SQL
        (test_dir / "schema.sql").write_text("""CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100),
  email VARCHAR(255)
);

INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com');
""", encoding="utf-8")

        # INI
        (test_dir / "app.ini").write_text("""[database]
host = localhost
port = 5432

[server]
port = 8000
debug = true
""", encoding="utf-8")

        # TOML
        (test_dir / "pyproject.toml").write_text("""[tool.poetry]
name = "test-project"
version = "1.0.0"

[tool.poetry.dependencies]
python = "^3.9"
""", encoding="utf-8")

        # ENV
        (test_dir / ".env").write_text("""DATABASE_URL=postgresql://localhost/db
API_KEY=secret123
DEBUG=true
""", encoding="utf-8")

        yield test_dir

        # 清理
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

    # ========================================
    # Grep 工具测试
    # ========================================

    @pytest.mark.asyncio
    async def test_grep_markdown(self, grep_tool, test_dir):
        result = await grep_tool.execute(
            pattern="功能特性",
            path=str(test_dir / "README.md"),
            output_mode="content"
        )
        assert result["success"] is True
        assert result["data"]["total_matches"] >= 1

    @pytest.mark.asyncio
    async def test_grep_json(self, grep_tool, test_dir):
        result = await grep_tool.execute(
            pattern='"port"',
            path=str(test_dir / "config.json"),
            output_mode="content"
        )
        assert result["success"] is True
        assert result["data"]["total_matches"] >= 1

    @pytest.mark.asyncio
    async def test_grep_yaml(self, grep_tool, test_dir):
        result = await grep_tool.execute(
            pattern="database:",
            path=str(test_dir / "config.yaml"),
            output_mode="content"
        )
        assert result["success"] is True
        assert result["data"]["total_matches"] >= 1

    @pytest.mark.asyncio
    async def test_grep_xml(self, grep_tool, test_dir):
        result = await grep_tool.execute(
            pattern='<item',
            path=str(test_dir / "data.xml"),
            output_mode="content"
        )
        assert result["success"] is True
        assert result["data"]["total_matches"] == 2

    @pytest.mark.asyncio
    async def test_grep_html(self, grep_tool, test_dir):
        result = await grep_tool.execute(
            pattern="<h1>",
            path=str(test_dir / "index.html"),
            output_mode="content"
        )
        assert result["success"] is True
        assert result["data"]["total_matches"] >= 1

    @pytest.mark.asyncio
    async def test_grep_css(self, grep_tool, test_dir):
        result = await grep_tool.execute(
            pattern="background-color",
            path=str(test_dir / "style.css"),
            output_mode="content"
        )
        assert result["success"] is True
        assert result["data"]["total_matches"] >= 1

    @pytest.mark.asyncio
    async def test_grep_sql(self, grep_tool, test_dir):
        result = await grep_tool.execute(
            pattern="CREATE TABLE",
            path=str(test_dir / "schema.sql"),
            output_mode="content"
        )
        assert result["success"] is True
        assert result["data"]["total_matches"] >= 1

    @pytest.mark.asyncio
    async def test_grep_type_filter_md(self, grep_tool, test_dir):
        """测试 type="md" 过滤"""
        result = await grep_tool.execute(
            pattern="项目",
            path=str(test_dir),
            type="md",
            output_mode="files_with_matches"
        )
        assert result["success"] is True
        assert result["data"]["files_matched"] >= 1
        assert any("README.md" in f for f in result["data"]["results"])

    # ========================================
    # Edit 工具测试
    # ========================================

    @pytest.mark.asyncio
    async def test_edit_markdown(self, edit_tool, test_dir):
        file_path = test_dir / "README.md"
        result = await edit_tool.execute(
            file_path=str(file_path),
            old_string="# 项目标题",
            new_string="# 新项目标题"
        )
        assert result["success"] is True
        assert "新项目标题" in file_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_edit_json(self, edit_tool, test_dir):
        file_path = test_dir / "config.json"
        result = await edit_tool.execute(
            file_path=str(file_path),
            old_string='"port": 8000',
            new_string='"port": 9000'
        )
        assert result["success"] is True
        assert "9000" in file_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_edit_yaml(self, edit_tool, test_dir):
        file_path = test_dir / "config.yaml"
        result = await edit_tool.execute(
            file_path=str(file_path),
            old_string="host: localhost",
            new_string="host: 127.0.0.1"
        )
        assert result["success"] is True
        assert "127.0.0.1" in file_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_edit_xml(self, edit_tool, test_dir):
        file_path = test_dir / "data.xml"
        result = await edit_tool.execute(
            file_path=str(file_path),
            old_string='<item id="1">Item One</item>',
            new_string='<item id="1">Updated Item</item>'
        )
        assert result["success"] is True
        assert "Updated Item" in file_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_edit_html(self, edit_tool, test_dir):
        file_path = test_dir / "index.html"
        result = await edit_tool.execute(
            file_path=str(file_path),
            old_string="<h1>Welcome</h1>",
            new_string="<h1>Hello World</h1>"
        )
        assert result["success"] is True
        assert "Hello World" in file_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_edit_css(self, edit_tool, test_dir):
        file_path = test_dir / "style.css"
        result = await edit_tool.execute(
            file_path=str(file_path),
            old_string="background-color: blue;",
            new_string="background-color: red;"
        )
        assert result["success"] is True
        assert "red" in file_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_edit_sql(self, edit_tool, test_dir):
        file_path = test_dir / "schema.sql"
        result = await edit_tool.execute(
            file_path=str(file_path),
            old_string="VARCHAR(100)",
            new_string="VARCHAR(200)"
        )
        assert result["success"] is True
        assert "VARCHAR(200)" in file_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_edit_multiline_markdown(self, edit_tool, test_dir):
        """测试多行 Markdown 编辑"""
        file_path = test_dir / "README.md"
        result = await edit_tool.execute(
            file_path=str(file_path),
            old_string="""## 功能特性

- 特性1：数据分析
- 特性2：可视化
- 特性3：报告生成""",
            new_string="""## 核心功能

- 功能1：智能分析
- 功能2：数据可视化
- 功能3：自动报告"""
        )
        assert result["success"] is True
        content = file_path.read_text(encoding="utf-8")
        assert "核心功能" in content
        assert "智能分析" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
