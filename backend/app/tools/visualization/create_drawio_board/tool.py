from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.tools.base.tool_interface import LLMTool, ToolCategory

from .xml_utils import DrawioXmlError, apply_drawio_operations, normalize_drawio_xml


class CreateDrawioBoardTool(LLMTool):
    def __init__(self, name: str = "create_drawio_board"):
        description = (
            "Chart-mode only. Create or edit the interactive draw.io board. "
            "Use operation=create with mxCell XML for new/major diagrams; "
            "use operation=edit with add/update/delete/update_label/update_style/move_resize/connect/delete_with_edges "
            "operations based on board_context.current_xml. Operations may use target=selected with selected_cells. "
            "before first use, read these guides with read_file: "
            "app/agent/guides/drawio_board_workflow.md, "
            "app/agent/guides/drawio_xml_rules.md, and "
            "app/agent/guides/drawio_edit_policy.md. "
            "Treat board_context.current_xml as authoritative, prefer selected_cells for local edits, "
            "and do not use create_diagram_artifact for chart-mode interactive boards."
        )
        function_schema = {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["create", "edit"], "default": "create"},
                    "artifact_id": {"type": "string"},
                    "title": {"type": "string"},
                    "xml": {
                        "type": "string",
                        "description": "mxCell fragment, mxGraphModel, or mxfile XML for create.",
                    },
                    "current_xml": {
                        "type": "string",
                        "description": "Authoritative current board XML for edit.",
                    },
                    "operations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "operation": {
                                    "type": "string",
                                    "enum": [
                                        "add",
                                        "update",
                                        "delete",
                                        "delete_with_edges",
                                        "update_label",
                                        "update_style",
                                        "move_resize",
                                        "connect",
                                    ],
                                },
                                "cell_id": {"type": "string"},
                                "target": {"type": "string", "description": "Use selected to target the first selected cell."},
                                "new_xml": {"type": "string"},
                                "label": {"type": "string"},
                                "style": {"type": "string"},
                                "style_patch": {"type": "object"},
                                "geometry": {"type": "object"},
                                "source_cell_id": {"type": "string"},
                                "target_cell_id": {"type": "string"},
                            },
                            "required": ["operation"],
                        },
                    },
                    "selected_cells": {
                        "type": "array",
                        "description": "Structured selected cells from board_context.selected_cells; used when operation target=selected.",
                        "items": {"type": "object"},
                    },
                },
                "required": ["artifact_id", "title"],
            },
        }
        super().__init__(
            name=name,
            description=description,
            category=ToolCategory.VISUALIZATION,
            function_schema=function_schema,
            version="1.0.0",
        )

    async def execute(
        self,
        operation: str = "create",
        artifact_id: Optional[str] = None,
        title: Optional[str] = None,
        xml: Optional[str] = None,
        current_xml: Optional[str] = None,
        operations: Optional[List[Dict[str, Any]]] = None,
        selected_cells: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        safe_artifact_id = str(artifact_id or "").strip()
        safe_title = str(title or "").strip()
        if not safe_artifact_id or not safe_title:
            return {"success": False, "data": None, "summary": "画板生成失败：缺少 artifact_id 或 title。"}

        try:
            op = str(operation or "create").strip().lower()
            if op == "edit":
                normalized_xml = apply_drawio_operations(current_xml or xml or "", operations or [], selected_cells)
            elif op == "create":
                normalized_xml = normalize_drawio_xml(xml or current_xml or "")
            else:
                return {
                    "success": False,
                    "data": {"error": "invalid_operation"},
                    "summary": f"画板生成失败：不支持 operation={op}",
                }
        except DrawioXmlError as exc:
            return {"success": False, "data": {"error": str(exc)}, "summary": f"画板生成失败：{exc}"}

        data = {
            "artifact_kind": "drawio_board",
            "artifact_id": safe_artifact_id,
            "board_id": safe_artifact_id,
            "title": safe_title,
            "xml": normalized_xml,
            "version": 1,
        }
        metadata = {
            "generator": self.name,
            "artifact_kind": "drawio_board",
            "panel": "board",
            "editable": True,
            "schema_version": "v1.0",
        }
        return {
            "status": "success",
            "success": True,
            "data": data,
            "metadata": metadata,
            "summary": f"交互式画板已生成：{safe_title}",
        }
