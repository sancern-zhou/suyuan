"""
AddSlide 工具 - PPT 幻灯片添加

功能：
- 向解包后的 PPTX 目录添加新幻灯片
- 支持从布局模板创建
- 支持复制现有幻灯片
- 自动更新关系文件和内容类型

使用场景：
- 批量生成幻灯片
- 基于模板创建演示文稿
- 复制幻灯片内容
"""
import re
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()


class AddSlideTool(LLMTool):
    """
    PPT 幻灯片添加工具

    功能：
    - 向解包后的 PPTX 目录添加新幻灯片
    - 支持从布局模板创建
    - 支持复制现有幻灯片
    """

    def __init__(self):
        super().__init__(
            name="add_ppt_slide",
            description="""向 PPT 添加新幻灯片

功能：
- 向解包后的 PPTX 目录添加新幻灯片
- 支持从布局模板创建（slideLayout1.xml）
- 支持复制现有幻灯片（slide1.xml）
- 自动更新关系文件和内容类型

使用场景：
- 批量生成幻灯片
- 基于模板创建演示文稿
- 复制幻灯片内容

示例：
- add_ppt_slide(unpacked_dir="unpacked/", source="slideLayout1.xml")  # 从布局创建
- add_ppt_slide(unpacked_dir="unpacked/", source="slide2.xml")  # 复制幻灯片

参数说明：
- unpacked_dir: 解包后的 PPTX 目录（使用 unpack_office 生成）
- source: 源文件名（slideLayoutN.xml 或 slideN.xml）

注意：
- 必须先使用 unpack_office 解包 PPTX 文件
- 完成后使用 pack_office 重新打包
- 会自动更新 presentation.xml
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        self.working_dir = Path.cwd().parent  # D:\溯源\ 或 /opt/app/ 等

    async def execute(
        self,
        unpacked_dir: str,
        source: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        添加 PPT 幻灯片

        Args:
            unpacked_dir: 解包后的 PPTX 目录
            source: 源文件名（slideLayoutN.xml 或 slideN.xml）

        Returns:
            {
                "success": bool,
                "data": {
                    "new_slide": str,
                    "slide_number": int,
                    "source_type": str
                },
                "summary": str
            }
        """
        try:
            # 1. 路径解析
            unpacked_dir = self._resolve_path(unpacked_dir)
            if not unpacked_dir:
                return {
                    "success": False,
                    "data": {"error": "目录路径无效"},
                    "summary": "添加幻灯片失败：路径无效"
                }

            if not unpacked_dir.exists() or not unpacked_dir.is_dir():
                return {
                    "success": False,
                    "data": {"error": f"目录不存在: {unpacked_dir}"},
                    "summary": "添加幻灯片失败：目录不存在"
                }

            # 2. 检查是否为有效的解包目录
            ppt_dir = unpacked_dir / "ppt"
            if not ppt_dir.exists():
                return {
                    "success": False,
                    "data": {"error": "不是有效的解包 PPTX 目录（缺少 ppt/ 目录）"},
                    "summary": "添加幻灯片失败：无效的目录结构"
                }

            # 3. 判断源类型
            if source.startswith("slideLayout") and source.endswith(".xml"):
                result = self._create_from_layout(unpacked_dir, source)
            elif source.startswith("slide") and source.endswith(".xml"):
                result = self._duplicate_slide(unpacked_dir, source)
            else:
                return {
                    "success": False,
                    "data": {"error": f"无效的源文件名: {source}"},
                    "summary": "添加幻灯片失败：源文件名格式错误"
                }

            if not result["success"]:
                return result

            logger.info(
                "add_slide_success",
                unpacked_dir=str(unpacked_dir),
                new_slide=result["data"]["new_slide"],
                source=source
            )

            return result

        except Exception as e:
            logger.error("add_slide_failed", unpacked_dir=unpacked_dir, error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"添加幻灯片失败：{str(e)[:80]}"
            }

    def _create_from_layout(self, unpacked_dir: Path, layout_file: str) -> Dict[str, Any]:
        """从布局模板创建幻灯片"""
        slides_dir = unpacked_dir / "ppt" / "slides"
        rels_dir = slides_dir / "_rels"
        layouts_dir = unpacked_dir / "ppt" / "slideLayouts"

        layout_path = layouts_dir / layout_file
        if not layout_path.exists():
            return {
                "success": False,
                "data": {"error": f"布局文件不存在: {layout_file}"},
                "summary": "添加幻灯片失败：布局文件不存在"
            }

        # 获取下一个幻灯片编号
        next_num = self._get_next_slide_number(slides_dir)
        dest = f"slide{next_num}.xml"
        dest_slide = slides_dir / dest
        dest_rels = rels_dir / f"{dest}.rels"

        # 创建幻灯片 XML
        slide_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr>
    <a:masterClrMapping/>
  </p:clrMapOvr>
</p:sld>'''
        dest_slide.write_text(slide_xml, encoding="utf-8")

        # 创建关系文件
        rels_dir.mkdir(exist_ok=True)
        rels_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/{layout_file}"/>
</Relationships>'''
        dest_rels.write_text(rels_xml, encoding="utf-8")

        # 更新内容类型
        self._add_to_content_types(unpacked_dir, dest)

        # 更新 presentation.xml.rels
        rid = self._add_to_presentation_rels(unpacked_dir, dest)

        # 获取下一个幻灯片 ID
        next_slide_id = self._get_next_slide_id(unpacked_dir)

        # 更新 presentation.xml
        self._add_to_presentation_xml(unpacked_dir, next_slide_id, rid)

        return {
            "success": True,
            "data": {
                "new_slide": dest,
                "slide_number": next_num,
                "source_type": "layout",
                "layout_file": layout_file
            },
            "summary": f"已从布局 {layout_file} 创建幻灯片 {dest}"
        }

    def _duplicate_slide(self, unpacked_dir: Path, source: str) -> Dict[str, Any]:
        """复制现有幻灯片"""
        slides_dir = unpacked_dir / "ppt" / "slides"
        rels_dir = slides_dir / "_rels"

        source_slide = slides_dir / source
        if not source_slide.exists():
            return {
                "success": False,
                "data": {"error": f"源幻灯片不存在: {source}"},
                "summary": "添加幻灯片失败：源幻灯片不存在"
            }

        # 获取下一个幻灯片编号
        next_num = self._get_next_slide_number(slides_dir)
        dest = f"slide{next_num}.xml"
        dest_slide = slides_dir / dest

        source_rels = rels_dir / f"{source}.rels"
        dest_rels = rels_dir / f"{dest}.rels"

        # 复制幻灯片文件
        shutil.copy2(source_slide, dest_slide)

        # 复制关系文件（如果存在）
        if source_rels.exists():
            shutil.copy2(source_rels, dest_rels)

            # 移除备注幻灯片关系
            rels_content = dest_rels.read_text(encoding="utf-8")
            rels_content = re.sub(
                r'\s*<Relationship[^>]*Type="[^"]*notesSlide"[^>]*/>\s*',
                "\n",
                rels_content,
            )
            dest_rels.write_text(rels_content, encoding="utf-8")

        # 更新内容类型
        self._add_to_content_types(unpacked_dir, dest)

        # 更新 presentation.xml.rels
        rid = self._add_to_presentation_rels(unpacked_dir, dest)

        # 获取下一个幻灯片 ID
        next_slide_id = self._get_next_slide_id(unpacked_dir)

        # 更新 presentation.xml
        self._add_to_presentation_xml(unpacked_dir, next_slide_id, rid)

        return {
            "success": True,
            "data": {
                "new_slide": dest,
                "slide_number": next_num,
                "source_type": "slide",
                "source_slide": source
            },
            "summary": f"已复制幻灯片 {source} 为 {dest}"
        }

    def _get_next_slide_number(self, slides_dir: Path) -> int:
        """获取下一个幻灯片编号"""
        existing = [int(m.group(1)) for f in slides_dir.glob("slide*.xml")
                    if (m := re.match(r"slide(\d+)\.xml", f.name))]
        return max(existing) + 1 if existing else 1

    def _add_to_content_types(self, unpacked_dir: Path, dest: str) -> None:
        """添加到内容类型文件"""
        content_types_path = unpacked_dir / "[Content_Types].xml"
        content_types = content_types_path.read_text(encoding="utf-8")

        new_override = f'<Override PartName="/ppt/slides/{dest}" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'

        if f"/ppt/slides/{dest}" not in content_types:
            content_types = content_types.replace("</Types>", f"  {new_override}\n</Types>")
            content_types_path.write_text(content_types, encoding="utf-8")

    def _add_to_presentation_rels(self, unpacked_dir: Path, dest: str) -> str:
        """添加到 presentation.xml.rels"""
        pres_rels_path = unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels"
        pres_rels = pres_rels_path.read_text(encoding="utf-8")

        rids = [int(m) for m in re.findall(r'Id="rId(\d+)"', pres_rels)]
        next_rid = max(rids) + 1 if rids else 1
        rid = f"rId{next_rid}"

        new_rel = f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/{dest}"/>'

        if f"slides/{dest}" not in pres_rels:
            pres_rels = pres_rels.replace("</Relationships>", f"  {new_rel}\n</Relationships>")
            pres_rels_path.write_text(pres_rels, encoding="utf-8")

        return rid

    def _get_next_slide_id(self, unpacked_dir: Path) -> int:
        """获取下一个幻灯片 ID"""
        pres_path = unpacked_dir / "ppt" / "presentation.xml"
        pres_content = pres_path.read_text(encoding="utf-8")
        slide_ids = [int(m) for m in re.findall(r'<p:sldId[^>]*id="(\d+)"', pres_content)]
        return max(slide_ids) + 1 if slide_ids else 256

    def _add_to_presentation_xml(self, unpacked_dir: Path, slide_id: int, rid: str) -> None:
        """添加到 presentation.xml"""
        pres_path = unpacked_dir / "ppt" / "presentation.xml"
        pres_content = pres_path.read_text(encoding="utf-8")

        new_slide_id = f'<p:sldId id="{slide_id}" r:id="{rid}"/>'

        # 查找 <p:sldIdLst> 标签
        if "<p:sldIdLst>" in pres_content:
            # 在 </p:sldIdLst> 前插入
            pres_content = pres_content.replace("</p:sldIdLst>", f"    {new_slide_id}\n  </p:sldIdLst>")
        else:
            # 如果没有 sldIdLst，在 </p:presentation> 前插入
            sld_id_lst = f'  <p:sldIdLst>\n    {new_slide_id}\n  </p:sldIdLst>\n'
            pres_content = pres_content.replace("</p:presentation>", f"{sld_id_lst}</p:presentation>")

        pres_path.write_text(pres_content, encoding="utf-8")

    def _resolve_path(self, path: str) -> Path:
        """解析路径（支持相对路径和绝对路径）"""
        try:
            file_path = Path(path)

            if not file_path.is_absolute():
                file_path = self.working_dir / file_path

            return file_path.resolve()

        except Exception as e:
            logger.error("add_slide_path_resolution_failed", path=path, error=str(e))
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "add_ppt_slide",
            "description": """向 PPT 添加新幻灯片

向解包后的 PPTX 目录添加新幻灯片，支持从布局创建或复制现有幻灯片。

使用场景：
- 批量生成幻灯片
- 基于模板创建演示文稿
- 复制幻灯片内容

注意：
- 必须先使用 unpack_office 解包 PPTX 文件
- 完成后使用 pack_office 重新打包
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "unpacked_dir": {
                        "type": "string",
                        "description": "解包后的 PPTX 目录（使用 unpack_office 生成）。示例：'unpacked/' 或 'D:/work/unpacked/'"
                    },
                    "source": {
                        "type": "string",
                        "description": "源文件名。示例：'slideLayout1.xml'（从布局创建）或 'slide2.xml'（复制幻灯片）"
                    }
                },
                "required": ["unpacked_dir", "source"]
            }
        }

    def is_available(self) -> bool:
        return True


# 创建工具实例
tool = AddSlideTool()
