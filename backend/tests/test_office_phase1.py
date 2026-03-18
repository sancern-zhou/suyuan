"""
Office 工具单元测试 - Phase 1

测试范围：
- soffice.py - LibreOffice 沙箱适配
- unpack_tool.py - Office 文件解包
- pack_tool.py - Office 文件打包

测试场景：
- DOCX 解包/打包
- XLSX 解包/打包
- PPTX 解包/打包
- 错误处理
"""
import pytest
import tempfile
import zipfile
from pathlib import Path
from app.tools.office.unpack_tool import UnpackOfficeTool
from app.tools.office.pack_tool import PackOfficeTool


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_docx(temp_dir):
    """创建示例 DOCX 文件"""
    docx_path = temp_dir / "sample.docx"

    # 创建最小化的 DOCX 结构
    with zipfile.ZipFile(docx_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
        # [Content_Types].xml
        zip_ref.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>''')

        # _rels/.rels
        zip_ref.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''')

        # word/document.xml
        zip_ref.writestr('word/document.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p>
            <w:r>
                <w:t>Hello World</w:t>
            </w:r>
        </w:p>
    </w:body>
</w:document>''')

    return docx_path


@pytest.fixture
def sample_xlsx(temp_dir):
    """创建示例 XLSX 文件"""
    xlsx_path = temp_dir / "sample.xlsx"

    # 创建最小化的 XLSX 结构
    with zipfile.ZipFile(xlsx_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
        # [Content_Types].xml
        zip_ref.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
    <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>''')

        # _rels/.rels
        zip_ref.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''')

        # xl/workbook.xml
        zip_ref.writestr('xl/workbook.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <sheets>
        <sheet name="Sheet1" sheetId="1" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>
    </sheets>
</workbook>''')

        # xl/worksheets/sheet1.xml
        zip_ref.writestr('xl/worksheets/sheet1.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <sheetData>
        <row r="1">
            <c r="A1" t="inlineStr">
                <is><t>Test Data</t></is>
            </c>
        </row>
    </sheetData>
</worksheet>''')

    return xlsx_path


class TestUnpackOfficeTool:
    """测试 UnpackOfficeTool"""

    @pytest.mark.asyncio
    async def test_unpack_docx(self, sample_docx, temp_dir):
        """测试解包 DOCX 文件"""
        tool = UnpackOfficeTool()
        output_dir = temp_dir / "unpacked_docx"

        result = await tool.execute(
            file_path=str(sample_docx),
            output_dir=str(output_dir)
        )

        assert result["success"] is True
        assert result["data"]["file_count"] > 0
        assert len(result["data"]["xml_files"]) > 0
        assert output_dir.exists()
        assert (output_dir / "word" / "document.xml").exists()

    @pytest.mark.asyncio
    async def test_unpack_xlsx(self, sample_xlsx, temp_dir):
        """测试解包 XLSX 文件"""
        tool = UnpackOfficeTool()
        output_dir = temp_dir / "unpacked_xlsx"

        result = await tool.execute(
            file_path=str(sample_xlsx),
            output_dir=str(output_dir)
        )

        assert result["success"] is True
        assert result["data"]["file_count"] > 0
        assert len(result["data"]["xml_files"]) > 0
        assert output_dir.exists()
        assert (output_dir / "xl" / "workbook.xml").exists()

    @pytest.mark.asyncio
    async def test_unpack_nonexistent_file(self, temp_dir):
        """测试解包不存在的文件"""
        tool = UnpackOfficeTool()

        result = await tool.execute(
            file_path=str(temp_dir / "nonexistent.docx"),
            output_dir=str(temp_dir / "output")
        )

        assert result["success"] is False
        assert "不存在" in result["summary"]

    @pytest.mark.asyncio
    async def test_unpack_invalid_format(self, temp_dir):
        """测试解包不支持的格式"""
        tool = UnpackOfficeTool()
        invalid_file = temp_dir / "test.txt"
        invalid_file.write_text("test")

        result = await tool.execute(
            file_path=str(invalid_file),
            output_dir=str(temp_dir / "output")
        )

        assert result["success"] is False
        assert "格式" in result["summary"]


class TestPackOfficeTool:
    """测试 PackOfficeTool"""

    @pytest.mark.asyncio
    async def test_pack_docx(self, sample_docx, temp_dir):
        """测试打包 DOCX 文件"""
        # 先解包
        unpack_tool = UnpackOfficeTool()
        unpacked_dir = temp_dir / "unpacked"
        await unpack_tool.execute(
            file_path=str(sample_docx),
            output_dir=str(unpacked_dir)
        )

        # 再打包
        pack_tool = PackOfficeTool()
        output_file = temp_dir / "repacked.docx"

        result = await pack_tool.execute(
            input_dir=str(unpacked_dir),
            output_file=str(output_file)
        )

        assert result["success"] is True
        assert result["data"]["file_count"] > 0
        assert output_file.exists()
        assert output_file.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_pack_xlsx(self, sample_xlsx, temp_dir):
        """测试打包 XLSX 文件"""
        # 先解包
        unpack_tool = UnpackOfficeTool()
        unpacked_dir = temp_dir / "unpacked"
        await unpack_tool.execute(
            file_path=str(sample_xlsx),
            output_dir=str(unpacked_dir)
        )

        # 再打包
        pack_tool = PackOfficeTool()
        output_file = temp_dir / "repacked.xlsx"

        result = await pack_tool.execute(
            input_dir=str(unpacked_dir),
            output_file=str(output_file)
        )

        assert result["success"] is True
        assert result["data"]["file_count"] > 0
        assert output_file.exists()
        assert output_file.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_pack_with_backup(self, sample_docx, temp_dir):
        """测试打包时备份原文件"""
        # 先解包
        unpack_tool = UnpackOfficeTool()
        unpacked_dir = temp_dir / "unpacked"
        await unpack_tool.execute(
            file_path=str(sample_docx),
            output_dir=str(unpacked_dir)
        )

        # 创建原文件
        output_file = temp_dir / "output.docx"
        output_file.write_text("original")

        # 打包（带备份）
        pack_tool = PackOfficeTool()
        result = await pack_tool.execute(
            input_dir=str(unpacked_dir),
            output_file=str(output_file),
            backup=True
        )

        assert result["success"] is True
        assert "backup_file" in result["data"]
        backup_file = Path(result["data"]["backup_file"])
        assert backup_file.exists()

    @pytest.mark.asyncio
    async def test_pack_nonexistent_dir(self, temp_dir):
        """测试打包不存在的目录"""
        pack_tool = PackOfficeTool()

        result = await pack_tool.execute(
            input_dir=str(temp_dir / "nonexistent"),
            output_file=str(temp_dir / "output.docx")
        )

        assert result["success"] is False
        assert "不存在" in result["summary"]


class TestRoundTrip:
    """测试完整的解包-编辑-打包流程"""

    @pytest.mark.asyncio
    async def test_docx_roundtrip(self, sample_docx, temp_dir):
        """测试 DOCX 完整流程"""
        # 1. 解包
        unpack_tool = UnpackOfficeTool()
        unpacked_dir = temp_dir / "unpacked"
        unpack_result = await unpack_tool.execute(
            file_path=str(sample_docx),
            output_dir=str(unpacked_dir)
        )
        assert unpack_result["success"] is True

        # 2. 验证 XML 文件存在
        document_xml = unpacked_dir / "word" / "document.xml"
        assert document_xml.exists()

        # 3. 读取并验证内容
        content = document_xml.read_text(encoding='utf-8')
        assert "Hello World" in content

        # 4. 打包
        pack_tool = PackOfficeTool()
        output_file = temp_dir / "output.docx"
        pack_result = await pack_tool.execute(
            input_dir=str(unpacked_dir),
            output_file=str(output_file)
        )
        assert pack_result["success"] is True

        # 5. 验证打包后的文件
        assert output_file.exists()
        assert zipfile.is_zipfile(output_file)

        # 6. 验证打包后的内容
        with zipfile.ZipFile(output_file, 'r') as zip_ref:
            with zip_ref.open('word/document.xml') as f:
                repacked_content = f.read().decode('utf-8')
                assert "Hello World" in repacked_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
