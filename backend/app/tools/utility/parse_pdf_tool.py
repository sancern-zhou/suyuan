"""
PDF解析工具 - 智能PDF内容提取

支持功能：
- 文本提取：使用PyPDF2或pdfplumber提取文本内容
- OCR识别：自动检测扫描版PDF并使用OCR识别（可选）
- 表格提取：提取PDF中的表格数据
- 图片提取：提取PDF中的图片信息
- 分页读取：支持指定页面范围
- 元数据提取：提取PDF的标题、作者、创建时间等元信息
- 自动保存：将解析结果自动保存为Markdown文档

适用场景：
- 解析文本型PDF（可直接提取文本）
- 解析扫描版PDF（需要OCR识别）
- 提取PDF中的表格数据
- 提取PDF中的图片信息
- 获取PDF元数据

使用示例：
- parse_pdf(path="report.pdf", mode="text")  # 提取文本
- parse_pdf(path="scan.pdf", mode="ocr")     # OCR识别
- parse_pdf(path="data.pdf", mode="table")   # 提取表格
- parse_pdf(path="doc.pdf", pages="1-5")     # 分页读取
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog
from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


class ParsePDFTool(LLMTool):
    """
    PDF解析工具

    支持多种解析模式，自动检测PDF类型，提供智能解析策略
    """

    # 解析模式
    MODE_TEXT = "text"      # 文本提取
    MODE_OCR = "ocr"        # OCR识别
    MODE_TABLE = "table"    # 表格提取
    MODE_IMAGE = "image"    # 图片提取
    MODE_META = "meta"      # 元数据
    MODE_AUTO = "auto"      # 自动检测（默认）

    def __init__(self):
        super().__init__(
            name="parse_pdf",
            description="""解析PDF文件并提取内容

支持多种解析模式：
- text: 提取文本内容（使用PyPDF2或pdfplumber）
- ocr: OCR识别（针对扫描版PDF）
- table: 提取表格数据
- image: 提取图片信息
- meta: 提取元数据（标题、作者等）
- auto: 自动检测PDF类型并选择最佳方法（默认）

特性：
- 自动检测文本型/扫描型PDF
- 支持多种OCR引擎（Qwen/PaddleOCR/Tesseract）
- 支持分页读取
- 提取表格和图片信息
- 获取PDF元数据

使用示例：
- parse_pdf(path="report.pdf")                   # 自动检测
- parse_pdf(path="report.pdf", mode="text")      # 提取文本
- parse_pdf(path="scan.pdf", mode="ocr")         # OCR识别
- parse_pdf(path="data.pdf", mode="table")       # 提取表格
- parse_pdf(path="doc.pdf", pages="1-5")         # 分页读取
- parse_pdf(path="doc.pdf", extract_tables=True) # 提取文本+表格

参数说明：
- path: PDF文件路径（必填）
- mode: 解析模式（默认auto）
- pages: 页面范围（如"1-5", "3"）
- extract_tables: 是否提取表格（默认False）
- extract_images: 是否提取图片信息（默认False）
- ocr_engine: OCR引擎（auto/tesseract/paddleocr/qwen）

限制：
- 文件大小限制：100MB
- 页面限制：最多50页
- OCR需要额外的依赖库

