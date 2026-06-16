from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from typing import Any, Dict, List, Optional

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.path_config import get_data_registry

from .xml_utils import DrawioXmlError, apply_drawio_operations, normalize_drawio_xml


DRAWIO_BOARD_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


class CreateDrawioBoardTool(LLMTool):
    def __init__(self, name: str = "create_drawio_board"):
        description = (
            "Chart-mode only. Create or edit the interactive draw.io board. "
            "Use operation=create with mxCell XML for new/major diagrams; "
            "use operation=edit with add/update/delete/update_label/update_style/move_resize/connect/delete_with_edges "
            "operations. Operations may use target=selected with selected_cells. "
            "before first use, read these guides with read_file: "
            "app/agent/guides/drawio_board_workflow.md, "
            "app/agent/guides/drawio_xml_rules.md, and "
            "app/agent/guides/drawio_edit_policy.md. "
            "Do not use create_diagram_artifact for chart-mode interactive boards."
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
                before_xml = normalize_drawio_xml(current_xml or xml or "")
                normalized_xml = apply_drawio_operations(before_xml, operations or [], selected_cells)
            elif op == "create":
                before_xml = ""
                normalized_xml = normalize_drawio_xml(xml or current_xml or "")
            else:
                return {
                    "success": False,
                    "data": {"error": "invalid_operation"},
                    "summary": f"画板生成失败：不支持 operation={op}",
                }
        except DrawioXmlError as exc:
            return {"success": False, "data": {"error": str(exc)}, "summary": f"画板生成失败：{exc}"}

        changed = op == "create" or normalized_xml != before_xml
        operation_count = len(operations or []) if op == "edit" else 0
        changed_cells = _operation_cell_ids(operations or [], selected_cells) if op == "edit" and changed else []
        xml_ref = _store_drawio_xml(safe_artifact_id, normalized_xml)

        data = {
            "artifact_kind": "drawio_board",
            "artifact_id": safe_artifact_id,
            "board_id": safe_artifact_id,
            "title": safe_title,
            "version": 1,
            "operation": op,
            "changed": changed,
            "changed_cells": changed_cells,
            "applied_operations": operation_count,
            "xml_length": len(normalized_xml),
            "xml_sha256": xml_ref["sha256"],
            "xml_ref": xml_ref,
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
            "refs": {"artifacts": [xml_ref]},
            "summary": _build_summary(safe_title, op, operation_count, changed, changed_cells),
        }


def _operation_cell_ids(
    operations: List[Dict[str, Any]],
    selected_cells: Optional[List[Dict[str, Any]]],
) -> List[str]:
    cell_ids: List[str] = []
    for operation in operations:
        cell_id = str(operation.get("cell_id") or operation.get("edge_id") or "").strip()
        if not cell_id and str(operation.get("target") or "").strip() == "selected":
            cell_id = _first_selected_cell_id(selected_cells)
        if not cell_id and str(operation.get("operation") or "").strip().lower() == "connect":
            cell_id = str(operation.get("cell_id") or operation.get("edge_id") or "").strip()
        if cell_id and cell_id not in cell_ids:
            cell_ids.append(cell_id)
    return cell_ids


def _first_selected_cell_id(selected_cells: Optional[List[Dict[str, Any]]]) -> str:
    for cell in selected_cells or []:
        if isinstance(cell, dict):
            cell_id = str(cell.get("id") or cell.get("cell_id") or cell.get("cellId") or "").strip()
            if cell_id:
                return cell_id
    return ""


def _build_summary(
    title: str,
    operation: str,
    operation_count: int,
    changed: bool,
    changed_cells: List[str],
) -> str:
    if operation == "edit":
        if not changed:
            return f"画板编辑完成：{title}。目标内容已是期望值，未产生实际变更。"
        cell_part = f"，涉及单元：{', '.join(changed_cells)}" if changed_cells else ""
        return f"画板编辑完成：{title}。已应用 {operation_count} 个编辑操作{cell_part}。"
    return f"交互式画板已生成：{title}。无需再次加载参考图片，除非用户明确要求重新查看原图。"


def _store_drawio_xml(artifact_id: str, xml: str) -> Dict[str, Any]:
    digest = hashlib.sha256(xml.encode("utf-8")).hexdigest()
    safe_id = DRAWIO_BOARD_ID_PATTERN.sub("_", artifact_id).strip("._") or "drawio_board"
    storage_dir = (get_data_registry() / "drawio_boards" / safe_id).resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = storage_dir / f"{timestamp}_{digest[:12]}.drawio"
    path.write_text(xml, encoding="utf-8")
    local_path = str(path)
    return {
        "kind": "drawio_board_xml",
        "artifact_kind": "drawio_board",
        "artifact_id": artifact_id,
        "local_path": local_path,
        "path": local_path,
        "read_url": f"/api/file/{quote(local_path, safe='')}",
        "mime_type": "application/xml",
        "format": "drawio",
        "size_bytes": len(xml.encode("utf-8")),
        "sha256": digest,
    }
