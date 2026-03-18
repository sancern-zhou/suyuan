"""
ReadFile 工具 - 智能文件读取（支持多种格式和模式）

让 LLM 能够读取本地文件系统中的文件：
- 文本文件：直接返回内容
- 图片文件：自动调用 Vision API 进行内容分析（智能模式）
- Word XML：智能分层读取（自动推断最优模式）⭐ 新增

智能分层策略（Word XML）：
- 系统自动检测文件类型和大小
- 根据任务自动选择最优读取模式
- LLM 可通过参数或自然语言表达意图覆盖默认行为

三种模式：
1. text（纯文本）：只提取文字内容，最节省 tokens
2. structured（结构化）：保留标题、表格等结构，~80% 压缩
3. raw（原始）：完整 XML，用于精确编辑

LLM 自主决策示例：
- "查看这个文档" → 自动使用 structured 模式
- "修改标题样式" → 自动使用 raw 模式
- "提取所有文字" → 自动使用 text 模式
"""
import os
import base64
from pathlib import Path
from typing import Dict, Any, Optional
from app.tools.base.tool_interface import LLMTool, ToolCategory
import structlog

logger = structlog.get_logger()


class ReadFileTool(LLMTool):
    """
    文件读取工具（支持图片）

    功能：
    - 读取文本文件内容
    - 读取图片文件并转换为 base64
    - 自动检测文件类型
    """

    # 支持的图片格式
    IMAGE_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'
    }

    # 支持的 PDF 格式
    PDF_EXTENSIONS = {'.pdf'}

    # 支持的图片格式
    IMAGE_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'
    }

    # 支持的 PDF 格式
    PDF_EXTENSIONS = {'.pdf'}

    def __init__(self):
        super().__init__(
            name="read_file",
            description="""读取文件内容（统一文件读取入口，自动识别类型并优化）

特性：
- 文本文件：直接返回文本内容
- 图片文件：自动调用 Vision API 分析图片内容（可关闭）
- PDF 文件：提取文本内容，支持指定页面范围
- Word XML：智能分层读取（根据文件大小自动选择模式）⭐ 新增
- 目录列表：查看目录中的文件和子目录
- 自动检测文件类型并智能处理

Word XML 读取模式（完全由 LLM 通过参数控制）：

默认模式（无需参数）：
• 小文档（<100KB）：structured 模式（保留标题、表格等结构）
• 大文档（≥100KB）：text 模式（只提取文字，最节省 tokens）

LLM 显式控制（高级场景）：
• raw_mode=True：返回完整原始 XML（用于精确编辑格式）
• include_formatting=True：强制使用 structured 模式（保留结构）
• max_paragraphs=N：限制读取段落数（进一步节省 tokens）

使用场景：
- 读取文本文件（代码、配置、日志等）
- 读取并分析图片（图表、文档截图、照片等）
- 读取 PDF 文档（支持指定页面范围）
- 读取 Word 文档内容（系统根据文件大小自动选择）
- 精确编辑 Word 文档（设置 raw_mode=True）
- 查看工作目录中的文件内容

示例：
- read_file(path="D:/work_dir/data.txt")                    # 文本文件
- read_file(path="D:/work_dir/chart.png")                   # 图片文件（自动分析）
- read_file(path="D:/work_dir/report.pdf")                  # PDF 文件（全部页面）
- read_file(path="D:/work_dir/report.pdf", pages="1-5")     # PDF 文件（第 1-5 页）
- read_file(path="D:/work_dir/document.xml")                # Word XML（自动根据文件大小选择）
- read_file(path="D:/work_dir/document.xml", raw_mode=True) # Word XML（完整 XML，用于编辑）
- read_file(path="D:/work_dir")                             # 查看目录内容
- read_file(path="D:/work_dir/doc.png", analysis_type="ocr")  # OCR识别
- read_file(path="D:/work_dir/photo.jpg", auto_analyze=False)  # 只读取不分析

参数说明：
- path: 文件或目录路径（必填）
- pages: PDF 页面范围（如 "1-5", "3", "10-20"），仅对 PDF 文件有效
- auto_analyze: 是否自动分析图片（默认 True）
- analysis_type: 图片分析类型（ocr/describe/chart/analyze，默认 analyze）
- encoding: 文本文件编码（默认 utf-8）
- raw_mode: 是否返回原始内容（Word XML 专用，默认 False）。设置 True 返回完整 XML
- include_formatting: 是否保留格式信息（Word XML 专用，默认 False）。设置 True 保留结构
- max_paragraphs: 最大段落数（Word XML 专用，默认不限制）。用于控制读取量

限制：
- 图片大小限制：5MB
- PDF 页面限制：最多 20 页（使用 pages 参数指定范围）
- 工作目录限制：D:/溯源/ 及其子目录

注意：
- 图片文件会自动进行内容分析，分析结果以文本形式返回
- PDF 文件超过 10 页时，建议使用 pages 参数指定范围
- Word XML 模式完全由 LLM 通过参数控制，系统不自动推断用户意图
- 不返回 base64 数据（避免 token 浪费）
- 如需手动控制图片分析，设置 auto_analyze=False
""",
            category=ToolCategory.QUERY,
            version="2.0.0",
            requires_context=False
        )

        # 工作目录限制
        self.working_dir = Path.cwd().parent  # D:\溯源\ 或 /opt/app/ 等
        self.max_image_size = 5 * 1024 * 1024  # 5MB

    async def execute(
        self,
        path: str,
        encoding: str = "utf-8",
        auto_analyze: bool = True,
        analysis_type: str = "analyze",
        pages: Optional[str] = None,
        raw_mode: bool = False,
        include_formatting: bool = False,
        max_paragraphs: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        读取文件内容（智能分层策略）

        Args:
            path: 文件路径（绝对路径或相对路径）
            encoding: 文本文件编码（默认 utf-8）
            auto_analyze: 是否自动分析图片（默认 True）
            analysis_type: 图片分析类型（ocr/describe/chart/analyze，默认 analyze）
            pages: PDF 页面范围（如 "1-5", "3", "10-20"），仅对 PDF 文件有效
            raw_mode: 是否返回原始内容（Word XML 专用，默认 False）
            include_formatting: 是否保留格式信息（Word XML 专用，默认 False）
            max_paragraphs: 最大段落数（Word XML 专用，默认不限制）

        Returns:
            {
                "status": "success|failed",
                "success": bool,
                "data": {
                    "type": "text|image|pdf|word_xml",
                    "content": str,  # 文本内容
                    "format": str,  # 文件格式
                    "size": int,    # 文件大小
                    "mode": str,    # 读取模式（text/structured/raw，仅 Word XML）
                    "analysis": dict  # 图片分析结果（仅图片文件）
                },
                "metadata": {...},
                "summary": str
            }
        """
        try:
            # 1. 解析文件路径
            file_path = self._resolve_path(path)
            if not file_path:
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"文件路径无效或超出工作目录范围: {path}",
                    "summary": f"❌ 无法访问文件: {path}"
                }

            # 2. 检查文件是否存在
            if not file_path.exists():
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"文件不存在: {path}",
                    "summary": f"❌ 文件不存在: {path}"
                }

            # 2.5. 检查是否为目录
            if file_path.is_dir():
                # 列出目录内容
                try:
                    items = list(file_path.iterdir())
                    item_list = []
                    for item in sorted(items, key=lambda x: (not x.is_dir(), x.name)):
                        item_type = "DIR " if item.is_dir() else "FILE"
                        item_list.append(f"{item_type} {item.name}")

                    content = "\n".join(item_list) if item_list else "(空目录)"
                    return {
                        "status": "success",
                        "success": True,
                        "data": {
                            "type": "directory",
                            "content": content,
                            "path": str(file_path),
                            "item_count": len(items)
                        },
                        "metadata": {
                            "schema_version": "v2.0",
                            "generator": "read_file",
                            "file_type": "directory"
                        },
                        "summary": f"📁 目录内容: {file_path.name} ({len(items)} 项)"
                    }
                except Exception as e:
                    return {
                        "status": "failed",
                        "success": False,
                        "error": f"无法列出目录内容: {str(e)}",
                        "summary": f"❌ 无法访问目录: {file_path.name}"
                    }

            # 3. 获取文件信息
            file_size = file_path.stat().st_size
            file_ext = file_path.suffix.lower()

            # 4. 判断文件类型
            is_image = file_ext in self.IMAGE_EXTENSIONS
            is_pdf = file_ext in self.PDF_EXTENSIONS
            is_word_xml = self._is_word_xml(file_path)

            if is_image:
                # 读取图片文件（可选自动分析）
                return await self._read_image(
                    file_path,
                    file_size,
                    auto_analyze=auto_analyze,
                    analysis_type=analysis_type
                )
            elif is_pdf:
                # 读取 PDF 文件
                return await self._read_pdf(file_path, file_size, pages)
            elif is_word_xml:
                # ⭐ 读取 Word XML（智能分层策略）
                return await self._read_word_xml(
                    file_path,
                    file_size,
                    raw_mode=raw_mode,
                    include_formatting=include_formatting,
                    max_paragraphs=max_paragraphs
                )
            else:
                # 读取文本文件
                return await self._read_text(file_path, encoding, file_size)

        except Exception as e:
            logger.error("read_file_failed", path=path, error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "summary": f"❌ 读取文件失败: {str(e)[:50]}"
            }

    async def _read_image(
        self,
        file_path: Path,
        file_size: int,
        auto_analyze: bool = True,
        analysis_type: str = "analyze"
    ) -> Dict[str, Any]:
        """读取图片文件（自动分析，不返回 base64）

        优化说明：
        - base64 只在 analyze_image 内部使用（调用视觉模型 API）
        - 不返回 base64 给 LLM，避免 token 浪费
        - 只返回分析结果文本和图片元信息
        """
        try:
            # 检查文件大小
            if file_size > self.max_image_size:
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"图片文件过大: {file_size} bytes (最大 {self.max_image_size} bytes)",
                    "summary": f"❌ 图片过大，超过5MB限制"
                }

            # 获取图片格式
            file_ext = file_path.suffix[1:]  # 去掉点号

            # 构建基础结果（不包含 base64 content）
            result = {
                "status": "success",
                "success": True,
                "data": {
                    "type": "image",
                    "format": file_ext,
                    "size": file_size,
                    "path": str(file_path)
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "read_file",
                    "file_type": "image"
                }
            }

            # ✨ 自动分析图片（默认开启）
            if auto_analyze:
                logger.info("auto_analyzing_image", path=str(file_path), type=analysis_type)

                try:
                    # 导入 AnalyzeImage 工具（延迟导入避免循环依赖）
                    from app.tools.utility.analyze_image_tool import AnalyzeImageTool

                    # 创建分析工具实例
                    analyze_tool = AnalyzeImageTool()

                    # 调用分析工具（analyze_image 内部会自己读取文件并转换为 base64）
                    analyze_result = await analyze_tool.execute(
                        path=str(file_path),
                        operation=analysis_type
                    )

                    if analyze_result.get('success'):
                        # 将分析结果添加到数据中
                        result['data']['analysis'] = analyze_result['data']['analysis']
                        result['data']['operation'] = analyze_result['data']['operation']

                        # 更新摘要信息
                        summary = f"✅ 读取并分析图片成功: {file_path.name} ({file_size} bytes, {file_ext})"
                        if analysis_type != "analyze":
                            summary += f" [{analysis_type}]"
                        result['summary'] = summary

                        logger.info("auto_analyze_success", path=str(file_path))
                    else:
                        # 分析失败
                        result['data']['analysis_error'] = analyze_result.get('error', '分析失败')
                        result['summary'] = f"✅ 读取图片成功（分析失败）: {file_path.name}"
                        logger.warning("auto_analyze_failed", path=str(file_path), error=analyze_result.get('error'))

                except ImportError:
                    # AnalyzeImage 工具不可用
                    result['data']['analysis_error'] = "AnalyzeImage 工具不可用"
                    result['summary'] = f"✅ 读取图片成功（分析工具不可用）: {file_path.name}"
                    logger.warning("analyze_image_unavailable", path=str(file_path))

                except Exception as e:
                    # 分析过程出错
                    result['data']['analysis_error'] = str(e)
                    result['summary'] = f"✅ 读取图片成功（分析出错）: {file_path.name}"
                    logger.error("auto_analyze_error", path=str(file_path), error=str(e))
            else:
                # 不自动分析（只返回图片信息）
                result['summary'] = f"✅ 读取图片信息: {file_path.name} ({file_size} bytes, {file_ext})"

            return result

        except Exception as e:
            logger.error("read_image_failed", path=str(file_path), error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "summary": f"❌ 读取图片失败: {str(e)[:50]}"
            }

    async def _read_text(
        self,
        file_path: Path,
        encoding: str,
        file_size: int
    ) -> Dict[str, Any]:
        """读取文本文件（返回完整内容）"""
        try:
            # 读取文本内容（完全不截断，依赖上下文压缩策略）
            content = file_path.read_text(encoding=encoding)

            return {
                "status": "success",
                "success": True,
                "data": {
                    "type": "text",
                    "format": file_path.suffix[1:] if file_path.suffix else "txt",
                    "content": content,  # 完整内容，不截断
                    "size": file_size,
                    "path": str(file_path)
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "read_file",
                    "file_type": "text",
                    "encoding": encoding
                },
                "summary": f"✅ 读取文件成功: {file_path.name} ({file_size} bytes)"
            }

        except UnicodeDecodeError:
            return {
                "status": "failed",
                "success": False,
                "error": f"编码错误（尝试使用 encoding='gbk' 或 encoding='latin-1'）",
                "summary": f"❌ 文本编码错误: {file_path.name}"
            }
        except Exception as e:
            logger.error("read_text_failed", path=str(file_path), error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "summary": f"❌ 读取文件失败: {str(e)[:50]}"
            }

    async def _read_pdf(
        self,
        file_path: Path,
        file_size: int,
        pages: Optional[str] = None
    ) -> Dict[str, Any]:
        """读取 PDF 文件

        Args:
            file_path: PDF 文件路径
            file_size: 文件大小
            pages: 页面范围（如 "1-5", "3", "10-20"），None 表示全部页面

        Returns:
            包含 PDF 文本内容的字典
        """
        try:
            # 尝试导入 PyPDF2
            try:
                import PyPDF2
            except ImportError:
                return {
                    "status": "failed",
                    "success": False,
                    "error": "PyPDF2 未安装，请运行: pip install PyPDF2",
                    "summary": f"❌ 缺少 PDF 支持库"
                }

            # 打开 PDF 文件
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                total_pages = len(pdf_reader.pages)

                # 解析页面范围
                page_numbers = self._parse_page_range(pages, total_pages)

                if page_numbers is None:
                    return {
                        "status": "failed",
                        "success": False,
                        "error": f"无效的页面范围: {pages}",
                        "summary": f"❌ 页面范围格式错误"
                    }

                # 检查页面数量限制（最大 20 页）
                if len(page_numbers) > 20:
                    return {
                        "status": "failed",
                        "success": False,
                        "error": f"页面数量超过限制（{len(page_numbers)} 页），最多支持 20 页。请使用 pages 参数指定范围，如 pages='1-20'",
                        "summary": f"❌ PDF 页面过多（{len(page_numbers)} 页，限制 20 页）"
                    }

                # 提取文本
                text_content = []
                for page_num in page_numbers:
                    try:
                        page = pdf_reader.pages[page_num - 1]  # 转换为 0-based 索引
                        text = page.extract_text()
                        text_content.append(f"--- Page {page_num} ---\n{text}")
                    except Exception as e:
                        logger.warning("pdf_page_extract_failed", page=page_num, error=str(e))
                        text_content.append(f"--- Page {page_num} ---\n(提取失败: {str(e)})")

                content = "\n\n".join(text_content)

                return {
                    "status": "success",
                    "success": True,
                    "data": {
                        "type": "pdf",
                        "format": "pdf",
                        "content": content,
                        "size": file_size,
                        "path": str(file_path),
                        "total_pages": total_pages,
                        "pages_read": len(page_numbers),
                        "page_range": pages or f"1-{total_pages}"
                    },
                    "metadata": {
                        "schema_version": "v2.0",
                        "generator": "read_file",
                        "file_type": "pdf"
                    },
                    "summary": f"✅ 读取 PDF 成功: {file_path.name} (第 {page_numbers[0]}-{page_numbers[-1]} 页，共 {len(page_numbers)} 页)"
                }

        except Exception as e:
            logger.error("read_pdf_failed", path=str(file_path), error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "summary": f"❌ 读取 PDF 失败: {str(e)[:50]}"
            }

    def _parse_page_range(self, pages: Optional[str], total_pages: int) -> Optional[list]:
        """解析页面范围字符串

        Args:
            pages: 页面范围字符串（如 "1-5", "3", "10-20"）
            total_pages: PDF 总页数

        Returns:
            页码列表（1-based），如果格式错误返回 None
        """
        if pages is None:
            # 没有指定范围，返回所有页面
            return list(range(1, total_pages + 1))

        try:
            pages = pages.strip()

            # 单页：如 "3"
            if pages.isdigit():
                page_num = int(pages)
                if 1 <= page_num <= total_pages:
                    return [page_num]
                else:
                    return None

            # 范围：如 "1-5"
            if '-' in pages:
                parts = pages.split('-')
                if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                    start = int(parts[0].strip())
                    end = int(parts[1].strip())

                    if 1 <= start <= end <= total_pages:
                        return list(range(start, end + 1))

            return None

        except Exception:
            return None

    def _is_word_xml(self, file_path: Path) -> bool:
        """检测是否是 Word XML 文件（document.xml）

        Args:
            file_path: 文件路径

        Returns:
            是否是 Word XML 文件
        """
        # 检查文件名是否是 document.xml
        if file_path.name != "document.xml":
            return False

        # 检查是否在 word 目录下
        if "word" not in file_path.parts:
            return False

        # 检查父目录是否是解包的 Office 文档结构
        # 典型结构: unpacked_xxx/word/document.xml
        try:
            # 检查是否存在 _rels 目录（Office 文档特征）
            parent_dir = file_path.parent.parent  # word 的父目录
            rels_dir = parent_dir / "_rels"
            if rels_dir.exists():
                return True

            # 备选检查：文件内容特征
            if file_path.exists():
                content_head = file_path.read_text(encoding='utf-8', errors='ignore')[:1000]
                if 'w:document' in content_head or 'http://schemas.openxmlformats.org' in content_head:
                    return True

        except Exception:
            pass

        return False

    async def _read_word_xml(
        self,
        file_path: Path,
        file_size: int,
        raw_mode: bool = False,
        include_formatting: bool = False,
        max_paragraphs: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        读取 Word XML 文件（完全由参数控制，不进行意图检测）

        模式选择逻辑（按优先级）：
        1. raw_mode=True → 返回完整原始 XML
        2. include_formatting=True → 返回结构化内容
        3. 文件大小 < 100KB → structured 模式（保留结构）
        4. 文件大小 >= 100KB → text 模式（节省 tokens）

        ⚠️ 重要：系统不会根据用户问题内容自动推断意图。
        LLM 必须通过参数明确指定所需模式。

        Args:
            file_path: Word XML 文件路径
            file_size: 文件大小
            raw_mode: 是否返回原始 XML（默认 False）
            include_formatting: 是否保留格式信息（默认 False）
            max_paragraphs: 最大段落数（默认不限制）

        Returns:
            读取结果字典
        """
        try:
            logger.info(
                "reading_word_xml",
                path=str(file_path),
                size=file_size,
                raw_mode=raw_mode,
                include_formatting=include_formatting,
                max_paragraphs=max_paragraphs
            )

            # 模式 1：强制返回原始 XML
            if raw_mode:
                logger.info("word_xml_raw_mode", path=str(file_path))
                return await self._read_raw_word_xml(file_path, file_size)

            # 模式 2：保留格式信息的结构化内容
            if include_formatting:
                logger.info("word_xml_structured_mode", path=str(file_path))
                return await self._extract_structured_from_word_xml(
                    file_path,
                    file_size,
                    max_paragraphs=max_paragraphs
                )

            # 模式 3：自动推断（根据文件大小）
            # 小文件：structured 模式（保留结构）
            # 大文件：text 模式（节省 tokens）
            if file_size < 100_000:  # < 100KB
                logger.info("word_xml_auto_structured", size=file_size)
                return await self._extract_structured_from_word_xml(
                    file_path,
                    file_size,
                    max_paragraphs=max_paragraphs
                )
            else:  # >= 100KB
                logger.info("word_xml_auto_text", size=file_size)
                return await self._extract_text_from_word_xml(
                    file_path,
                    file_size,
                    max_paragraphs=max_paragraphs
                )

        except Exception as e:
            logger.error("read_word_xml_failed", path=str(file_path), error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "summary": f"❌ 读取 Word XML 失败: {str(e)[:50]}"
            }

    async def _read_raw_word_xml(self, file_path: Path, file_size: int) -> Dict[str, Any]:
        """读取原始 Word XML 内容（用于精确编辑）

        Args:
            file_path: 文件路径
            file_size: 文件大小

        Returns:
            原始 XML 内容
        """
        try:
            content = file_path.read_text(encoding='utf-8')

            return {
                "status": "success",
                "success": True,
                "data": {
                    "type": "word_xml",
                    "mode": "raw",
                    "format": "xml",
                    "content": content,  # 完整原始 XML
                    "size": file_size,
                    "path": str(file_path)
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "read_file",
                    "file_type": "word_xml",
                    "read_mode": "raw"
                },
                "summary": f"✅ 读取 Word XML 成功（原始模式）: {file_path.name} ({file_size} bytes)"
            }

        except Exception as e:
            logger.error("read_raw_word_xml_failed", path=str(file_path), error=str(e))
            raise

    async def _extract_text_from_word_xml(
        self,
        file_path: Path,
        file_size: int,
        max_paragraphs: Optional[int] = None
    ) -> Dict[str, Any]:
        """从 Word XML 提取纯文本（最节省 tokens）

        使用 LobsterAI 的递归文本提取方式：
        - 只提取 <w:t> 标签内的文本
        - 跳过空白节点
        - 压缩率：~90%

        Args:
            file_path: 文件路径
            file_size: 文件大小
            max_paragraphs: 最大段落数

        Returns:
            提取的纯文本内容
        """
        try:
            from defusedxml import minidom

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            doc = minidom.parseString(content)

            # 提取所有 w:t 标签的文本
            text_parts = []
            paragraph_count = 0

            for elem in doc.getElementsByTagName('w:t'):
                if max_paragraphs and paragraph_count >= max_paragraphs:
                    break

                if elem.firstChild and elem.firstChild.nodeValue.strip():
                    text_parts.append(elem.firstChild.nodeValue.strip())
                    paragraph_count += 1

            result = "\n".join(text_parts)

            return {
                "status": "success",
                "success": True,
                "data": {
                    "type": "word_xml",
                    "mode": "text",
                    "format": "plain_text",
                    "content": result,
                    "size": file_size,
                    "path": str(file_path),
                    "original_size": file_size,
                    "extracted_size": len(result.encode('utf-8')),
                    "compression_ratio": f"{(1 - len(result.encode('utf-8')) / file_size) * 100:.1f}%"
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "read_file",
                    "file_type": "word_xml",
                    "read_mode": "text",
                    "paragraph_count": paragraph_count
                },
                "summary": f"✅ 提取纯文本成功: {file_path.name} ({paragraph_count} 个文本片段，压缩 ~90%)"
            }

        except ImportError:
            logger.warning("defusedxml_not_installed")
            return {
                "status": "failed",
                "success": False,
                "error": "defusedxml 未安装，请运行: pip install defusedxml",
                "summary": "❌ 缺少 XML 解析库"
            }
        except Exception as e:
            logger.error("extract_text_from_word_xml_failed", path=str(file_path), error=str(e))
            raise

    async def _extract_structured_from_word_xml(
        self,
        file_path: Path,
        file_size: int,
        max_paragraphs: Optional[int] = None
    ) -> Dict[str, Any]:
        """从 Word XML 提取结构化内容（保留标题、表格等）

        保留关键结构信息，压缩冗余标签：
        - 标题层级（# ## ###）
        - 表格结构
        - 段落文本
        - 图片引用

        压缩率：~80%

        ⭐ 重构说明（2025-02-24）：
        - 改变遍历策略：从"遍历所有段落"改为"遍历 body 的直接子元素"
        - 解决问题：表格单元格内的段落不再被重复提取
        - 性能优化：O(n) 复杂度，只遍历一次顶层元素
        - 逻辑清晰：按元素类型分发，表格和段落完全分离

        Args:
            file_path: 文件路径
            file_size: 文件大小
            max_paragraphs: 最大元素数（包括表格、段落、图片等）

        Returns:
            结构化文本内容
        """
        try:
            from defusedxml import minidom

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            doc = minidom.parseString(content)

            # 获取 body 元素
            body_elements = doc.getElementsByTagName('w:body')
            if not body_elements:
                logger.warning("word_xml_no_body_element", path=str(file_path))
                return {
                    "status": "failed",
                    "success": False,
                    "error": "Word XML 缺少 w:body 元素",
                    "summary": "❌ 文档格式错误"
                }

            body = body_elements[0]

            structured_parts = []
            element_count = 0

            # 遍历 body 的直接子元素（不递归）
            for child in body.childNodes:
                # 检查元素数量限制
                if max_paragraphs and element_count >= max_paragraphs:
                    break

                # 跳过非元素节点（如文本节点、注释等）
                if child.nodeType != child.ELEMENT_NODE:
                    continue

                tag_name = child.tagName

                # 处理表格（w:tbl 与 w:p 平级，在 body 下）
                if tag_name == 'w:tbl':
                    table_text = self._extract_table_text(child)
                    if table_text and table_text != "[空表格]":
                        structured_parts.append(table_text)
                        element_count += 1
                    continue

                # 处理段落（w:p）
                if tag_name == 'w:p':
                    # 检测标题样式
                    style_elems = child.getElementsByTagName('w:pStyle')
                    if style_elems:
                        style_val = style_elems[0].getAttribute('w:val')
                        if style_val in ['1', '2', '3', '4', '5']:
                            level = int(style_val)
                            text = self._get_paragraph_text(child)
                            if text:
                                structured_parts.append(f"{'#' * level} {text}")
                                element_count += 1
                            continue

                    # 检测图片
                    drawings = child.getElementsByTagName('a:blip')
                    if drawings:
                        r_id = drawings[0].getAttribute('r:embed')
                        structured_parts.append(f"[图片引用: {r_id}]")
                        element_count += 1
                        continue

                    # 普通段落
                    text = self._get_paragraph_text(child)
                    if text.strip():
                        structured_parts.append(text)
                        element_count += 1
                    continue

                # 其他元素类型（如 w:sectPr）可以忽略或添加处理逻辑
                # logger.debug("word_xml_unknown_element", element=tag_name)

            result = "\n\n".join(structured_parts)
            compressed_size = len(result.encode('utf-8'))

            return {
                "status": "success",
                "success": True,
                "data": {
                    "type": "word_xml",
                    "mode": "structured",
                    "format": "markdown",
                    "content": result,
                    "size": file_size,
                    "path": str(file_path),
                    "original_size": file_size,
                    "extracted_size": compressed_size,
                    "compression_ratio": f"{(1 - compressed_size / file_size) * 100:.1f}%"
                },
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "read_file",
                    "file_type": "word_xml",
                    "read_mode": "structured",
                    "element_count": element_count,
                    "paragraph_count": element_count  # 保持兼容性
                },
                "summary": f"✅ 提取结构化内容成功: {file_path.name} ({element_count} 个元素，压缩 ~80%)"
            }

        except ImportError:
            logger.warning("defusedxml_not_installed")
            return {
                "status": "failed",
                "success": False,
                "error": "defusedxml 未安装，请运行: pip install defusedxml",
                "summary": "❌ 缺少 XML 解析库"
            }
        except Exception as e:
            logger.error("extract_structured_from_word_xml_failed", path=str(file_path), error=str(e))
            raise

    def _get_paragraph_text(self, paragraph) -> str:
        """从段落元素提取文本（LobsterAI 方式）

        递归提取所有 w:t 标签的文本内容

        Args:
            paragraph: 段落元素（minidom.Element）

        Returns:
            提取的文本
        """
        text_parts = []
        for elem in paragraph.getElementsByTagName('w:t'):
            if elem.firstChild and elem.firstChild.nodeValue:
                text_parts.append(elem.firstChild.nodeValue)
        return ''.join(text_parts)

    def _extract_table_text(self, table) -> str:
        """从表格元素提取文本（简化版）

        Args:
            table: 表格元素（minidom.Element）

        Returns:
            表格的文本表示
        """
        try:
            rows = table.getElementsByTagName('w:tr')
            table_lines = []

            for row in rows:
                cells = row.getElementsByTagName('w:tc')
                cell_texts = []
                for cell in cells:
                    text = self._get_paragraph_text(cell)
                    # 限制单元格文本长度（避免过长）
                    cell_texts.append(text.strip()[:50])
                table_lines.append(" | ".join(cell_texts))

            if table_lines:
                # 添加表头分隔线
                header = table_lines[0]
                separator = " | ".join(["---"] * len(header.split(" | ")))
                return "[表格]\n" + "\n".join([header, separator] + table_lines[1:])

            return "[空表格]"

        except Exception as e:
            logger.warning("extract_table_text_failed", error=str(e))
            return "[表格解析失败]"

    def _resolve_path(self, path: str) -> Optional[Path]:
        """
        解析文件路径，确保在工作目录范围内

        Args:
            path: 文件路径（绝对或相对）

        Returns:
            Path 对象或 None（如果路径无效）
        """
        try:
            # 转换为 Path 对象
            file_path = Path(path)

            # 如果是相对路径，基于工作目录解析
            if not file_path.is_absolute():
                file_path = self.working_dir / file_path

            # 解析为绝对路径
            file_path = file_path.resolve()

            # 检查是否在工作目录范围内
            if not file_path.is_relative_to(self.working_dir):
                logger.warning(
                    "path_escape_attempt",
                    requested_path=path,
                    allowed_dir=str(self.working_dir)
                )
                return None

            return file_path

        except Exception as e:
            logger.error("path_resolution_failed", path=path, error=str(e))
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """获取 Function Calling Schema"""
        return {
            "name": "read_file",
            "description": """读取文件内容（统一文件读取入口，自动识别类型并优化）

特性：
- 文本文件：返回文本内容
- 图片文件：自动调用 Vision API 分析图片内容（可关闭）
- PDF 文件：提取文本内容，支持指定页面范围
- Word XML：智能分层读取（根据文件大小和 LLM 参数自动选择）⭐
- 目录列表：查看目录中的文件和子目录
- 自动检测文件类型并智能处理

Word XML 模式选择（完全由 LLM 通过参数控制）：

Word XML 模式选择（完全由 LLM 通过参数控制）：

默认行为（无需参数）：
• 小文档（<100KB）：structured 模式（保留标题、表格等结构）
• 大文档（≥100KB）：text 模式（只提取文字，最节省 tokens）

LLM 显式控制（高级场景）：
• raw_mode=True：返回完整原始 XML（用于精确编辑格式）
• include_formatting=True：强制使用 structured 模式（保留结构）
• max_paragraphs=N：限制读取段落数（进一步节省 tokens）

使用场景：
- 读取文本文件（代码、配置、日志等）
- 读取并分析图片（图表、文档截图、照片等）
- 读取 PDF 文档（支持指定页面范围）
- 读取 Word 文档内容（系统根据文件大小自动选择）
- 精确编辑 Word 文档（设置 raw_mode=True）
- 查看工作目录中的文件内容

示例：
- read_file(path="D:/work_dir/data.txt")  # 读取文本
- read_file(path="D:/work_dir/chart.png")  # 读取并自动分析图片
- read_file(path="D:/work_dir/report.pdf")  # 读取 PDF（全部页面）
- read_file(path="D:/work_dir/report.pdf", pages="1-5")  # 读取 PDF（第 1-5 页）
- read_file(path="D:/work_dir/document.xml")  # Word XML（自动根据文件大小选择）
- read_file(path="D:/work_dir/document.xml", raw_mode=True)  # Word XML（完整 XML，用于编辑）
- read_file(path="D:/work_dir")  # 查看目录内容
- read_file(path="D:/work_dir/doc.png", analysis_type="ocr")  # OCR文字识别
- read_file(path="D:/work_dir/photo.jpg", auto_analyze=False)  # 只读取不分析

限制：
- 图片大小限制：5MB
- PDF 页面限制：最多 20 页
- 工作目录限制：D:/溯源/ 及其子目录

注意：
- Word XML 模式完全由 LLM 通过参数控制，系统不会自动推断用户意图
- 图片文件会自动进行内容分析，分析结果以文本形式返回
- PDF 文件超过 10 页时，建议使用 pages 参数指定范围
- 不返回 base64 数据（避免 token 浪费）
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（绝对路径或相对路径）。示例：'D:/work_dir/data.txt' 或 'data/chart.png'"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "文本文件编码（默认 utf-8），对于中文文件可尝试 'gbk'",
                        "default": "utf-8"
                    },
                    "auto_analyze": {
                        "type": "boolean",
                        "description": "是否自动分析图片（默认 True）。设置为 False 则只读取图片数据，不调用 Vision API",
                        "default": True
                    },
                    "analysis_type": {
                        "type": "string",
                        "enum": ["ocr", "describe", "chart", "analyze"],
                        "description": "图片分析类型（仅当 auto_analyze=True 时有效）：ocr=文字识别, describe=图片描述, chart=图表分析, analyze=综合分析（默认）",
                        "default": "analyze"
                    },
                    "pages": {
                        "type": "string",
                        "description": "PDF 页面范围（仅对 PDF 文件有效）。格式：'1-5'（范围）或 '3'（单页）。最多支持 20 页。"
                    },
                    "raw_mode": {
                        "type": "boolean",
                        "description": "是否返回原始内容（Word XML 专用，默认 False）。设置为 True 时返回完整原始 XML，用于精确编辑格式。",
                        "default": False
                    },
                    "include_formatting": {
                        "type": "boolean",
                        "description": "是否保留格式信息（Word XML 专用，默认 False）。设置为 True 时保留标题、表格等结构信息。",
                        "default": False
                    },
                    "max_paragraphs": {
                        "type": "integer",
                        "description": "最大段落数（Word XML 专用，默认不限制）。用于进一步控制 token 消耗，例如设置为 50 只读取前 50 个段落。"
                    }
                },
                "required": ["path"]
            }
        }

    def is_available(self) -> bool:
        """检查工具是否可用"""
        return True


# 创建工具实例
tool = ReadFileTool()