注意：
- 文本型PDF使用text模式最快
- 扫描版PDF需要OCR，处理时间较长
- 提取表格需要安装pdfplumber
- OCR需要配置API密钥或安装本地引擎
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )
        self.max_pages = 50  # 最大处理页数
        self.max_file_size = 100 * 1024 * 1024  # 100MB

        # 文档存储目录
        self.storage_dir = Path("backend_data_registry/parse_pdf_results")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _save_result_to_file(
        self,
        file_path: Path,
        mode: str,
        data: Dict[str, Any]
    ) -> Optional[str]:
        """
        将解析结果保存为Markdown文档

        Args:
            file_path: 原PDF文件路径
            mode: 解析模式
            data: 解析结果数据

        Returns:
            保存的文档文件路径（相对于项目根目录）
        """
        try:
            # 生成文件名：原文件名_模式_时间戳.md
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = file_path.stem.replace(" ", "_").replace("-", "_")
            result_filename = f"{safe_name}_{mode}_{timestamp}.md"
            result_path = self.storage_dir / result_filename

            # 构建Markdown内容
            md_content = self._build_markdown_content(file_path, mode, data)

            # 保存文件
            with open(result_path, 'w', encoding='utf-8') as f:
                f.write(md_content)

            # 返回相对路径
            relative_path = str(result_path)
            logger.info(
                "parse_pdf_result_saved",
                pdf_file=str(file_path.name),
                mode=mode,
                result_file=relative_path,
                content_length=len(md_content)
            )

            return relative_path

        except Exception as e:
            logger.error("save_result_failed", error=str(e))
            return None

    def _build_markdown_content(
        self,
        file_path: Path,
        mode: str,
        data: Dict[str, Any]
    ) -> str:
        """构建Markdown格式的文档内容"""
        lines = []

        # 标题
        lines.append(f"# PDF解析结果\n")
        lines.append(f"**文件**: `{file_path.name}`\n")
        lines.append(f"**路径**: `{file_path}`\n")
        lines.append(f"**解析模式**: {mode}\n")
        lines.append(f"**解析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append("---\n\n")

        # 根据模式添加内容
        pdf_type = data.get("type", "")

        if pdf_type == "pdf_text":
            lines.extend(self._build_text_markdown(data))
        elif pdf_type == "pdf_ocr":
            lines.extend(self._build_ocr_markdown(data))
        elif pdf_type == "pdf_tables":
            lines.extend(self._build_tables_markdown(data))
        elif pdf_type == "pdf_images":
            lines.extend(self._build_images_markdown(data))
        elif pdf_type == "pdf_metadata":
            lines.extend(self._build_metadata_markdown(data))

        return "\n".join(lines)

    def _build_text_markdown(self, data: Dict[str, Any]) -> List[str]:
        """构建文本提取结果的Markdown"""
        lines = []

        lines.append("## 文本提取结果\n")

        # 基本信息
        if "total_pages" in data:
            lines.append(f"- **总页数**: {data['total_pages']}")
        if "pages_processed" in data:
            lines.append(f"- **处理页数**: {data['pages_processed']}")
        if "content_length" in data:
            lines.append(f"- **内容长度**: {data['content_length']} 字符")
        lines.append("")

        # 完整内容
        if "content" in data:
            lines.append("## 完整内容\n")
            lines.append("```")
            lines.append(data["content"])
            lines.append("```")
        lines.append("")

        # 表格信息
        if "table_count" in data and data["table_count"] > 0:
            lines.append(f"## 表格信息\n")
            lines.append(f"- **表格数量**: {data['table_count']}")
            lines.append("")

            if "tables" in data and len(data["tables"]) <= 10:
                # 显示所有表格（最多10个）
                for idx, table in enumerate(data["tables"]):
                    lines.append(f"### 表格 {idx + 1}: 页码{table['page']}\n")
                    lines.append(f"- **行数**: {table['rows']}")
                    lines.append(f"- **列数**: {table['cols']}")
                    lines.append("")

                    # 显示表格数据（Markdown表格格式）
                    if "data" in table and table["data"]:
                        lines.append("| " + " | ".join(str(cell) if cell else "" for cell in table["data"][0]) + " |")
                        lines.append("|" + "|".join(["---"] * len(table["data"][0])) + "|")
                        for row in table["data"]:
                            lines.append("| " + " | ".join(str(cell) if cell else "" for cell in row) + " |")
                        lines.append("")
            else:
                lines.append(f"表格数量过多（{data['table_count']}个），已省略详细显示\n")

        # 图片信息
        if "image_count" in data and data["image_count"] > 0:
            lines.append(f"## 图片信息\n")
            lines.append(f"- **图片数量**: {data['image_count']}")
            lines.append("")

            if "images" in data and len(data["images"]) <= 20:
                lines.append("### 图片列表\n")
                for idx, img in enumerate(data["images"][:20]):
                    lines.append(f"{idx + 1}. **页码{img['page']}**")
                    if img.get("width") and img.get("height"):
                        lines.append(f"   - 尺寸: {img['width']} × {img['height']}")
                    lines.append("")
            else:
                lines.append(f"图片数量过多（{data['image_count']}个），已省略详细显示\n")

        return lines

    def _build_ocr_markdown(self, data: Dict[str, Any]) -> List[str]:
        """构建OCR识别结果的Markdown"""
        lines = []

        lines.append("## OCR识别结果\n")

        # 基本信息
        ocr_engine = data.get("ocr_engine", "unknown")
        lines.append(f"- **OCR引擎**: {ocr_engine}")
        if "pages_processed" in data:
            lines.append(f"- **处理页数**: {data['pages_processed']}")
        if "content_length" in data:
            lines.append(f"- **内容长度**: {data['content_length']} 字符")
        lines.append("")

        # 完整内容
        if "content" in data:
            lines.append("## 识别文本\n")
            lines.append("```")
            lines.append(data["content"])
            lines.append("```")
        lines.append("")

        return lines

    def _build_tables_markdown(self, data: Dict[str, Any]) -> List[str]:
        """构建表格提取结果的Markdown"""
        lines = []

        lines.append("## 表格提取结果\n")

        # 基本信息
        if "pages_processed" in data:
            lines.append(f"- **处理页数**: {data['pages_processed']}")
        if "table_count" in data:
            lines.append(f"- **表格数量**: {data['table_count']}")
        lines.append("")

        # 表格数据
        if "tables" in data and data["tables"]:
            for idx, table in enumerate(data["tables"]):
                lines.append(f"### 表格 {idx + 1}\n")
                lines.append(f"- **页码**: {table['page']}")
                lines.append(f"- **行数**: {table['rows']}")
                lines.append(f"- **列数**: {table['cols']}")
                lines.append("")

                # 显示表格数据（Markdown表格格式）
                if "data" in table and table["data"]:
                    lines.append("| " + " | ".join(str(cell) if cell else "" for cell in table["data"][0]) + " |")
                    lines.append("|" + "|".join(["---"] * len(table["data"][0])) + "|")
                    for row in table["data"]:
                        lines.append("| " + " | ".join(str(cell) if cell else "" for cell in row) + " |")
                    lines.append("")
                lines.append("")

        return lines

    def _build_images_markdown(self, data: Dict[str, Any]) -> List[str]:
        """构建图片信息提取结果的Markdown"""
        lines = []

        lines.append("## 图片信息提取结果\n")

        # 基本信息
        if "pages_processed" in data:
            lines.append(f"- **处理页数**: {data['pages_processed']}")
        if "image_count" in data:
            lines.append(f"- **图片数量**: {data['image_count']}")
        lines.append("")

        # 图片列表
        if "images" in data and data["images"]:
            lines.append("## 图片列表\n")

            # 按页码分组显示
            page_groups = {}
            for img in data["images"]:
                page = img["page"]
                if page not in page_groups:
                    page_groups[page] = []
                page_groups[page].append(img)

            for page in sorted(page_groups.keys()):
                lines.append(f"### 第 {page} 页\n")
                for img in page_groups[page]:
                    lines.append(f"- **索引**: {img['index']}")
                    if img.get("width") and img.get("height"):
                        lines.append(f"  - 尺寸: {img['width']} × {img['height']}")
                    if img.get("x0") is not None:
                        lines.append(f"  - 位置: ({img['x0']:.1f}, {img['y0']:.1f}) → ({img['x1']:.1f}, {img['y1']:.1f})")
                lines.append("")

        return lines

    def _build_metadata_markdown(self, data: Dict[str, Any]) -> List[str]:
        """构建元数据提取结果的Markdown"""
        lines = []

        lines.append("## PDF元数据\n")

        # 基本信息
        if "page_count" in data:
            lines.append(f"- **页数**: {data['page_count']}")
        if "is_encrypted" in data:
            lines.append(f"- **是否加密**: {'是' if data['is_encrypted'] else '否'}")
        lines.append("")

        # PDF元数据
        lines.append("## 文档属性\n")
        if "title" in data and data["title"]:
            lines.append(f"- **标题**: {data['title']}")
        if "author" in data and data["author"]:
            lines.append(f"- **作者**: {data['author']}")
        if "subject" in data and data["subject"]:
            lines.append(f"- **主题**: {data['subject']}")
        if "creator" in data and data["creator"]:
            lines.append(f"- **创建工具**: {data['creator']}")
        if "producer" in data and data["producer"]:
            lines.append(f"- **PDF生成器**: {data['producer']}")
        if "creation_date" in data and data["creation_date"]:
            lines.append(f"- **创建日期**: {data['creation_date']}")
        if "modification_date" in data and data["modification_date"]:
            lines.append(f"- **修改日期**: {data['modification_date']}")

        return lines
        self.max_pages = 50  # 最大处理页数
        self.max_file_size = 100 * 1024 * 1024  # 100MB

    async def execute(
        self,
        path: str,
        mode: str = "auto",
        pages: Optional[str] = None,
        extract_tables: bool = False,
        extract_images: bool = False,
        ocr_engine: str = "auto",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行PDF解析

        Args:
            path: PDF文件路径
            mode: 解析模式（text/ocr/table/image/meta/auto）
            pages: 页面范围（如 "1-5", "3", "10-20"）
            extract_tables: 是否提取表格
            extract_images: 是否提取图片
            ocr_engine: OCR引擎（auto/tesseract/paddleocr/qwen）

        Returns:
            简化格式：{"success": bool, "data": dict, "summary": str}
        """
        try:
            # 1. 验证文件路径
            file_path = Path(path)
            if not file_path.exists():
                return {
                    "success": False,
                    "data": {"error": f"文件不存在: {path}"},
                    "summary": "PDF文件不存在"
                }

            # 2. 检查文件大小
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                return {
                    "success": False,
                    "data": {"error": f"文件过大: {file_size} bytes (最大 {self.max_file_size} bytes)"},
                    "summary": "PDF文件超过100MB限制"
                }

            # 3. 解析页面范围
            page_numbers = self._parse_page_range(pages)

            # 4. 自动检测模式
            if mode == self.MODE_AUTO:
                mode = await self._detect_mode(file_path, page_numbers)

            # 5. 根据模式解析
            if mode == self.MODE_TEXT:
                return await self._extract_text(file_path, page_numbers, extract_tables, extract_images)
            elif mode == self.MODE_OCR:
                return await self._ocr_extract(file_path, page_numbers, ocr_engine)
            elif mode == self.MODE_TABLE:
                return await self._extract_tables(file_path, page_numbers)
            elif mode == self.MODE_IMAGE:
                return await self._extract_images(file_path, page_numbers)
            elif mode == self.MODE_META:
                return await self._extract_metadata(file_path)
            else:
                return {
                    "success": False,
                    "data": {"error": f"不支持的解析模式: {mode}"},
                    "summary": "无效的解析模式"
                }

        except Exception as e:
            logger.error("parse_pdf_failed", path=path, error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"PDF解析失败: {str(e)[:50]}"
            }

    async def _detect_mode(self, file_path: Path, page_numbers: List[int]) -> str:
        """自动检测PDF类型"""
        try:
            # 尝试使用PyPDF2提取文本
            try:
                import PyPDF2
                with open(file_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)

                    # 检查前几页是否有文本
                    pages_to_check = min(3, len(pdf_reader.pages))
                    text_count = 0

                    for i in range(pages_to_check):
                        if i + 1 not in page_numbers:
                            continue
                        page = pdf_reader.pages[i]
                        text = page.extract_text()
                        if text and len(text.strip()) > 50:
                            text_count += 1

                    # 如果有足够的文本，判定为文本型PDF
                    if text_count >= pages_to_check * 0.5:
                        return self.MODE_TEXT
                    else:
                        return self.MODE_OCR

            except ImportError:
                # PyPDF2未安装，尝试pdfplumber
                return self.MODE_TEXT

        except Exception as e:
            logger.warning("detect_mode_failed", error=str(e))
            return self.MODE_TEXT

    async def _extract_text(
        self,
        file_path: Path,
        page_numbers: List[int],
        extract_tables: bool,
        extract_images: bool
    ) -> Dict[str, Any]:
        """提取文本内容"""
        try:
            # 优先使用pdfplumber（更精确）
            try:
                import pdfplumber

                with pdfplumber.open(file_path) as pdf:
                    total_pages = len(pdf.pages)
                    pages_to_process = [p for p in page_numbers if p <= total_pages]

                    if not pages_to_process:
                        return {
                            "success": False,
                            "data": {"error": f"无效的页面范围: {page_numbers} (总页数: {total_pages})"},
                            "summary": "页面范围超出PDF总页数"
                        }

                    # 提取文本
                    text_content = []
                    tables = []
                    images_info = []

                    for page_num in pages_to_process:
                        page = pdf.pages[page_num - 1]

                        # 提取文本
                        text = page.extract_text()
                        if text:
                            text_content.append(f"--- 第 {page_num} 页 ---\n{text}")

                        # 提取表格
                        if extract_tables:
                            page_tables = page.extract_tables()
                            if page_tables:
                                for idx, table in enumerate(page_tables):
                                    tables.append({
                                        "page": page_num,
                                        "index": idx,
                                        "data": table
                                    })

                        # 提取图片信息
                        if extract_images:
                            page_images = page.images
                            if page_images:
                                for img in page_images:
                                    images_info.append({
                                        "page": page_num,
                                        "x0": img.get("x0"),
                                        "y0": img.get("y0"),
                                        "x1": img.get("x1"),
                                        "y1": img.get("y1"),
                                        "width": img.get("width"),
                                        "height": img.get("height")
                                    })

                    # 构建结果
                    content = "\n\n".join(text_content)
                    result_data = {
                        "type": "pdf_text",
                        "file_path": str(file_path),
                        "file_name": file_path.name,
                        "file_size": file_path.stat().st_size,
                        "total_pages": total_pages,
                        "pages_processed": len(pages_to_process),
                        "content": content,
                        "content_length": len(content)
                    }

                    # 添加表格信息
                    if tables:
                        result_data["tables"] = tables
                        result_data["table_count"] = len(tables)

                    # 添加图片信息
                    if images_info:
                        result_data["images"] = images_info
                        result_data["image_count"] = len(images_info)

                    # 保存结果到文件
                    result_file_path = self._save_result_to_file(file_path, "text", result_data)

                    result = {
                        "success": True,
                        "data": result_data,
                        "metadata": {
                            "generator": "parse_pdf"
                        },
                        "summary": f"成功提取PDF文本: {file_path.name} (共 {len(pages_to_process)} 页)"
                    }

                    # 添加文档路径到data中
                    if result_file_path:
                        result["data"]["result_file_path"] = result_file_path
                        result["summary"] += f" → 结果已保存: `{result_file_path}`"

                    return result

            except ImportError:
                # pdfplumber未安装，使用PyPDF2
                import PyPDF2

                with open(file_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    total_pages = len(pdf_reader.pages)
                    pages_to_process = [p for p in page_numbers if p <= total_pages]

                    text_content = []
                    for page_num in pages_to_process:
                        page = pdf_reader.pages[page_num - 1]
                        text = page.extract_text()
                        if text:
                            text_content.append(f"--- 第 {page_num} 页 ---\n{text}")

                    content = "\n\n".join(text_content)

                    result_data = {
                        "type": "pdf_text",
                        "file_path": str(file_path),
                        "file_name": file_path.name,
                        "file_size": file_path.stat().st_size,
                        "total_pages": total_pages,
                        "pages_processed": len(pages_to_process),
                        "content": content,
                        "content_length": len(content),
                        "note": "使用PyPDF2提取（安装pdfplumber可获得更好效果）"
                    }

                    # 保存结果到文件
                    result_file_path = self._save_result_to_file(file_path, "text", result_data)

                    result = {
                        "success": True,
                        "data": result_data,
                        "metadata": {
                            "generator": "parse_pdf"
                        },
                        "summary": f"成功提取PDF文本: {file_path.name} (共 {len(pages_to_process)} 页)"
                    }

                    # 添加文档路径到data中
                    if result_file_path:
                        result["data"]["result_file_path"] = result_file_path
                        result["summary"] += f" → 结果已保存: `{result_file_path}`"

                    return result

        except Exception as e:
            logger.error("extract_text_failed", path=str(file_path), error=str(e))
            raise

    async def _ocr_extract(
        self,
        file_path: Path,
        page_numbers: List[int],
        ocr_engine: str
    ) -> Dict[str, Any]:
        """OCR识别"""
        try:
            # 检查OCR引擎
            if ocr_engine == "auto":
                ocr_engine = await self._detect_ocr_engine()

            if ocr_engine == "qwen":
                return await self._ocr_with_qwen(file_path, page_numbers)
            elif ocr_engine == "paddleocr":
                return await self._ocr_with_paddleocr(file_path, page_numbers)
            elif ocr_engine == "tesseract":
                return await self._ocr_with_tesseract(file_path, page_numbers)
            else:
                return {
                    "success": False,
                    "data": {"error": f"OCR引擎不可用: {ocr_engine}"},
                    "summary": "OCR引擎未安装或配置错误"
                }

        except Exception as e:
            logger.error("ocr_extract_failed", path=str(file_path), error=str(e))
            raise

    async def _detect_ocr_engine(self) -> str:
        """检测可用的OCR引擎"""
        # 优先使用Qwen（从环境变量读取API key）
        api_key = os.getenv("QWEN_VL_API_KEY", "")
        if api_key:
            return "qwen"

        # 尝试PaddleOCR
        try:
            import paddleocr
            return "paddleocr"
        except ImportError:
            pass

        # 尝试Tesseract
        try:
            import pytesseract
            return "tesseract"
        except ImportError:
            pass

        return "none"

    async def _ocr_with_qwen(self, file_path: Path, page_numbers: List[int]) -> Dict[str, Any]:
        """使用Qwen-VL进行OCR识别"""
        try:
            import pdf2image
            import httpx
            import base64

            # 转换PDF为图片
            images = pdf2image.convert_from_path(
                file_path,
                first_page=min(page_numbers),
                last_page=max(page_numbers)
            )

            # API配置（从环境变量读取）
            api_url = os.getenv("QWEN_VL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            api_key = os.getenv("QWEN_VL_API_KEY", "")

            if not api_key:
                return {
                    "success": False,
                    "data": {"error": "未配置QWEN_VL_API_KEY"},
                    "summary": "Qwen OCR API密钥未配置"
                }

            text_content = []
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            # 对每一页进行OCR
            for idx, image in enumerate(images):
                page_num = idx + 1
                if page_num not in page_numbers:
                    continue

                # 转换图片为base64
                import io
                img_buffer = io.BytesIO()
                image.save(img_buffer, format='PNG')
                img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')

                # 调用API
                payload = {
                    "model": os.getenv("OCR_MODEL", "qwen-vl-plus"),
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{img_base64}"}
                                },
                                {"type": "text", "text": "请识别图片中的所有文字内容，保持原有格式和排版。"}
                            ]
                        }
                    ]
                }

                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(f"{api_url}/chat/completions", headers=headers, json=payload)
                    response.raise_for_status()
                    result = response.json()

                # 提取文本
                text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                text_content.append(f"--- 第 {page_num} 页 ---\n{text}")

            content = "\n\n".join(text_content)

            result_data = {
                "type": "pdf_ocr",
                "ocr_engine": "qwen",
                "file_path": str(file_path),
                "file_name": file_path.name,
                "pages_processed": len(page_numbers),
                "content": content,
                "content_length": len(content)
            }

            # 保存结果到文件
            result_file_path = self._save_result_to_file(file_path, "ocr", result_data)

            result = {
                "success": True,
                "data": result_data,
                "metadata": {
                    "generator": "parse_pdf"
                },
                "summary": f"OCR识别成功: {file_path.name} (共 {len(page_numbers)} 页)"
            }

            # 添加文档路径到data中
            if result_file_path:
                result["data"]["result_file_path"] = result_file_path
                result["summary"] += f" → 结果已保存: `{result_file_path}`"

            return result

        except Exception as e:
            logger.error("ocr_qwen_failed", path=str(file_path), error=str(e))
            raise

    async def _ocr_with_paddleocr(self, file_path: Path, page_numbers: List[int]) -> Dict[str, Any]:
        """使用PaddleOCR进行识别"""
        try:
            from paddleocr import PaddleOCR
            import pdf2image

            # 初始化OCR
            ocr = PaddleOCR(use_angle_cls=True, lang='ch')

            # 转换PDF为图片
            images = pdf2image.convert_from_path(
                file_path,
                first_page=min(page_numbers),
                last_page=max(page_numbers)
            )

            text_content = []

            for idx, image in enumerate(images):
                page_num = idx + 1
                if page_num not in page_numbers:
                    continue

                # OCR识别
                result = ocr.ocr(image, cls=True)

                # 提取文本
                page_text = []
                if result and result[0]:
                    for line in result[0]:
                        if line and len(line) >= 2:
                            text_line = line[0]  # 坐标
                            text_content_str = line[1][0]  # 文本内容
                            page_text.append(text_content_str)

                text_content.append(f"--- 第 {page_num} 页 ---\n" + "\n".join(page_text))

            content = "\n\n".join(text_content)

            result_data = {
                "type": "pdf_ocr",
                "ocr_engine": "paddleocr",
                "file_path": str(file_path),
                "file_name": file_path.name,
                "pages_processed": len(page_numbers),
                "content": content,
                "content_length": len(content)
            }

            # 保存结果到文件
            result_file_path = self._save_result_to_file(file_path, "ocr_paddleocr", result_data)

            result = {
                "success": True,
                "data": result_data,
                "metadata": {
                    "generator": "parse_pdf"
                },
                "summary": f"OCR识别成功: {file_path.name} (共 {len(page_numbers)} 页)"
            }

            # 添加文档路径到data中
            if result_file_path:
                result["data"]["result_file_path"] = result_file_path
                result["summary"] += f" → 结果已保存: `{result_file_path}`"

            return result

        except ImportError:
            return {
                "success": False,
                "data": {"error": "PaddleOCR未安装，请运行: pip install paddleocr"},
                "summary": "PaddleOCR未安装"
            }
        except Exception as e:
            logger.error("ocr_paddleocr_failed", path=str(file_path), error=str(e))
            raise

    async def _ocr_with_tesseract(self, file_path: Path, page_numbers: List[int]) -> Dict[str, Any]:
        """使用Tesseract进行OCR识别"""
        try:
            import pdf2image
            import pytesseract
            from PIL import Image

            # 转换PDF为图片
            images = pdf2image.convert_from_path(
                file_path,
                first_page=min(page_numbers),
                last_page=max(page_numbers)
            )

            text_content = []

            for idx, image in enumerate(images):
                page_num = idx + 1
                if page_num not in page_numbers:
                    continue

                # OCR识别
                text = pytesseract.image_to_string(image, lang='chi_sim+eng')
                text_content.append(f"--- 第 {page_num} 页 ---\n{text}")

            content = "\n\n".join(text_content)

            result_data = {
                "type": "pdf_ocr",
                "ocr_engine": "tesseract",
                "file_path": str(file_path),
                "file_name": file_path.name,
                "pages_processed": len(page_numbers),
                "content": content,
                "content_length": len(content)
            }

            # 保存结果到文件
            result_file_path = self._save_result_to_file(file_path, "ocr_tesseract", result_data)

            result = {
                "success": True,
                "data": result_data,
                "metadata": {
                    "generator": "parse_pdf"
                },
                "summary": f"OCR识别成功: {file_path.name} (共 {len(page_numbers)} 页)"
            }

            # 添加文档路径到data中
            if result_file_path:
                result["data"]["result_file_path"] = result_file_path
                result["summary"] += f" → 结果已保存: `{result_file_path}`"

            return result

        except ImportError:
            return {
                "success": False,
                "data": {"error": "依赖库未安装，请运行: pip install pdf2image pytesseract"},
                "summary": "OCR依赖库未安装"
            }
        except Exception as e:
            logger.error("ocr_tesseract_failed", path=str(file_path), error=str(e))
            raise

    async def _extract_tables(self, file_path: Path, page_numbers: List[int]) -> Dict[str, Any]:
        """提取表格"""
        try:
            import pdfplumber

            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                pages_to_process = [p for p in page_numbers if p <= total_pages]

                tables = []
                for page_num in pages_to_process:
                    page = pdf.pages[page_num - 1]
                    page_tables = page.extract_tables()

                    if page_tables:
                        for idx, table in enumerate(page_tables):
                            # 转换表格为可读格式
                            formatted_table = []
                            for row in table:
                                formatted_row = [str(cell) if cell else "" for cell in row]
                                formatted_table.append(formatted_row)

                            tables.append({
                                "page": page_num,
                                "index": idx,
                                "rows": len(formatted_table),
                                "cols": len(formatted_table[0]) if formatted_table else 0,
                                "data": formatted_table
                            })

                result_data = {
                    "type": "pdf_tables",
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "pages_processed": len(pages_to_process),
                    "tables": tables,
                    "table_count": len(tables)
                }

                # 保存结果到文件
                result_file_path = self._save_result_to_file(file_path, "tables", result_data)

                result = {
                    "success": True,
                    "data": result_data,
                    "metadata": {
                        "generator": "parse_pdf"
                    },
                    "summary": f"成功提取表格: {file_path.name} (共 {len(tables)} 个表格)"
                }

                # 添加文档路径到data中
                if result_file_path:
                    result["data"]["result_file_path"] = result_file_path
                    result["summary"] += f" → 结果已保存: `{result_file_path}`"

                return result

        except ImportError:
            return {
                "success": False,
                "data": {"error": "pdfplumber未安装，请运行: pip install pdfplumber"},
                "summary": "pdfplumber未安装"
            }
        except Exception as e:
            logger.error("extract_tables_failed", path=str(file_path), error=str(e))
            raise

    async def _extract_images(self, file_path: Path, page_numbers: List[int]) -> Dict[str, Any]:
        """提取图片信息"""
        try:
            import pdfplumber

            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                pages_to_process = [p for p in page_numbers if p <= total_pages]

                images_info = []
                for page_num in pages_to_process:
                    page = pdf.pages[page_num - 1]
                    page_images = page.images

                    if page_images:
                        for idx, img in enumerate(page_images):
                            images_info.append({
                                "page": page_num,
                                "index": idx,
                                "x0": img.get("x0"),
                                "y0": img.get("y0"),
                                "x1": img.get("x1"),
                                "y1": img.get("y1"),
                                "width": img.get("width"),
                                "height": img.get("height")
                            })

                result_data = {
                    "type": "pdf_images",
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "pages_processed": len(pages_to_process),
                    "images": images_info,
                    "image_count": len(images_info)
                }

                # 保存结果到文件
                result_file_path = self._save_result_to_file(file_path, "images", result_data)

                result = {
                    "success": True,
                    "data": result_data,
                    "metadata": {
                        "generator": "parse_pdf"
                    },
                    "summary": f"成功提取图片信息: {file_path.name} (共 {len(images_info)} 个图片)"
                }

                # 添加文档路径到data中
                if result_file_path:
                    result["data"]["result_file_path"] = result_file_path
                    result["summary"] += f" → 结果已保存: `{result_file_path}`"

                return result

        except ImportError:
            return {
                "success": False,
                "data": {"error": "pdfplumber未安装，请运行: pip install pdfplumber"},
                "summary": "pdfplumber未安装"
            }
        except Exception as e:
            logger.error("extract_images_failed", path=str(file_path), error=str(e))
            raise

    async def _extract_metadata(self, file_path: Path) -> Dict[str, Any]:
        """提取元数据"""
        try:
            import PyPDF2

            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)

                # 基本信息
                metadata = {
                    "type": "pdf_metadata",
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "file_size": file_path.stat().st_size,
                    "page_count": len(pdf_reader.pages),
                    "is_encrypted": pdf_reader.is_encrypted
                }

                # PDF元数据
                pdf_info = pdf_reader.metadata
                if pdf_info:
                    metadata.update({
                        "title": pdf_info.get("/Title", ""),
                        "author": pdf_info.get("/Author", ""),
                        "subject": pdf_info.get("/Subject", ""),
                        "creator": pdf_info.get("/Creator", ""),
                        "producer": pdf_info.get("/Producer", ""),
                        "creation_date": str(pdf_info.get("/CreationDate", "")),
                        "modification_date": str(pdf_info.get("/ModDate", ""))
                    })

                # 添加generator标识
                metadata["generator"] = "parse_pdf"

                # 保存结果到文件
                result_file_path = self._save_result_to_file(file_path, "metadata", metadata)

                result = {
                    "success": True,
                    "data": metadata,
                    "metadata": {
                        "generator": "parse_pdf"
                    },
                    "summary": f"成功提取元数据: {file_path.name}"
                }

                # 添加文档路径到data中
                if result_file_path:
                    result["data"]["result_file_path"] = result_file_path
                    result["summary"] += f" → 结果已保存: `{result_file_path}`"

                return result

        except Exception as e:
            logger.error("extract_metadata_failed", path=str(file_path), error=str(e))
            raise

    def _parse_page_range(self, pages: Optional[str]) -> List[int]:
        """解析页面范围"""
        if pages is None:
            return list(range(1, self.max_pages + 1))

        try:
            pages = pages.strip()

            if pages.isdigit():
                return [int(pages)]

            if '-' in pages:
                parts = pages.split('-')
                if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                    start = int(parts[0].strip())
                    end = int(parts[1].strip())
                    return list(range(start, end + 1))

            return list(range(1, self.max_pages + 1))

        except Exception:
            return list(range(1, self.max_pages + 1))

    def get_function_schema(self) -> Dict[str, Any]:
        """获取Function Calling Schema"""
        return {
            "name": "parse_pdf",
            "description": (
                "解析PDF并提取文本、OCR、表格、图片信息或元数据。"
                "mode默认auto；文本型PDF用text更快，扫描版用ocr；最多50页，文件上限100MB。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "PDF文件路径，绝对或相对路径"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["auto", "text", "ocr", "table", "image", "meta"],
                        "description": "解析模式：auto/text/ocr/table/image/meta",
                        "default": "auto"
                    },
                    "pages": {
                        "type": "string",
                        "description": "页面范围，如'1-5'或'3'；默认最多50页"
                    },
                    "extract_tables": {
                        "type": "boolean",
                        "description": "text模式下是否同时提取表格",
                        "default": False
                    },
                    "extract_images": {
                        "type": "boolean",
                        "description": "text模式下是否提取图片位置信息",
                        "default": False
                    },
                    "ocr_engine": {
                        "type": "string",
                        "enum": ["auto", "qwen", "paddleocr", "tesseract"],
                        "description": "OCR引擎，仅ocr模式有效",
                        "default": "auto"
                    }
                },
                "required": ["path"]
            }
        }

    def is_available(self) -> bool:
        """检查工具是否可用"""
        return True


# 创建工具实例（兼容LLMTool接口）
def create_parse_pdf_tool():
    """创建PDF解析工具实例"""
    return ParsePDFTool()


# 导出
tool = create_parse_pdf_tool()
