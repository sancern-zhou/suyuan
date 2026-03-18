"""
Word Edit Tool - Unified Word Document Editing

Provides a comprehensive Word document editing interface that automatically
handles the unpack/edit/pack workflow. This is the recommended tool for
complex Word document editing operations.

Key Features:
- Automatic unpacking and packing of .docx files
- Structured editing operations (replace, insert, delete)
- Preserves document formatting and structure
- Powerful XML-based editing with XMLEditor
- Automatic PDF preview generation
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from docx import Document as DocxDocument
import structlog
import uuid
from datetime import datetime

from app.tools.base.tool_interface import LLMTool, ToolCategory
# 延迟导入避免循环依赖
# from app.tools.office.unpack_tool import UnpackOfficeTool
# from app.tools.office.pack_tool import PackOfficeTool
from app.tools.office.document import Document

logger = structlog.get_logger()

# PDF转换器导入（懒加载避免循环依赖）
def get_pdf_converter():
    try:
        from app.services.pdf_converter import pdf_converter
        return pdf_converter
    except ImportError:
        logger.warning("pdf_converter_not_available")
        return None


class WordEditTool(LLMTool):
    """
    Unified Word document editing tool.

    This tool provides a high-level API for editing Word documents with
    automatic handling of the underlying XML structure. It's designed for
    complex editing operations that require more control than simple
    find-and-replace.

    Use this tool for:
    - Structural editing (inserting paragraphs, reorganizing content)
    - Precise content replacement with context
    - Complex multi-step edits
    - Operations requiring XML-level control

    For simple text replacement, use find_replace_word instead.
    """

    def __init__(self):
        super().__init__(
            name="word_edit",
            description="""编辑 Word 文档（结构化编辑，自动解包/打包）

⭐ 复杂 Word 编辑的首选工具，自动处理解包/编辑/打包流程。

功能：
- 自动解包 .docx 文件
- 结构化编辑操作（替换段落、插入内容、删除节点）
- 保留文档格式和结构
- 强大的 XML 级别编辑能力

使用场景：
- ✅ 结构化编辑（插入段落、重新组织内容）
- ✅ 精确内容替换（带上下文）
- ✅ 复杂多步骤编辑
- ✅ 需要 XML 级别控制的操作

简单文本替换？
→ 使用 find_replace_word 工具（更简单、更快）

操作类型：
1. replace_text: 替换文本内容
2. replace_paragraph: 替换整个段落
3. insert_after: 在指定文本后插入新段落
4. insert_before: 在指定文本前插入新段落
5. delete_paragraph: 删除包含指定文本的段落

示例：
- word_edit(path="report.docx", operation="replace_text", search="旧内容", replace="新内容")
- word_edit(path="report.docx", operation="insert_after", marker="结论：", content="补充说明")
- word_edit(path="report.docx", operation="replace_paragraph", contains="错误段落", new_content="正确内容")

参数说明：
- path: DOCX 文件路径
- operation: 操作类型（replace_text/replace_paragraph/insert_after/insert_before/delete_paragraph）
- search: 要查找的文本（replace_text 操作）
- replace: 替换后的文本（replace_text 操作）
- contains: 段落包含的文本（replace_paragraph/delete_paragraph 操作）
- marker: 标记文本（insert_after/insert_before 操作）
- content: 新内容（insert_after/insert_before/replace_paragraph 操作）
- output_file: 输出文件路径（可选，默认覆盖原文件）
- backup: 是否创建备份（默认 True）

