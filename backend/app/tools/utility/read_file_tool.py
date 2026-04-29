"""
ReadFile 工具 - 统一文件读取入口（支持分页、大小限制、多种格式）

让 LLM 能够读取本地文件系统中的文件：
- 文本文件：支持分页读取，智能大小限制
- 图片文件：自动调用 Vision API 进行内容分析
- Word XML：智能分层读取（自动推断最优模式）
- PDF 文件：委托给 parse_pdf 工具（支持OCR、表格、图片提取）
- DOCX 文件：委托给 read_docx 工具（支持PDF预览）
- 目录列表：查看目录中的文件和子目录

智能分页策略：
- 自动检测文件大小，超过限制时智能截断并提示
- 支持 offset/limit 参数进行精确分页
- 大文件时提示 Agent 使用 grep 搜索或分页读取

Word XML 三种模式：
1. text（纯文本）：只提取文字内容，最节省 tokens
2. structured（结构化）：保留标题、表格等结构，~80% 压缩
3. raw（原始）：完整 XML，用于精确编辑

委托模式：
- PDF/DOCX 内部委托给专业工具，保持代码不变
- 自动降级策略确保鲁棒性
"""
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.utility.file_read_state import get_file_read_state
from app.tools.utility.project_root import get_project_root
import structlog

logger = structlog.get_logger()


