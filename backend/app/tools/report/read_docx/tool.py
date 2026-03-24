"""
读取DOCX文档工具

使用python-docx直接读取DOCX文件内容，无需解包
"""

from typing import Dict, Any, Optional
from pathlib import Path
from docx import Document
from docx.table import Table
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


# PDF转换器导入（懒加载避免循环依赖）
def get_pdf_converter():
    """获取PDF转换器实例"""
    try:
        from app.services.pdf_converter import pdf_converter
        return pdf_converter
    except ImportError:
        logger.warning("pdf_converter_not_available")
        return None


class ReadDocxTool(LLMTool):
    """
    读取DOCX文档工具

    功能：
    - 直接读取DOCX文件内容（无需解包）
    - 提取段落和表格
    - 保留文档结构
    """

    def __init__(self):
        super().__init__(
            name="read_docx",
            description="读取DOCX文档内容（直接读取，无需解包）。参数: path(str), max_paragraphs(int, 可选, 默认100), include_tables(bool, 可选, 默认true)",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        self.function_schema = {
            "name": "read_docx",
            "description": "读取DOCX文档内容，提取段落和表格结构",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "DOCX文件路径"
                    },
                    "max_paragraphs": {
                        "type": "integer",
                        "description": "最大段落数（默认100，用于控制token消耗）",
                        "default": 100
                    },
                    "include_tables": {
                        "type": "boolean",
                        "description": "是否包含表格内容（默认true）",
                        "default": True
                    }
                },
                "required": ["path"]
            }
        }

    async def execute(
        self,
        path: str,
        max_paragraphs: int = 100,
        include_tables: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行DOCX文档读取

        Args:
            path: DOCX文件路径
            max_paragraphs: 最大段落数
            include_tables: 是否包含表格

        Returns:
            读取结果
        """
        try:
            file_path = Path(path)

            # 验证文件存在
            if not file_path.exists():
                return {
                    "success": False,
                    "data": {"error": f"文件不存在: {path}"},
                    "summary": "文件不存在"
                }

            # 验证文件格式
            if file_path.suffix.lower() != ".docx":
                return {
                    "success": False,
                    "data": {"error": "只支持DOCX格式文件"},
                    "summary": "文件格式不支持"
                }

            # 使用python-docx读取文档
            doc = Document(str(file_path))

            # 提取内容（保持段落和表格的原始顺序）
            content_parts = []
            paragraph_count = 0  # 统计非空段落数
            table_count = 0
            image_count = 0  # 统计图片数量

            # 使用 iter_inner_content() 按原始顺序遍历段落和表格
            from docx.table import Table
            from docx.text.paragraph import Paragraph

            for item in doc.iter_inner_content():
                if paragraph_count >= max_paragraphs:
                    break

                if isinstance(item, Paragraph):
                    # 处理段落
                    text = item.text.strip()
                    if text:
                        # 检查是否是标题
                        if item.style and item.style.name.startswith("Heading"):
                            level = item.style.name.replace("Heading ", "")
                            try:
                                level_int = int(level)
                                content_parts.append(f"{'#' * level_int} {text}")
                            except ValueError:
                                content_parts.append(text)
                        else:
                            content_parts.append(text)
                        paragraph_count += 1

                elif isinstance(item, Table) and include_tables:
                    # 处理表格
                    if table_count >= 20:  # 限制表格数量
                        break

                    table_text = self._extract_table_text(item)
                    if table_text:
                        content_parts.append(table_text)
                        table_count += 1

            # 统计段落中嵌入的图片
            for para in doc.paragraphs:
                for run in para.runs:
                    if run._element.xpath('.//pic:pic'):
                        image_count += 1

            # 构建结果
            content = "\n\n".join(content_parts)

            # 构建摘要信息
            summary_parts = [f"{paragraph_count}个段落", f"{table_count}个表格"]
            if image_count > 0:
                summary_parts.append(f"{image_count}个图片")

            result_data = {
                "type": "docx",
                "content": content,
                "path": str(file_path),
                "file_name": file_path.name,
                "file_size": file_path.stat().st_size,
                "paragraph_count": paragraph_count,
                "table_count": table_count,
                "image_count": image_count,
                "has_images": image_count > 0,
                "total_paragraphs": len(doc.paragraphs),
                "total_tables": len(doc.tables)
            }

            # 如果有图片，添加提示信息
            if image_count > 0:
                result_data["image_note"] = "文档" + (f"包含 {image_count} 张图片。" if image_count > 1 else "包含图片。")
                result_data["image_suggestion"] = "如需提取图片内容，请使用 unpack_office 工具解包文档后，使用 analyze_image 工具分析图片。"

            # 生成PDF预览
            try:
                converter = get_pdf_converter()
                if converter:
                    pdf_preview = await converter.convert_to_pdf(str(file_path))
                    result_data["pdf_preview"] = pdf_preview
                    logger.info(
                        "read_docx_pdf_generated",
                        pdf_id=pdf_preview["pdf_id"],
                        pdf_url=pdf_preview["pdf_url"]
                    )
            except Exception as pdf_error:
                logger.warning("read_docx_pdf_conversion_failed", error=str(pdf_error))

            result = {
                "success": True,
                "data": result_data,
                "summary": f"读取成功: {file_path.name} ({', '.join(summary_parts)})",
                "metadata": {
                    "generator": "read_docx",
                    "tool_name": "read_docx"
                }
            }

            logger.info(
                "docx_read_success",
                path=str(file_path),
                paragraphs=paragraph_count,
                tables=table_count,
                images=image_count
            )

            return result

        except Exception as e:
            logger.error(
                "read_docx_failed",
                path=path,
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"读取失败: {str(e)[:50]}"
            }

    def _extract_table_text(self, table: Table) -> str:
        """从表格提取文本（完整保留内容）"""
        try:
            lines = []
            col_count = 0

            for row_idx, row in enumerate(table.rows):
                cells = []
                for cell in row.cells:
                    # 提取文本并处理换行符
                    text = cell.text.strip()
                    # 替换换行符为空格，保持内容在同一行
                    text = text.replace('\n', ' ').replace('\r', '').strip()
                    # 移除多余空格
                    text = ' '.join(text.split())
                    # ✅ 完整保留内容，不再限制字符长度
                    cells.append(text)

                line = " | ".join(cells)
                lines.append(line)

                # 记录列数（以第一行为准）
                if row_idx == 0:
                    col_count = len(cells)

            if lines and col_count > 0:
                # 添加表头分隔符（与列数一致）
                separator = " | ".join(["---"] * col_count)
                return "\n".join([lines[0], separator] + lines[1:])

            return ""

        except Exception as e:
            logger.warning("extract_table_failed", error=str(e))
            return "[表格解析失败]"
