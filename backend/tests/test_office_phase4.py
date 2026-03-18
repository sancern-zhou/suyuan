"""
Office 工具单元测试 - Phase 4

测试范围：
- add_slide_tool.py - PPT 幻灯片添加

测试场景：
- 从布局创建幻灯片
- 复制现有幻灯片
- 错误处理
"""
import pytest
import tempfile
import zipfile
from pathlib import Path
from app.tools.office.add_slide_tool import AddSlideTool
from app.tools.office.unpack_tool import UnpackOfficeTool


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_pptx(temp_dir):
    """创建示例 PPTX 文件"""
    pptx_path = temp_dir / "sample.pptx"

    # 创建最小化的 PPTX 结构
    with zipfile.ZipFile(pptx_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
        # [Content_Types].xml
        zip_ref.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
    <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
    <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
</Types>''')

        # _rels/.rels
        zip_ref.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>''')

        # ppt/presentation.xml
        zip_ref.writestr('ppt/presentation.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <p:sldIdLst>
        <p:sldId id="256" r:id="rId2"/>
    </p:sldIdLst>
</p:presentation>''')

        # ppt/_rels/presentation.xml.rels
        zip_ref.writestr('ppt/_rels/presentation.xml.rels', '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="slideLayouts/slideLayout1.xml"/>
</Relationships>''')

        # ppt/slides/slide1.xml
        zip_ref.writestr('ppt/slides/slide1.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
    <p:cSld>
        <p:spTree>
            <p:nvGrpSpPr>
                <p:cNvPr id="1" name=""/>
                <p:cNvGrpSpPr/>
                <p:nvPr/>
            </p:nvGrpSpPr>
        </p:spTree>
    </p:cSld>
</p:sld>''')

        # ppt/slides/_rels/slide1.xml.rels
        zip_ref.writestr('ppt/slides/_rels/slide1.xml.rels', '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>''')

        # ppt/slideLayouts/slideLayout1.xml
        zip_ref.writestr('ppt/slideLayouts/slideLayout1.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<p:sldLayout xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
    <p:cSld name="Blank"/>
</p:sldLayout>''')

    return pptx_path


class TestAddSlideTool:
    """测试 AddSlideTool"""

    @pytest.mark.asyncio
    async def test_add_slide_invalid_dir(self, temp_dir):
        """测试添加幻灯片 - 目录不存在"""
        tool = AddSlideTool()

        result = await tool.execute(
            unpacked_dir=str(temp_dir / "nonexistent"),
            source="slideLayout1.xml"
        )

        assert result["success"] is False
        assert "不存在" in result["summary"]

    @pytest.mark.asyncio
    async def test_add_slide_invalid_structure(self, temp_dir):
        """测试添加幻灯片 - 无效的目录结构"""
        tool = AddSlideTool()
        invalid_dir = temp_dir / "invalid"
        invalid_dir.mkdir()

        result = await tool.execute(
            unpacked_dir=str(invalid_dir),
            source="slideLayout1.xml"
        )

        assert result["success"] is False
        assert "无效" in result["summary"]

    @pytest.mark.asyncio
    async def test_add_slide_from_layout(self, sample_pptx, temp_dir):
        """测试从布局创建幻灯片"""
        # 先解包
        unpack_tool = UnpackOfficeTool()
        unpacked_dir = temp_dir / "unpacked"
        await unpack_tool.execute(
            file_path=str(sample_pptx),
            output_dir=str(unpacked_dir)
        )

        # 添加幻灯片
        tool = AddSlideTool()
        result = await tool.execute(
            unpacked_dir=str(unpacked_dir),
            source="slideLayout1.xml"
        )

        assert result["success"] is True
        assert result["data"]["source_type"] == "layout"
        assert result["data"]["slide_number"] == 2
        assert result["data"]["new_slide"] == "slide2.xml"

        # 验证文件已创建
        new_slide = unpacked_dir / "ppt" / "slides" / "slide2.xml"
        assert new_slide.exists()

    @pytest.mark.asyncio
    async def test_duplicate_slide(self, sample_pptx, temp_dir):
        """测试复制幻灯片"""
        # 先解包
        unpack_tool = UnpackOfficeTool()
        unpacked_dir = temp_dir / "unpacked"
        await unpack_tool.execute(
            file_path=str(sample_pptx),
            output_dir=str(unpacked_dir)
        )

        # 复制幻灯片
        tool = AddSlideTool()
        result = await tool.execute(
            unpacked_dir=str(unpacked_dir),
            source="slide1.xml"
        )

        assert result["success"] is True
        assert result["data"]["source_type"] == "slide"
        assert result["data"]["slide_number"] == 2
        assert result["data"]["source_slide"] == "slide1.xml"

        # 验证文件已创建
        new_slide = unpacked_dir / "ppt" / "slides" / "slide2.xml"
        assert new_slide.exists()

    @pytest.mark.asyncio
    async def test_add_multiple_slides(self, sample_pptx, temp_dir):
        """测试添加多个幻灯片"""
        # 先解包
        unpack_tool = UnpackOfficeTool()
        unpacked_dir = temp_dir / "unpacked"
        await unpack_tool.execute(
            file_path=str(sample_pptx),
            output_dir=str(unpacked_dir)
        )

        tool = AddSlideTool()

        # 添加第一个幻灯片
        result1 = await tool.execute(
            unpacked_dir=str(unpacked_dir),
            source="slideLayout1.xml"
        )
        assert result1["success"] is True
        assert result1["data"]["slide_number"] == 2

        # 添加第二个幻灯片
        result2 = await tool.execute(
            unpacked_dir=str(unpacked_dir),
            source="slide1.xml"
        )
        assert result2["success"] is True
        assert result2["data"]["slide_number"] == 3

        # 验证文件已创建
        assert (unpacked_dir / "ppt" / "slides" / "slide2.xml").exists()
        assert (unpacked_dir / "ppt" / "slides" / "slide3.xml").exists()

    @pytest.mark.asyncio
    async def test_add_slide_invalid_source(self, sample_pptx, temp_dir):
        """测试添加幻灯片 - 无效的源文件名"""
        # 先解包
        unpack_tool = UnpackOfficeTool()
        unpacked_dir = temp_dir / "unpacked"
        await unpack_tool.execute(
            file_path=str(sample_pptx),
            output_dir=str(unpacked_dir)
        )

        tool = AddSlideTool()
        result = await tool.execute(
            unpacked_dir=str(unpacked_dir),
            source="invalid.xml"
        )

        assert result["success"] is False
        assert "格式错误" in result["summary"]

    @pytest.mark.asyncio
    async def test_add_slide_nonexistent_layout(self, sample_pptx, temp_dir):
        """测试添加幻灯片 - 布局文件不存在"""
        # 先解包
        unpack_tool = UnpackOfficeTool()
        unpacked_dir = temp_dir / "unpacked"
        await unpack_tool.execute(
            file_path=str(sample_pptx),
            output_dir=str(unpacked_dir)
        )

        tool = AddSlideTool()
        result = await tool.execute(
            unpacked_dir=str(unpacked_dir),
            source="slideLayout99.xml"
        )

        assert result["success"] is False
        assert "不存在" in result["summary"]

    @pytest.mark.asyncio
    async def test_add_slide_schema(self):
        """测试工具 Schema"""
        tool = AddSlideTool()
        schema = tool.get_function_schema()

        assert schema["name"] == "add_ppt_slide"
        assert "parameters" in schema
        assert "unpacked_dir" in schema["parameters"]["properties"]
        assert "source" in schema["parameters"]["properties"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