注意：
- 此工具自动处理解包和打包，无需手动调用 unpack_office/pack_office
- 编辑完成后自动重新打包 .docx 文件
- 复杂编辑可能需要多次调用
- 简单文本替换建议使用 find_replace_word
""",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )

        self.working_dir = Path.cwd().parent
        # 延迟初始化工具，避免循环导入
        self._unpack_tool = None
        self._pack_tool = None

    def _get_unpack_tool(self):
        """延迟获取UnpackOfficeTool实例"""
        if self._unpack_tool is None:
            from app.tools.office.unpack_tool import UnpackOfficeTool
            self._unpack_tool = UnpackOfficeTool()
        return self._unpack_tool

    def _get_pack_tool(self):
        """延迟获取PackOfficeTool实例"""
        if self._pack_tool is None:
            from app.tools.office.pack_tool import PackOfficeTool
            self._pack_tool = PackOfficeTool()
        return self._pack_tool

    async def execute(
        self,
        path: str,
        operation: str,
        search: Optional[str] = None,
        replace: Optional[str] = None,
        contains: Optional[str] = None,
        marker: Optional[str] = None,
        content: Optional[str] = None,
        new_content: Optional[str] = None,
        output_file: Optional[str] = None,
        backup: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute Word document editing operation.

        Args:
            path: DOCX file path
            operation: Operation type (replace_text, replace_paragraph, insert_after, insert_before, delete_paragraph)
            search: Text to search for (replace_text)
            replace: Replacement text (replace_text)
            contains: Text that paragraph must contain (replace_paragraph, delete_paragraph)
            marker: Marker text (insert_after, insert_before)
            content: New content to insert (insert_after, insert_before, replace_paragraph)
            new_content: Alias for content
            output_file: Output file path (optional, defaults to overwrite)
            backup: Whether to create backup (default True)

        Returns:
            {
                "success": bool,
                "data": {
                    "file_path": str,
                    "operation": str,
                    "changes": int,
                    "backup_path": str (if backup created)
                },
                "summary": str
            }
        """
        try:
            # 1. Resolve path
            resolved_path = self._resolve_path(path)
            if not resolved_path or not resolved_path.exists():
                return {
                    "success": False,
                    "data": {"error": f"文件不存在: {path}"},
                    "summary": "编辑失败：文件不存在"
                }

            if resolved_path.suffix.lower() != ".docx":
                return {
                    "success": False,
                    "data": {"error": f"不支持的文件格式: {resolved_path.suffix}"},
                    "summary": "编辑失败：仅支持 DOCX 格式"
                }

            # 2. Determine output file
            if output_file:
                output_path = self._resolve_path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                output_path = resolved_path

            # 3. Create backup if requested
            backup_path = None
            if backup and output_path == resolved_path:
                backup_path = self._create_backup(resolved_path)

            # 4. 检查是否存在已解包目录，如果有则直接使用，否则创建临时目录
            existing_unpacked = self._find_existing_unpacked_dir(resolved_path)
            should_cleanup = True  # 默认需要清理临时目录

            if existing_unpacked:
                # 使用已存在的解包目录
                unpacked_dir = str(existing_unpacked)
                should_cleanup = False  # 不清理已存在的目录
                logger.info(
                    "word_edit_using_existing_unpacked",
                    unpacked_dir=unpacked_dir
                )
            else:
                # 创建临时解包目录
                unique_temp_id = uuid.uuid4().hex[:8]
                temp_output_dir = f".word_edit_temp_{unique_temp_id}"
                unpack_result = await self._get_unpack_tool().execute(
                    path=str(resolved_path),
                    output_dir=temp_output_dir
                )

                if not unpack_result.get("success"):
                    return {
                        "success": False,
                        "data": {"error": "解包失败: " + unpack_result.get("summary", "")},
                        "summary": "编辑失败：无法解包文档"
                    }

                unpacked_dir = str(self.working_dir / unpack_result["data"]["output_dir"])

            try:
                # 5. Open document for editing
                doc = Document(unpacked_dir)

                # 6. Execute the requested operation
                result = self._execute_operation(doc, operation, {
                    "search": search,
                    "replace": replace,
                    "contains": contains,
                    "marker": marker,
                    "content": content or new_content,
                })

                if not result["success"]:
                    error_summary = result.get('summary', '')
                    return {
                        "success": False,
                        "data": result.get("data"),
                        "summary": error_summary if error_summary else "编辑失败：操作未成功完成"
                    }

                # 7. Save document changes
                doc.save()

                # 8. Pack the document
                pack_result = await self._get_pack_tool().execute(
                    input_dir=unpacked_dir,
                    output_file=str(output_path),
                    backup=False  # Already backed up if needed
                )

                if not pack_result.get("success"):
                    return {
                        "success": False,
                        "data": {"error": "打包失败: " + pack_result.get("summary", "")},
                        "summary": "编辑失败：无法重新打包文档"
                    }

                # 9. Return success
                response_data = {
                    "file_path": str(output_path),
                    "operation": operation,
                    "changes": result["changes"],
                }

                if backup_path:
                    response_data["backup_path"] = str(backup_path)

                # 生成PDF预览
                try:
                    converter = get_pdf_converter()
                    if converter:
                        pdf_preview = await converter.convert_to_pdf(str(output_path))
                        response_data["pdf_preview"] = pdf_preview
                        logger.info(
                            "word_edit_pdf_generated",
                            pdf_id=pdf_preview["pdf_id"],
                            pdf_url=pdf_preview["pdf_url"]
                        )
                except Exception as pdf_error:
                    logger.warning("word_edit_pdf_conversion_failed", error=str(pdf_error))

                # Use the summary from the operation result if available
                operation_summary = result.get('summary') or f"{operation} 操作完成，{result['changes']} 处修改"
                if should_cleanup:
                    success_summary = f"{operation_summary}。自动完成打包，临时解包文件已被清除。"
                else:
                    success_summary = f"{operation_summary}。已更新现有解包目录。"
                    response_data["updated_unpacked_dir"] = unpacked_dir

                return {
                    "success": True,
                    "data": response_data,
                    "summary": success_summary
                }

            finally:
                # 只清理临时目录，保留已存在的解包目录
                if should_cleanup:
                    self._cleanup_unpacked_dir(unpacked_dir)

        except Exception as e:
            logger.error("word_edit_failed", path=path, operation=operation, error=str(e))
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"编辑失败：{str(e)[:80]}"
            }

    def _execute_operation(self, doc: Document, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the specified editing operation."""
        operations = {
            "replace_text": self._op_replace_text,
            "replace_paragraph": self._op_replace_paragraph,
            "insert_after": self._op_insert_after,
            "insert_before": self._op_insert_before,
            "delete_paragraph": self._op_delete_paragraph,
        }

        if operation not in operations:
            return {
                "success": False,
                "summary": f"未知操作类型: {operation}。有效操作: {', '.join(operations.keys())}"
            }

        return operations[operation](doc, params)

    def _op_replace_text(self, doc: Document, params: Dict[str, Any]) -> Dict[str, Any]:
        """Replace text throughout the document."""
        search = params.get("search")
        replace = params.get("replace")

        if not search or replace is None:
            return {
                "success": False,
                "summary": "replace_text 操作需要 search 和 replace 参数"
            }

        count = doc.replace_text(search, replace)

        if count == 0:
            return {
                "success": False,
                "changes": 0,
                "summary": f"未找到要替换的文本: '{search[:100]}{'...' if len(search) > 100 else ''}'"
            }

        return {
            "success": True,
            "changes": count,
            "summary": f"成功替换 {count} 处文本: '{search[:30]}...' → '{replace[:30]}...'"
        }

    def _op_replace_paragraph(self, doc: Document, params: Dict[str, Any]) -> Dict[str, Any]:
        """Replace paragraph content."""
        contains = params.get("contains")
        content = params.get("content") or params.get("new_content")

        if not contains or not content:
            return {
                "success": False,
                "summary": "replace_paragraph 操作需要 contains 和 content (或 new_content) 参数"
            }

        success = doc.replace_paragraph_content(contains, content)

        if not success:
            return {
                "success": False,
                "changes": 0,
                "summary": f"替换段落失败: 未找到包含 '{contains[:100]}{'...' if len(contains) > 100 else ''}' 的段落"
            }

        return {
            "success": True,
            "changes": 1,
            "summary": f"成功替换包含 '{contains[:50]}...' 的段落内容"
        }

    def _op_insert_after(self, doc: Document, params: Dict[str, Any]) -> Dict[str, Any]:
        """Insert content after marker text."""
        marker = params.get("marker")
        content = params.get("content")

        if not marker or not content:
            return {
                "success": False,
                "summary": "insert_after 操作需要 marker 和 content 参数"
            }

        # insert_paragraph_after 现在返回 (success, message) 元组
        success, message = doc.insert_paragraph_after(marker, content)

        return {
            "success": success,
            "changes": 1 if success else 0,
            "summary": message if not success else f"在 '{marker[:50]}...' 后成功插入段落"
        }

    def _op_insert_before(self, doc: Document, params: Dict[str, Any]) -> Dict[str, Any]:
        """Insert content before marker text."""
        marker = params.get("marker", "")
        content = params.get("content", "")

        if not content:
            return {
                "success": False,
                "summary": "insert_before 操作需要 content 参数"
            }

        # Find paragraphs with the marker
        target_paragraphs = doc.find_paragraphs(marker)

        if not target_paragraphs:
            return {
                "success": False,
                "changes": 0,
                "summary": f"未找到包含标记文本的段落: '{marker[:100]}{'...' if len(marker) > 100 else ''}'. "
                          f"可能的原因: 1) 文本被分割到多个节点 2) 文本中有额外空格 3) 字符不完全匹配"
            }

        main_doc = doc.get_main_document()
        target = target_paragraphs[0]

        new_para_xml = f'''<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:r><w:t>{content}</w:t></w:r>
        </w:p>'''

        success = main_doc.editor.insert_before(target, new_para_xml)
        if success:
            main_doc.mark_modified()
            return {
                "success": True,
                "changes": 1,
                "summary": f"在 '{marker[:50]}...' 前成功插入段落"
            }
        else:
            return {
                "success": False,
                "changes": 0,
                "summary": "插入段落失败: XML 操作失败"
            }

    def _op_delete_paragraph(self, doc: Document, params: Dict[str, Any]) -> Dict[str, Any]:
        """Delete paragraphs containing specified text."""
        contains = params.get("contains")

        if not contains:
            return {
                "success": False,
                "summary": "delete_paragraph 操作需要 contains 参数"
            }

        main_doc = doc.get_main_document()
        target_paragraphs = doc.find_paragraphs(contains)

        if not target_paragraphs:
            return {
                "success": False,
                "changes": 0,
                "summary": f"未找到包含指定文本的段落: '{contains[:100]}{'...' if len(contains) > 100 else ''}'"
            }

        count = 0
        for para in target_paragraphs:
            if main_doc.editor.remove_node(para):
                main_doc.mark_modified()
                count += 1

        if count == 0:
            return {
                "success": False,
                "changes": 0,
                "summary": "删除段落失败: XML 操作失败"
            }

        return {
            "success": True,
            "changes": count,
            "summary": f"成功删除 {count} 个包含指定文本的段落"
        }

    def _create_backup(self, file_path: Path) -> Path:
        """Create a backup of the file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.stem}_backup_{timestamp}{file_path.suffix}"
        backup_path = file_path.parent / backup_name
        shutil.copy2(file_path, backup_path)
        return backup_path

    def _cleanup_unpacked_dir(self, unpacked_dir: str):
        """Clean up the temporary unpacked directory."""
        try:
            import shutil
            shutil.rmtree(unpacked_dir, ignore_errors=True)
        except Exception as e:
            logger.warning("cleanup_unpacked_dir_failed", dir=unpacked_dir, error=str(e))

    def _find_existing_unpacked_dir(self, doc_file_path: Path) -> Optional[Path]:
        """
        检查是否存在已解包的目录（遵循 unpack_office 的命名规则）

        Args:
            doc_file_path: Word 文档路径

        Returns:
            已解包目录的 Path 对象，如果不存在则返回 None
        """
        file_name = doc_file_path.stem
        expected_unpacked_dir = doc_file_path.parent / f"unpacked_{file_name}"

        if expected_unpacked_dir.exists() and expected_unpacked_dir.is_dir():
            # 验证这是一个有效的解包目录（包含 word/document.xml）
            doc_xml = expected_unpacked_dir / "word" / "document.xml"
            if doc_xml.exists():
                return expected_unpacked_dir

        return None

    def _resolve_path(self, path: str) -> Optional[Path]:
        """Resolve file path."""
        try:
            file_path = Path(path)

            if not file_path.is_absolute():
                file_path = self.working_dir / file_path

            return file_path.resolve()

        except Exception as e:
            logger.error("path_resolution_failed", path=path, error=str(e))
            return None

    def get_function_schema(self) -> Dict[str, Any]:
        """Get Function Calling Schema."""
        return {
            "name": "word_edit",
            "description": """编辑 Word 文档（结构化编辑，自动解包/打包）

⭐ 复杂 Word 编辑的首选工具，自动处理解包/编辑/打包流程。

功能：
- 自动解包 .docx 文件
- 结构化编辑操作（替换段落、插入内容、删除节点）
- 保留文档格式和结构
- 强大的 XML 级别编辑能力

使用场景：
- ✅ 结构化编辑（插入段落、重新组织内容）
- ✅ 精确内容替换（带上下文）
- ✅ 复杂多步骤编辑
- ✅ 需要 XML 级别控制的操作

简单文本替换？
→ 使用 find_replace_word 工具（更简单、更快）

操作类型：
1. replace_text: 替换文本内容
2. replace_paragraph: 替换整个段落
3. insert_after: 在指定文本后插入新段落
4. insert_before: 在指定文本前插入新段落
5. delete_paragraph: 删除包含指定文本的段落

示例：
- word_edit(path="report.docx", operation="replace_text", search="旧内容", replace="新内容")
- word_edit(path="report.docx", operation="insert_after", marker="结论：", content="补充说明")
- word_edit(path="report.docx", operation="replace_paragraph", contains="错误段落", new_content="正确内容")

参数说明：
- path: DOCX 文件路径
- operation: 操作类型（replace_text/replace_paragraph/insert_after/insert_before/delete_paragraph）
- search: 要查找的文本（replace_text 操作）
- replace: 替换后的文本（replace_text 操作）
- contains: 段落包含的文本（replace_paragraph/delete_paragraph 操作）
- marker: 标记文本（insert_after/insert_before 操作）
- content: 新内容（insert_after/insert_before/replace_paragraph 操作）
- output_file: 输出文件路径（可选，默认覆盖原文件）
- backup: 是否创建备份（默认 True）

决策流程：
1. 仅需简单文本替换？→ find_replace_word
2. 需要结构化编辑？→ word_edit（推荐）
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "DOCX 文件路径。示例：'report.docx' 或 'D:/work/report.docx'"
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["replace_text", "replace_paragraph", "insert_after", "insert_before", "delete_paragraph"],
                        "description": "操作类型。replace_text=替换文本, replace_paragraph=替换段落, insert_after=在标记后插入, insert_before=在标记前插入, delete_paragraph=删除段落"
                    },
                    "search": {
                        "type": "string",
                        "description": "要查找的文本（replace_text 操作必填）。示例：'旧术语'"
                    },
                    "replace": {
                        "type": "string",
                        "description": "替换后的文本（replace_text 操作必填）。示例：'新术语'"
                    },
                    "contains": {
                        "type": "string",
                        "description": "段落包含的文本（replace_paragraph/delete_paragraph 操作必填）。示例：'错误内容'"
                    },
                    "marker": {
                        "type": "string",
                        "description": "标记文本（insert_after/insert_before 操作必填）。示例：'结论：'"
                    },
                    "content": {
                        "type": "string",
                        "description": "新内容（insert_after/insert_before/replace_paragraph 操作必填）。示例：'补充说明内容'"
                    },
                    "new_content": {
                        "type": "string",
                        "description": "新内容的别名（与 content 二选一）"
                    },
                    "output_file": {
                        "type": "string",
                        "description": "输出文件路径（可选，默认覆盖原文件）。示例：'report_updated.docx'"
                    },
                    "backup": {
                        "type": "boolean",
                        "description": "是否创建备份（默认 True）",
                        "default": True
                    }
                },
                "required": ["path", "operation"]
            }
        }

    def is_available(self) -> bool:
        return True


# Import required modules
import shutil
from datetime import datetime

# Create tool instance
tool = WordEditTool()
