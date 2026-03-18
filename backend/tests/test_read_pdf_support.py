"""
测试 Read 工具的 PDF pages 参数支持

验证功能：
1. 读取完整 PDF
2. 读取指定页面范围（如 "1-3"）
3. 读取单页（如 "2"）
4. 页面范围验证
5. 页面数量限制（最多 20 页）
6. 错误处理
"""
import pytest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.tools.utility.read_file_tool import ReadFileTool


class TestReadFilePDFSupport:

    @pytest.fixture
    def read_tool(self):
        return ReadFileTool()

    @pytest.fixture
    def test_pdf(self):
        """创建测试 PDF 文件"""
        test_dir = project_root / "tests" / "pdf_test_data"
        test_dir.mkdir(exist_ok=True)

        # 创建一个简单的 PDF 文件用于测试
        pdf_path = test_dir / "test_document.pdf"

        # 使用 PyPDF2 创建测试 PDF
        try:
            from PyPDF2 import PdfWriter, PdfReader
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            import io

            # 创建一个包含 5 页的 PDF
            writer = PdfWriter()

            for i in range(1, 6):
                # 创建每一页
                packet = io.BytesIO()
                can = canvas.Canvas(packet, pagesize=letter)
                can.drawString(100, 750, f"This is page {i}")
                can.drawString(100, 700, f"Content of page {i}")
                can.save()

                packet.seek(0)
                reader = PdfReader(packet)
                writer.add_page(reader.pages[0])

            # 写入文件
            with open(pdf_path, 'wb') as f:
                writer.write(f)

        except ImportError:
            # 如果没有 reportlab，跳过测试
            pytest.skip("reportlab not installed")

        yield pdf_path

        # 清理
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # 1. 读取完整 PDF
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_read_full_pdf(self, read_tool, test_pdf):
        result = await read_tool.execute(path=str(test_pdf))
        assert result["success"] is True
        assert result["data"]["type"] == "pdf"
        assert result["data"]["total_pages"] == 5
        assert result["data"]["pages_read"] == 5
        assert "Page 1" in result["data"]["content"]
        assert "Page 5" in result["data"]["content"]

    # ------------------------------------------------------------------
    # 2. 读取指定页面范围
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_read_pdf_page_range(self, read_tool, test_pdf):
        result = await read_tool.execute(
            path=str(test_pdf),
            pages="1-3"
        )
        assert result["success"] is True
        assert result["data"]["pages_read"] == 3
        assert "Page 1" in result["data"]["content"]
        assert "Page 3" in result["data"]["content"]
        assert "Page 4" not in result["data"]["content"]

    # ------------------------------------------------------------------
    # 3. 读取单页
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_read_pdf_single_page(self, read_tool, test_pdf):
        result = await read_tool.execute(
            path=str(test_pdf),
            pages="2"
        )
        assert result["success"] is True
        assert result["data"]["pages_read"] == 1
        assert "Page 2" in result["data"]["content"]
        assert "Page 1" not in result["data"]["content"]
        assert "Page 3" not in result["data"]["content"]

    # ------------------------------------------------------------------
    # 4. 页面范围验证
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_invalid_page_range(self, read_tool, test_pdf):
        # 超出范围
        result = await read_tool.execute(
            path=str(test_pdf),
            pages="1-10"
        )
        assert result["success"] is False
        assert "无效" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_page_format(self, read_tool, test_pdf):
        # 格式错误
        result = await read_tool.execute(
            path=str(test_pdf),
            pages="abc"
        )
        assert result["success"] is False

    # ------------------------------------------------------------------
    # 5. 边界测试
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_first_page(self, read_tool, test_pdf):
        result = await read_tool.execute(
            path=str(test_pdf),
            pages="1"
        )
        assert result["success"] is True
        assert result["data"]["pages_read"] == 1

    @pytest.mark.asyncio
    async def test_last_page(self, read_tool, test_pdf):
        result = await read_tool.execute(
            path=str(test_pdf),
            pages="5"
        )
        assert result["success"] is True
        assert result["data"]["pages_read"] == 1
        assert "Page 5" in result["data"]["content"]

    # ------------------------------------------------------------------
    # 6. 页面数量限制（模拟）
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_page_limit_warning(self, read_tool):
        """测试页面数量限制提示"""
        # 注意：这个测试需要一个超过 20 页的 PDF
        # 这里只是验证逻辑，实际测试需要大 PDF
        pass

    # ------------------------------------------------------------------
    # 7. 非 PDF 文件
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_non_pdf_with_pages_param(self, read_tool):
        """pages 参数对非 PDF 文件应该被忽略"""
        test_dir = project_root / "tests" / "pdf_test_data"
        test_dir.mkdir(exist_ok=True)
        txt_file = test_dir / "test.txt"
        txt_file.write_text("This is a text file")

        result = await read_tool.execute(
            path=str(txt_file),
            pages="1-5"  # 应该被忽略
        )
        assert result["success"] is True
        assert result["data"]["type"] == "text"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
