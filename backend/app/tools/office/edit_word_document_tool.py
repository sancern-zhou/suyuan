"""Agent-facing Word document editing wrapper."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from app.tools.artifact_utils import attach_document_artifact
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.accept_changes_tool import AcceptChangesTool
from app.tools.office.find_replace_tool import FindReplaceTool
from app.tools.office.word_edit_tool import WordEditTool

logger = structlog.get_logger()


class EditWordDocumentTool(LLMTool):
    """Single high-level Word editing entry point for agents."""

    SIMPLE_REPLACE_ACTIONS = {"find_replace", "simple_replace", "replace_all"}
    STRUCTURED_ACTIONS = {
        "replace_text",
        "replace_paragraph",
        "insert_after",
        "insert_before",
        "delete_paragraph",
    }
    REVISION_ACTIONS = {"accept_changes"}

    def __init__(self):
        super().__init__(
            name="edit_word_document",
            description=(
                "统一编辑 DOCX 文档的工具。用于简单查找替换、结构化段落编辑、接受修订；"
                "自动调用底层 Word 工具并返回右侧预览可识别的 document artifact。"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False,
        )
        self._find_replace_tool: Optional[FindReplaceTool] = None
        self._word_edit_tool: Optional[WordEditTool] = None
        self._accept_changes_tool: Optional[AcceptChangesTool] = None

    async def execute(
        self,
        path: str,
        action: str,
        find_text: Optional[str] = None,
        replace_text: Optional[str] = None,
        search: Optional[str] = None,
        replace: Optional[str] = None,
        contains: Optional[str] = None,
        marker: Optional[str] = None,
        content: Optional[str] = None,
        new_content: Optional[str] = None,
        output_file: Optional[str] = None,
        use_regex: bool = False,
        case_sensitive: bool = True,
        backup: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        normalized_action = str(action or "").strip().lower()
        if not normalized_action:
            return {
                "success": False,
                "data": {"error": "action 不能为空"},
                "summary": "Word 编辑失败：缺少 action",
            }

        try:
            if normalized_action in self.SIMPLE_REPLACE_ACTIONS:
                resolved_find_text = find_text or search
                if not resolved_find_text:
                    return {
                        "success": False,
                        "data": {"error": "简单替换需要 find_text 或 search"},
                        "summary": "Word 编辑失败：缺少查找文本",
                    }
                result = await self._find_replace().execute(
                    path=path,
                    find_text=resolved_find_text,
                    replace_text=replace_text if replace_text is not None else (replace or ""),
                    output_file=output_file,
                    use_regex=use_regex,
                    case_sensitive=case_sensitive,
                )
            elif normalized_action in self.STRUCTURED_ACTIONS:
                result = await self._word_edit().execute(
                    path=path,
                    operation=normalized_action,
                    search=search or find_text,
                    replace=replace if replace is not None else replace_text,
                    contains=contains,
                    marker=marker,
                    content=content,
                    new_content=new_content,
                    output_file=output_file,
                    backup=backup,
                )
            elif normalized_action in self.REVISION_ACTIONS:
                result = await self._accept_changes().execute(
                    input_file=path,
                    output_file=output_file or self._default_revision_output(path),
                )
            else:
                return {
                    "success": False,
                    "data": {
                        "error": (
                            "不支持的 action。可用值：find_replace/simple_replace/replace_all、"
                            "replace_text/replace_paragraph/insert_after/insert_before/delete_paragraph、"
                            "accept_changes"
                        )
                    },
                    "summary": "Word 编辑失败：action 不支持",
                }

            return self._normalize_result(result, normalized_action)
        except Exception as exc:
            logger.error("edit_word_document_failed", path=path, action=action, error=str(exc), exc_info=True)
            return {
                "success": False,
                "data": {"error": str(exc)},
                "summary": f"Word 编辑失败：{str(exc)[:80]}",
            }

    def _normalize_result(self, result: Dict[str, Any], action: str) -> Dict[str, Any]:
        if not result.get("success"):
            return result

        data = dict(result.get("data") or {})
        file_path = data.get("file_path") or data.get("output_file")
        if file_path:
            attach_document_artifact(
                data,
                file_path,
                kind="office",
                format="docx",
                preview_key="pdf_preview",
                generator=self.name,
                metadata={"action": action},
            )
        data["action"] = action
        return {
            **result,
            "data": data,
            "metadata": {"generator": self.name, "schema_version": "document_artifact.v1"},
        }

    def _find_replace(self) -> FindReplaceTool:
        if self._find_replace_tool is None:
            self._find_replace_tool = FindReplaceTool()
        return self._find_replace_tool

    def _word_edit(self) -> WordEditTool:
        if self._word_edit_tool is None:
            self._word_edit_tool = WordEditTool()
        return self._word_edit_tool

    def _accept_changes(self) -> AcceptChangesTool:
        if self._accept_changes_tool is None:
            self._accept_changes_tool = AcceptChangesTool()
        return self._accept_changes_tool

    def _default_revision_output(self, path: str) -> str:
        input_path = Path(path)
        return str(input_path.with_name(f"{input_path.stem}_accepted{input_path.suffix}"))

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": "edit_word_document",
            "description": (
                "统一编辑 DOCX。action=find_replace/simple_replace/replace_all 做简单替换；"
                "action=replace_text/replace_paragraph/insert_after/insert_before/delete_paragraph 做结构化编辑；"
                "action=accept_changes 接受修订。返回 file_path、pdf_preview 和 document artifact，不返回下载链接。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "DOCX 文件路径"},
                    "action": {
                        "type": "string",
                        "enum": [
                            "find_replace",
                            "simple_replace",
                            "replace_all",
                            "replace_text",
                            "replace_paragraph",
                            "insert_after",
                            "insert_before",
                            "delete_paragraph",
                            "accept_changes",
                        ],
                        "description": "编辑动作",
                    },
                    "find_text": {"type": "string", "description": "简单替换要查找的文本"},
                    "replace_text": {"type": "string", "description": "简单替换的新文本"},
                    "search": {"type": "string", "description": "replace_text 要查找的文本"},
                    "replace": {"type": "string", "description": "replace_text 替换文本"},
                    "contains": {"type": "string", "description": "段落操作的定位文本"},
                    "marker": {"type": "string", "description": "插入操作的定位文本"},
                    "content": {"type": "string", "description": "插入或替换段落的新内容"},
                    "new_content": {"type": "string", "description": "content 的别名"},
                    "output_file": {"type": "string", "description": "输出文件路径；可选"},
                    "use_regex": {"type": "boolean", "description": "简单替换是否使用正则", "default": False},
                    "case_sensitive": {"type": "boolean", "description": "简单替换是否大小写敏感", "default": True},
                    "backup": {"type": "boolean", "description": "结构化编辑是否备份原文件", "default": True},
                },
                "required": ["path", "action"],
            },
        }

    def is_available(self) -> bool:
        return True


tool = EditWordDocumentTool()