class ReadFileTool(LLMTool):
    """
    文件读取工具（统一入口，支持分页和大小限制）

    功能：
    - 读取文本文件内容（支持分页）
    - 读取图片文件并自动分析
    - 读取 PDF 文件（委托给 parse_pdf，支持OCR、表格、图片提取）
    - 读取 DOCX 文件（委托给 read_docx，支持PDF预览）
    - 读取 Word XML（支持多种模式）
    - 自动检测文件类型和大小
    """

    # 支持的图片格式
    IMAGE_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'
    }

    # 支持的 PDF 格式
    PDF_EXTENSIONS = {'.pdf'}

    # 支持的 DOCX 格式
    DOCX_EXTENSIONS = {'.docx'}

    # 支持的 Excel 格式
    EXCEL_EXTENSIONS = {'.xlsx', '.xls', '.xlsm'}

    # 支持的 Markdown 格式
    MARKDOWN_EXTENSIONS = {'.md', '.markdown'}

    # 支持的 Jupyter Notebook 格式
    NOTEBOOK_EXTENSIONS = {'.ipynb'}

    # 文本文件默认大小限制（100KB）
    DEFAULT_MAX_SIZE = 100 * 1024

    # 默认分页行数
    DEFAULT_LIMIT = 1000

    def __init__(self):
        super().__init__(
            name="read_file",
            description=(
                "读取文件或目录内容，支持文本分页、图片分析、PDF、DOCX、Word XML、Markdown、Notebook。"
                "PDF/DOCX 默认会生成前端可查看的预览；预览失败不影响文本读取。"
                "Excel文件不由 read_file 读取，需使用 execute_python。"
                "大文本默认100KB限制，超限会截断并提示用 grep 或 offset/limit 分页。"
                "不返回base64，避免浪费上下文。"
            ),
            category=ToolCategory.QUERY,
            version="4.0.0",
            requires_context=False
        )

        # 工作目录：使用项目根目录（稳定路径，不依赖 cwd）
        self.working_dir = get_project_root()
        # 允许访问的额外目录（如临时目录）
        self.allowed_dirs = [self.working_dir, Path("/tmp")]
        self.max_image_size = 5 * 1024 * 1024  # 5MB
        self.max_pdf_size = 50 * 1024 * 1024  # 50MB
        self.max_docx_size = 20 * 1024 * 1024  # 20MB

        # 工具实例缓存
        self._tool_cache = {}

    async def execute(
        self,
        path: str,
        offset: int = 0,
        limit: Optional[int] = None,
        max_size: int = DEFAULT_MAX_SIZE,
        encoding: str = "utf-8",
        auto_analyze: bool = True,
        analysis_type: str = "analyze",
        pages: Optional[str] = None,
        raw_mode: bool = False,
        include_formatting: bool = False,
        max_paragraphs: Optional[int] = None,
        extract_tables: bool = True,
        extract_images: bool = False,
        enable_preview: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        读取文件内容（支持分页和智能大小限制）

        Args:
            path: 文件路径（绝对路径或相对路径）
            offset: 起始行号（从0开始，默认0）
            limit: 读取行数（默认1000，None表示不限制）
            max_size: 最大文件大小（字节，默认100KB）
            encoding: 文本文件编码（默认 utf-8）
            auto_analyze: 是否自动分析图片（默认 True）
            analysis_type: 图片分析类型（ocr/describe/chart/analyze，默认 analyze）
            pages: PDF/DOCX 页面范围（如 "1-5", "3", "10-20"）
            raw_mode: 是否返回原始内容（Word XML 专用，默认 False）
            include_formatting: 是否保留格式信息（Word XML 专用，默认 False）
            max_paragraphs: 最大段落数（Word XML/DOCX 专用，默认不限制）
            extract_tables: PDF是否提取表格（默认 True）
            extract_images: PDF是否提取图片（默认 False）
            enable_preview: PDF/DOCX是否生成预览（默认 True）

        Returns:
            简化格式：{"success": bool, "data": dict, "summary": str}
        """
        try:
            # 1. 解析文件路径
            resolved_path = self._resolve_path(path)
            if not resolved_path:
                return {
                    "success": False,
                    "data": {"error": f"文件路径无效或超出工作目录范围: {path}"},
                    "summary": f"无法访问文件: {path}"
                }

            # 2. 检查文件是否存在
            if not resolved_path.exists():
                return {
                    "success": False,
                    "data": {"error": f"文件不存在: {path}"},
                    "summary": f"文件不存在: {path}"
                }

            # 2.5. 检查是否为目录
            if resolved_path.is_dir():
                return await self._list_directory(resolved_path)

            # 3. 获取文件信息
            file_size = resolved_path.stat().st_size
            file_ext = resolved_path.suffix.lower()

            # 4. 判断文件类型并读取
            is_image = file_ext in self.IMAGE_EXTENSIONS
            is_pdf = file_ext in self.PDF_EXTENSIONS
            is_docx = file_ext in self.DOCX_EXTENSIONS
            is_excel = file_ext in self.EXCEL_EXTENSIONS
            is_notebook = file_ext in self.NOTEBOOK_EXTENSIONS
            is_word_xml = self._is_word_xml(resolved_path)

            if is_image:
                return await self._read_image(
                    resolved_path, file_size, auto_analyze, analysis_type
                )
            elif is_pdf:
                return await self._read_pdf_delegated(
                    resolved_path, file_size, pages, extract_tables, extract_images, enable_preview
                )
            elif is_docx:
                return await self._read_docx_delegated(
                    resolved_path, file_size, pages, max_paragraphs, enable_preview
                )
            elif is_excel:
                # Excel 文件需要使用 execute_python 工具
                return await self._handle_excel_file(resolved_path)
            elif is_word_xml:
                return await self._read_word_xml(
                    resolved_path, file_size, raw_mode, include_formatting, max_paragraphs
                )
            elif is_notebook:
                # 读取 Jupyter Notebook（作为文本文件处理）
                result = await self._read_text(
                    resolved_path, encoding, file_size, offset, limit, max_size
                )
                # 标记为已读取（用于 notebook_edit 的 Read-Before-Edit 机制）
                if result.get("success"):
                    try:
                        from app.tools.utility.notebook_edit_tool import mark_notebook_as_read
                        full_content = resolved_path.read_text(encoding=encoding)
                        mark_notebook_as_read(str(resolved_path), full_content)
                    except ImportError:
                        pass
                # 生成 HTML 预览
                if result.get("success") and enable_preview:
                    await self._ensure_notebook_preview(resolved_path, result["data"])
                return result
            else:
                # 读取文本文件（支持分页）
                return await self._read_text(
                    resolved_path, encoding, file_size, offset, limit, max_size
                )

        except Exception as e:
            logger.error("read_file_failed", path=path, error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"读取文件失败: {str(e)[:50]}"
            }

    async def _list_directory(self, dir_path: Path) -> Dict[str, Any]:
        """列出目录内容"""
        try:
            items = list(dir_path.iterdir())
            item_list = []
            for item in sorted(items, key=lambda x: (not x.is_dir(), x.name)):
                item_type = "DIR " if item.is_dir() else "FILE"
                size = f" ({item.stat().st_size} bytes)" if item.is_file() else ""
                item_list.append(f"{item_type} {item.name}{size}")

            content = "\n".join(item_list) if item_list else "(空目录)"

            return {
                "success": True,
                "data": {
                    "type": "directory",
                    "content": content,
                    "path": str(dir_path),
                    "item_count": len(items)
                },
                "summary": f"目录内容: {dir_path.name} ({len(items)} 项)"
            }
        except Exception as e:
            return {
                "success": False,
                "data": {"error": f"无法列出目录内容: {str(e)}"},
                "summary": f"无法访问目录: {dir_path.name}"
            }

    async def _read_text(
        self,
        file_path: Path,
        encoding: str,
        file_size: int,
        offset: int = 0,
        limit: Optional[int] = None,
        max_size: int = DEFAULT_MAX_SIZE
    ) -> Dict[str, Any]:
        """
        读取文本文件（支持分页和智能大小限制）

        策略：
        1. 如果指定了 limit，按 limit 读取（不超过 max_size）
        2. 如果文件超过 max_size 且未指定 limit，自动截断并提示
        3. 返回行号信息，方便后续分页
        """
        try:
            # 检查文件是否过大
            is_large_file = file_size > max_size
            effective_limit = limit or self.DEFAULT_LIMIT

            # 读取文件内容
            try:
                full_content = file_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                return {
                    "success": False,
                    "data": {"error": "编码错误，尝试使用 encoding='gbk' 或 encoding='latin-1'"},
                    "summary": f"文本编码错误: {file_path.name}"
                }

            # 分割成行
            lines = full_content.splitlines()
            total_lines = len(lines)

            # 计算实际读取范围
            start_line = offset
            end_line = min(offset + effective_limit, total_lines) if limit else total_lines

            # 提取指定范围的内容
            selected_lines = lines[start_line:end_line]
            content = "\n".join(selected_lines)

            # 检查是否需要截断
            is_truncated = is_large_file or (limit and end_line < total_lines)

            # 构建返回数据
            data = {
                "type": "text",
                "format": file_path.suffix[1:] if file_path.suffix else "txt",
                "content": content,
                "path": str(file_path),
                "size": file_size,
                "line_range": [start_line + 1, end_line],  # 1-based
                "total_lines": total_lines,
                "is_truncated": is_truncated
            }

            # Markdown文件添加预览字段
            if file_path.suffix.lower() in self.MARKDOWN_EXTENSIONS:
                data["markdown_preview"] = {
                    "content": content,
                    "file_name": file_path.name,
                    "file_path": str(file_path)
                }

            # 构建摘要信息
            if is_large_file and limit is None:
                # 文件过大，自动截断
                data["truncation_reason"] = "file_size_exceeded"
                data["max_size"] = max_size
                summary = (
                    f"读取成功: {file_path.name} ({file_size} bytes, {total_lines} 行)\n"
                    f"已返回第 {start_line + 1}-{end_line} 行（共{total_lines}行）\n"
                    f"提示: 文件超过{max_size}bytes，已自动截断。"
                    f"使用 offset={end_line},limit={effective_limit} 继续读取，"
                    f"或先用 grep 搜索定位行号"
                )
            elif limit and end_line < total_lines:
                # 用户指定了 limit 但未读完
                summary = (
                    f"读取成功: {file_path.name} ({file_size} bytes)\n"
                    f"已返回第 {start_line + 1}-{end_line} 行（共{total_lines}行）\n"
                    f"提示: 使用 offset={end_line},limit={effective_limit} 继续读取后续内容"
                )
            else:
                # 完整读取
                summary = f"读取成功: {file_path.name} ({file_size} bytes, {total_lines} 行)"

            # 记录读取状态（用于edit_file预读验证）
            is_full_read = not is_truncated
            read_state = get_file_read_state()
            read_state.set(
                str(file_path),
                content=full_content if is_full_read else None,
                offset=offset if not is_full_read else None,
                limit=limit if not is_full_read else None,
                is_partial_view=not is_full_read,
                file_size=file_size,
                encoding=encoding
            )

            return {
                "success": True,
                "data": data,
                "summary": summary
            }

        except Exception as e:
            logger.error("read_text_failed", path=str(file_path), error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"读取文件失败: {str(e)[:50]}"
            }

    async def _read_image(
        self,
        file_path: Path,
        file_size: int,
        auto_analyze: bool = True,
        analysis_type: str = "analyze"
    ) -> Dict[str, Any]:
        """读取图片文件（自动分析）"""
        try:
            # 检查文件大小
            if file_size > self.max_image_size:
                return {
                    "success": False,
                    "data": {
                        "error": f"图片文件过大: {file_size} bytes (最大 {self.max_image_size} bytes)"
                    },
                    "summary": f"图片过大，超过5MB限制"
                }

            file_ext = file_path.suffix[1:]
            result = {
                "success": True,
                "data": {
                    "type": "image",
                    "format": file_ext,
                    "size": file_size,
                    "path": str(file_path)
                },
                "summary": f"读取图片: {file_path.name} ({file_size} bytes, {file_ext})"
            }

            # 自动分析图片
            if auto_analyze:
                try:
                    from app.tools.utility.analyze_image_tool import AnalyzeImageTool
                    analyze_tool = AnalyzeImageTool()
                    analyze_result = await analyze_tool.execute(
                        path=str(file_path),
                        operation=analysis_type
                    )

                    if analyze_result.get('success'):
                        result['data']['analysis'] = analyze_result['data']['analysis']
                        result['data']['operation'] = analyze_result['data']['operation']
                        op_text = f" [{analysis_type}]" if analysis_type != "analyze" else ""
                        result['summary'] = f"读取并分析图片成功: {file_path.name}{op_text}"
                    else:
                        result['data']['analysis_error'] = analyze_result.get('error', '分析失败')
                        result['summary'] = f"读取图片成功（分析失败）: {file_path.name}"

                except ImportError:
                    result['data']['analysis_error'] = "AnalyzeImage 工具不可用"
                    result['summary'] = f"读取图片成功（分析工具不可用）: {file_path.name}"
                except Exception as e:
                    result['data']['analysis_error'] = str(e)
                    result['summary'] = f"读取图片成功（分析出错）: {file_path.name}"

            return result

        except Exception as e:
            logger.error("read_image_failed", path=str(file_path), error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"读取图片失败: {str(e)[:50]}"
            }

    async def _read_pdf(
        self,
        file_path: Path,
        file_size: int,
        pages: Optional[str] = None
    ) -> Dict[str, Any]:
        """读取 PDF 文件"""
        try:
            try:
                import PyPDF2
            except ImportError:
                return {
                    "success": False,
                    "data": {"error": "PyPDF2 未安装，请运行: pip install PyPDF2"},
                    "summary": "缺少 PDF 支持库"
                }

            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                total_pages = len(pdf_reader.pages)

                page_numbers = self._parse_page_range(pages, total_pages)

                if page_numbers is None:
                    return {
                        "success": False,
                        "data": {"error": f"无效的页面范围: {pages}"},
                        "summary": "页面范围格式错误"
                    }

                if len(page_numbers) > 20:
                    return {
                        "success": False,
                        "data": {
                            "error": f"页面数量超过限制（{len(page_numbers)} 页），最多支持 20 页。"
                                    f"请使用 pages 参数指定范围，如 pages='1-20'"
                        },
                        "summary": f"PDF 页面过多（{len(page_numbers)} 页，限制 20 页）"
                    }

                # 提取文本
                text_content = []
                for page_num in page_numbers:
                    try:
                        page = pdf_reader.pages[page_num - 1]
                        text = page.extract_text()
                        text_content.append(f"--- Page {page_num} ---\n{text}")
                    except Exception as e:
                        logger.warning("pdf_page_extract_failed", page=page_num, error=str(e))
                        text_content.append(f"--- Page {page_num} ---\n(提取失败: {str(e)})")

                content = "\n\n".join(text_content)

                return {
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
                    "summary": f"读取 PDF 成功: {file_path.name} (第 {page_numbers[0]}-{page_numbers[-1]} 页，共 {len(page_numbers)} 页)"
                }

        except Exception as e:
            logger.error("read_pdf_failed", path=str(file_path), error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"读取 PDF 失败: {str(e)[:50]}"
            }

    async def _read_pdf_delegated(
        self,
        file_path: Path,
        file_size: int,
        pages: Optional[str] = None,
        extract_tables: bool = True,
        extract_images: bool = False,
        enable_preview: bool = True
    ) -> Dict[str, Any]:
        """委托 parse_pdf 工具读取 PDF（带降级策略）"""
        try:
            # 检查文件大小
            if file_size > self.max_pdf_size:
                return {
                    "success": False,
                    "data": {"error": f"PDF文件过大: {file_size} bytes (最大 {self.max_pdf_size} bytes)"},
                    "summary": f"PDF过大，超过50MB限制"
                }
        except Exception as e:
            logger.error("read_pdf_delegated_failed", path=str(file_path), error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"读取PDF失败: {str(e)[:50]}"
            }

        try:
            # 1. 尝试调用 parse_pdf 工具
            from app.tools.utility.parse_pdf_tool import ParsePDFTool

            tool = self._get_cached_tool(ParsePDFTool, "parse_pdf")

            # 构造参数：使用 auto 模式自动检测
            parse_pdf_args = {
                "path": str(file_path),
                "mode": "auto",  # 自动检测文本型/扫描型
                "ocr_engine": "auto"  # 自动选择最佳OCR引擎
            }

            # 添加可选参数
            if pages:
                parse_pdf_args["pages"] = pages

            if extract_tables:
                parse_pdf_args["extract_tables"] = True

            if extract_images:
                parse_pdf_args["extract_images"] = True

            result = await tool.execute(**parse_pdf_args)

            if result.get("success"):
                normalized = self._normalize_pdf_result(result, file_path, file_size)
                # 生成PDF预览（PDF直接使用原文件）
                if enable_preview:
                    await self._ensure_pdf_preview(file_path, normalized["data"], is_pdf=True)
                return normalized

            # 2. parse_pdf 失败，降级到原生 PyPDF2
            logger.warning("parse_pdf_failed_fallback_to_pypdf2", path=str(file_path))
            return await self._read_pdf_fallback(file_path, file_size, pages, enable_preview)

        except ImportError:
            # 3. parse_pdf 不可用，使用原生 PyPDF2
            logger.warning("parse_pdf_not_available_fallback_to_pypdf2", path=str(file_path))
            return await self._read_pdf_fallback(file_path, file_size, pages, enable_preview)

        except Exception as e:
            logger.error("read_pdf_delegated_failed", path=str(file_path), error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"读取PDF失败: {str(e)[:50]}"
            }

    def _normalize_pdf_result(self, result: Dict[str, Any], file_path: Path, file_size: int) -> Dict[str, Any]:
        """标准化 parse_pdf 工具的返回格式"""
        try:
            data = result.get("data", {})
            content_parts = []

            # 添加文本内容
            if "text" in data:
                content_parts.append(data["text"])

            # 添加表格内容
            if "tables" in data and data["tables"]:
                content_parts.append("\n\n[提取的表格]")
                for i, table in enumerate(data["tables"], 1):
                    content_parts.append(f"\n表格 {i}:\n{table}")

            # 添加图片信息
            if "images" in data and data["images"]:
                content_parts.append(f"\n\n[检测到 {len(data['images'])} 张图片]")

            content = "\n".join(content_parts)

            normalized_data = {
                "type": "pdf",
                "content": content,
                "path": str(file_path),
                "size": file_size,
                "total_pages": data.get("total_pages", 0),
                "pages_read": data.get("pages_read", 0),
            }

            # 添加提取的表格和图片信息
            if "tables" in data:
                normalized_data["extracted_tables"] = data["tables"]
            if "images" in data:
                normalized_data["extracted_images"] = data["images"]

            return {
                "success": True,
                "data": normalized_data,
                "summary": result.get("summary", f"读取PDF成功: {file_path.name}"),
                "metadata": {
                    "generator": "read_file",
                    "delegated_to": "parse_pdf"
                }
            }

        except Exception as e:
            logger.error("normalize_pdf_result_failed", error=str(e))
            return {
                "success": False,
                "data": {"error": f"结果标准化失败: {str(e)}"},
                "summary": "PDF结果格式错误"
            }

    async def _read_pdf_fallback(
        self,
        file_path: Path,
        file_size: int,
        pages: Optional[str] = None,
        enable_preview: bool = True
    ) -> Dict[str, Any]:
        """使用原生 PyPDF2 降级读取 PDF"""
        try:
            import PyPDF2
        except ImportError:
            return {
                "success": False,
                "data": {"error": "PyPDF2 未安装，请运行: pip install PyPDF2"},
                "summary": "缺少 PDF 支持库"
            }

        try:
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                total_pages = len(pdf_reader.pages)

                page_numbers = self._parse_page_range(pages, total_pages)

                if page_numbers is None:
                    return {
                        "success": False,
                        "data": {"error": f"无效的页面范围: {pages}"},
                        "summary": "页面范围格式错误"
                    }

                if len(page_numbers) > 20:
                    return {
                        "success": False,
                        "data": {
                            "error": f"页面数量超过限制（{len(page_numbers)} 页），最多支持 20 页。"
                                    f"请使用 pages 参数指定范围，如 pages='1-20'"
                        },
                        "summary": f"PDF 页面过多（{len(page_numbers)} 页，限制 20 页）"
                    }

                # 提取文本
                text_content = []
                for page_num in page_numbers:
                    try:
                        page = pdf_reader.pages[page_num - 1]
                        text = page.extract_text()
                        text_content.append(f"--- Page {page_num} ---\n{text}")
                    except Exception as e:
                        logger.warning("pdf_page_extract_failed", page=page_num, error=str(e))
                        text_content.append(f"--- Page {page_num} ---\n(提取失败: {str(e)})")

                content = "\n\n".join(text_content)

                result_data = {
                    "type": "pdf",
                    "content": content,
                    "size": file_size,
                    "path": str(file_path),
                    "total_pages": total_pages,
                    "pages_read": len(page_numbers),
                    "page_range": pages or f"1-{total_pages}"
                }

                # 生成PDF预览（PDF直接使用原文件）
                if enable_preview:
                    await self._ensure_pdf_preview(file_path, result_data, is_pdf=True)

                return {
                    "success": True,
                    "data": result_data,
                    "summary": f"读取 PDF 成功: {file_path.name} (第 {page_numbers[0]}-{page_numbers[-1]} 页，共 {len(page_numbers)} 页)",
                    "metadata": {
                        "generator": "read_file",
                        "delegated_to": "pypdf2_fallback"
                    }
                }

        except Exception as e:
            logger.error("read_pdf_fallback_failed", path=str(file_path), error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"读取 PDF 失败: {str(e)[:50]}"
            }

    async def _read_docx_delegated(
        self,
        file_path: Path,
        file_size: int,
        pages: Optional[str] = None,
        max_paragraphs: Optional[int] = None,
        enable_preview: bool = True
    ) -> Dict[str, Any]:
        """委托 read_docx 工具读取 DOCX"""
        try:
            # 检查文件大小
            if file_size > self.max_docx_size:
                return {
                    "success": False,
                    "data": {"error": f"DOCX文件过大: {file_size} bytes (最大 {self.max_docx_size} bytes)"},
                    "summary": f"DOCX过大，超过20MB限制"
                }

            # 导入 read_docx 工具
            from app.tools.report.read_docx.tool import ReadDocxTool

            tool = self._get_cached_tool(ReadDocxTool, "read_docx")

            # 构造参数
            read_docx_args = {
                "path": str(file_path),
                "max_paragraphs": max_paragraphs or 100,
                "include_tables": True
            }

            result = await tool.execute(**read_docx_args)

            if result.get("success"):
                # 标准化返回格式
                normalized = {
                    "success": True,
                    "data": result["data"],
                    "summary": result["summary"],
                    "metadata": {
                        "generator": "read_file",
                        "delegated_to": "read_docx"
                    }
                }
                return normalized
            else:
                return result

        except ImportError:
            logger.error("read_docx_not_available", path=str(file_path))
            return {
                "success": False,
                "data": {"error": "read_docx 工具不可用"},
                "summary": "DOCX读取工具不可用"
            }
        except Exception as e:
            logger.error("read_docx_delegated_failed", path=str(file_path), error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"读取DOCX失败: {str(e)[:50]}"
            }

    async def _ensure_pdf_preview(self, file_path: Path, result_data: dict, is_pdf: bool = False):
        """确保PDF预览已生成（PDF和DOCX）"""
        if "pdf_preview" in result_data:
            return  # 已有预览

        try:
            if is_pdf:
                # PDF：直接使用原文件，生成预览元数据
                import pypdf
                pages = 0
                try:
                    with open(file_path, 'rb') as f:
                        reader = pypdf.PdfReader(f)
                        pages = len(reader.pages)
                except Exception:
                    pages = result_data.get("total_pages", 0)

                result_data["pdf_preview"] = {
                    "pdf_id": f"{uuid.uuid4()}",
                    "pdf_url": f"/api/file/{str(file_path)}",
                    "pages": pages,
                    "size": file_path.stat().st_size
                }
            else:
                # DOCX：通过 LibreOffice 转换
                from app.services.pdf_converter import pdf_converter
                pdf_preview = await pdf_converter.convert_to_pdf(str(file_path))
                result_data["pdf_preview"] = pdf_preview

        except Exception as e:
            logger.warning("pdf_preview_generation_failed", path=str(file_path), error=str(e))
            # 预览失败不影响主流程

    async def _ensure_notebook_preview(self, notebook_path: Path, result_data: dict):
        """确保Notebook HTML预览已生成"""
        if "html_preview" in result_data:
            return  # 已有预览

        try:
            from app.services.notebook_converter import notebook_converter
            html_preview = await notebook_converter.convert_to_html(str(notebook_path))
            result_data["html_preview"] = html_preview
            logger.info(
                "notebook_preview_generated",
                notebook_path=str(notebook_path),
                html_id=html_preview["html_id"]
            )
        except Exception as e:
            logger.warning("notebook_preview_generation_failed", path=str(notebook_path), error=str(e))
            # 预览失败不影响主流程

    def _get_cached_tool(self, tool_class, tool_name: str):
        """获取缓存的工具实例"""
        if tool_name not in self._tool_cache:
            self._tool_cache[tool_name] = tool_class()
        return self._tool_cache[tool_name]

    def _parse_page_range(self, pages: Optional[str], total_pages: int) -> Optional[list]:
        """解析页面范围字符串"""
        if pages is None:
            return list(range(1, total_pages + 1))

        try:
            pages = pages.strip()

            if pages.isdigit():
                page_num = int(pages)
                if 1 <= page_num <= total_pages:
                    return [page_num]
                else:
                    return None

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
        """检测是否是 Word XML 文件（document.xml）"""
        if file_path.name != "document.xml":
            return False

        if "word" not in file_path.parts:
            return False

        try:
            parent_dir = file_path.parent.parent
            rels_dir = parent_dir / "_rels"
            if rels_dir.exists():
                return True

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
        """读取 Word XML 文件"""
        try:
            if raw_mode:
                return await self._read_raw_word_xml(file_path, file_size)

            if include_formatting:
                return await self._extract_structured_from_word_xml(
                    file_path, file_size, max_paragraphs
                )

            # 自动推断（根据文件大小）
            if file_size < 100_000:  # < 100KB
                return await self._extract_structured_from_word_xml(
                    file_path, file_size, max_paragraphs
                )
            else:  # >= 100KB
                return await self._extract_text_from_word_xml(
                    file_path, file_size, max_paragraphs
                )

        except Exception as e:
            logger.error("read_word_xml_failed", path=str(file_path), error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"读取 Word XML 失败: {str(e)[:50]}"
            }

    async def _read_raw_word_xml(self, file_path: Path, file_size: int) -> Dict[str, Any]:
        """读取原始 Word XML 内容"""
        try:
            content = file_path.read_text(encoding='utf-8')

            return {
                "success": True,
                "data": {
                    "type": "word_xml",
                    "mode": "raw",
                    "format": "xml",
                    "content": content,
                    "size": file_size,
                    "path": str(file_path)
                },
                "summary": f"读取 Word XML 成功（原始模式）: {file_path.name} ({file_size} bytes)"
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
        """从 Word XML 提取纯文本"""
        try:
            from defusedxml import minidom

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            doc = minidom.parseString(content)

            text_parts = []
            paragraph_count = 0

            for elem in doc.getElementsByTagName('w:t'):
                if max_paragraphs and paragraph_count >= max_paragraphs:
                    break

                if elem.firstChild and elem.firstChild.nodeValue.strip():
                    text_parts.append(elem.firstChild.nodeValue.strip())
                    paragraph_count += 1

            result = "\n".join(text_parts)
            compressed_size = len(result.encode('utf-8'))

            return {
                "success": True,
                "data": {
                    "type": "word_xml",
                    "mode": "text",
                    "format": "plain_text",
                    "content": result,
                    "size": file_size,
                    "path": str(file_path),
                    "original_size": file_size,
                    "extracted_size": compressed_size,
                    "compression_ratio": f"{(1 - compressed_size / file_size) * 100:.1f}%",
                    "paragraph_count": paragraph_count
                },
                "summary": f"提取纯文本成功: {file_path.name} ({paragraph_count} 个文本片段，压缩 ~90%)"
            }

        except ImportError:
            return {
                "success": False,
                "data": {"error": "defusedxml 未安装，请运行: pip install defusedxml"},
                "summary": "缺少 XML 解析库"
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
        """从 Word XML 提取结构化内容"""
        try:
            from defusedxml import minidom

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            doc = minidom.parseString(content)

            body_elements = doc.getElementsByTagName('w:body')
            if not body_elements:
                return {
                    "success": False,
                    "data": {"error": "Word XML 缺少 w:body 元素"},
                    "summary": "文档格式错误"
                }

            body = body_elements[0]

            structured_parts = []
            element_count = 0

            for child in body.childNodes:
                if max_paragraphs and element_count >= max_paragraphs:
                    break

                if child.nodeType != child.ELEMENT_NODE:
                    continue

                tag_name = child.tagName

                if tag_name == 'w:tbl':
                    table_text = self._extract_table_text(child)
                    if table_text and table_text != "[空表格]":
                        structured_parts.append(table_text)
                        element_count += 1
                    continue

                if tag_name == 'w:p':
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

                    drawings = child.getElementsByTagName('a:blip')
                    if drawings:
                        r_id = drawings[0].getAttribute('r:embed')
                        structured_parts.append(f"[图片引用: {r_id}]")
                        element_count += 1
                        continue

                    text = self._get_paragraph_text(child)
                    if text.strip():
                        structured_parts.append(text)
                        element_count += 1
                    continue

            result = "\n\n".join(structured_parts)
            compressed_size = len(result.encode('utf-8'))

            return {
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
                    "compression_ratio": f"{(1 - compressed_size / file_size) * 100:.1f}%",
                    "element_count": element_count
                },
                "summary": f"提取结构化内容成功: {file_path.name} ({element_count} 个元素，压缩 ~80%)"
            }

        except ImportError:
            return {
                "success": False,
                "data": {"error": "defusedxml 未安装，请运行: pip install defusedxml"},
                "summary": "缺少 XML 解析库"
            }
        except Exception as e:
            logger.error("extract_structured_from_word_xml_failed", path=str(file_path), error=str(e))
            raise

    def _get_paragraph_text(self, paragraph) -> str:
        """从段落元素提取文本"""
        text_parts = []
        for elem in paragraph.getElementsByTagName('w:t'):
            if elem.firstChild and elem.firstChild.nodeValue:
                text_parts.append(elem.firstChild.nodeValue)
        return ''.join(text_parts)

    def _extract_table_text(self, table) -> str:
        """从表格元素提取文本"""
        try:
            rows = table.getElementsByTagName('w:tr')
            table_lines = []

            for row in rows:
                cells = row.getElementsByTagName('w:tc')
                cell_texts = []
                for cell in cells:
                    text = self._get_paragraph_text(cell)
                    cell_texts.append(text.strip()[:50])
                table_lines.append(" | ".join(cell_texts))

            if table_lines:
                header = table_lines[0]
                separator = " | ".join(["---"] * len(header.split(" | ")))
                return "[表格]\n" + "\n".join([header, separator] + table_lines[1:])

            return "[空表格]"

        except Exception as e:
            logger.warning("extract_table_text_failed", error=str(e))
            return "[表格解析失败]"

    def _resolve_path(self, path: str) -> Optional[Path]:
        """解析文件路径，确保在允许的目录范围内"""
        try:
            file_path = Path(path)

            if not file_path.is_absolute():
                file_path = self.working_dir / file_path

            file_path = file_path.resolve()

            # 检查是否在允许的目录范围内
            is_allowed = any(file_path.is_relative_to(allowed_dir) for allowed_dir in self.allowed_dirs)

            if not is_allowed:
                logger.warning(
                    "path_escape_attempt",
                    requested_path=path,
                    allowed_dirs=[str(d) for d in self.allowed_dirs]
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
            "description": (
                "读取文件/目录；支持文本分页、图片、PDF、DOCX、Word XML、Markdown、Notebook。"
                "PDF/DOCX可预览；Excel用execute_python；大文本用grep或分页；不返回base64。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件或目录路径"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "起始行号，从0开始",
                        "default": 0
                    },
                    "limit": {
                        "type": "integer",
                        "description": "分页读取行数，默认1000",
                        "default": 1000
                    },
                    "max_size": {
                        "type": "integer",
                        "description": "最大读取字节，默认100KB",
                        "default": 102400
                    },
                    "encoding": {
                        "type": "string",
                        "description": "文本编码，默认utf-8",
                        "default": "utf-8"
                    },
                    "auto_analyze": {
                        "type": "boolean",
                        "description": "是否自动分析图片",
                        "default": True
                    },
                    "analysis_type": {
                        "type": "string",
                        "enum": ["ocr", "describe", "chart", "analyze"],
                        "description": "图片分析类型",
                        "default": "analyze"
                    },
                    "pages": {
                        "type": "string",
                        "description": "PDF/DOCX页码范围，如1-5或3"
                    },
                    "extract_tables": {
                        "type": "boolean",
                        "description": "PDF是否提取表格",
                        "default": True
                    },
                    "extract_images": {
                        "type": "boolean",
                        "description": "PDF是否提取图片",
                        "default": False
                    },
                    "enable_preview": {
                        "type": "boolean",
                        "description": "PDF/DOCX是否生成前端预览",
                        "default": True
                    },
                    "raw_mode": {
                        "type": "boolean",
                        "description": "Word XML是否返回原始内容",
                        "default": False
                    },
                    "include_formatting": {
                        "type": "boolean",
                        "description": "Word XML是否保留格式信息",
                        "default": False
                    },
                    "max_paragraphs": {
                        "type": "integer",
                        "description": "最大段落数"
                    }
                },
                "required": ["path"]
            }
        }

    async def _handle_excel_file(self, file_path: Path) -> Dict[str, Any]:
        """
        处理 Excel 文件，提示用户使用 execute_python 工具

        Args:
            file_path: Excel 文件路径

        Returns:
            提示信息和 Excel 处理函数说明
        """
        file_name = file_path.name
        file_size = file_path.stat().st_size
        size_mb = file_size / (1024 * 1024)

        return {
            "success": False,
            "data": {
                "error": "Excel 文件需要使用 execute_python 工具读取",
                "file_type": "Excel",
                "file_name": file_name,
                "file_size_mb": round(size_mb, 2),
                "suggested_tool": "execute_python",
                "available_functions": {
                    "read_excel": "读取 Excel 文件的数据和结构信息",
                    "analyze_excel_template": "分析 Excel 模板的结构和图表配置",
                    "create_excel_report": "创建 Excel 报告（支持数据和图表）"
                },
                "usage_example": f'''
# 使用 execute_python 读取 Excel 文件

# 方法1：读取数据和结构
result = read_excel("{file_path}")
print(result['sheets'])  # 工作表列表
print(result['data']['Sheet1'])  # 数据

# 方法2：分析模板结构
template = analyze_excel_template("{file_path}")
print(template['sheets'])  # 工作表结构
print(template['charts'])  # 图表配置

# 方法3：生成新报告
data = [{{"列1": "值1", "列2": "值2"}}]
report = create_excel_report(data, output_name="new_report.xlsx")
print(report['file_path'])  # 生成的文件路径
'''
            },
            "summary": f"📊 Excel 文件: {file_name} ({round(size_mb, 2)} MB) - 请使用 execute_python 工具读取"
        }

    def is_available(self) -> bool:
        """检查工具是否可用"""
        return True


# 创建工具实例
tool = ReadFileTool()
