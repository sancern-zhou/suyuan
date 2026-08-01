from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.boards.application import BoardApplicationService
from app.boards.quality import evaluate_drawio_quality
from app.db.database import async_session
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import board_product
from app.utils.path_config import get_data_registry

from .routing import DrawioRoutingError, route_drawio_candidate
from .xml_utils import DrawioXmlError, apply_drawio_operations, normalize_drawio_xml

DRAWIO_BOARD_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
logger = structlog.get_logger()


class CreateDrawioBoardTool(LLMTool):
    def __init__(
        self,
        name: str = "create_drawio_board",
        *,
        quality_service=None,
        candidate_persister=None,
    ):
        # Kept as an injectable compatibility attribute; candidate creation no longer invokes rendering.
        self.quality_service = quality_service
        self.candidate_persister = candidate_persister or self._persist_candidate
        description = (
            "Board-mode only. Create or edit the interactive draw.io board. "
            "Use operation=create with mxCell XML for new/major diagrams; "
            "use operation=edit with add/update/delete/update_label/update_style/move_resize/connect/delete_with_edges "
            "operations. Operations may use target=selected with selected_cells. "
            "before first use, read these guides with read_file: "
            "app/agent/guides/drawio_board_workflow.md, "
            "app/agent/guides/drawio_xml_rules.md, and "
            "app/agent/guides/drawio_edit_policy.md. "
            "You must classify the requested diagram type and read only the one or two matching drawio_patterns guides "
            "routed by drawio_board_workflow.md before calling this tool for a new, structural, or major edit; "
            "never read every pattern guide. Minor text, color, font, size, or position-only edits may skip pattern guides. "
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
                        "description": (
                            "mxCell fragment, complete mxGraphModel, or standard draw.io mxfile XML for create. "
                            "A standard mxfile must contain diagram/mxGraphModel/root; do not wrap mxGraphModel directly under mxfile."
                        ),
                    },
                    "operations": {
                        "type": "array",
                        "description": (
                            "Ordered edit operations. Each item must match exactly one operation-specific schema. "
                            "For connect, cell_id is the unique ID of the new edge and source_cell_id plus "
                            "target_cell_id are both required. Example: "
                            '{"operation":"connect","cell_id":"edge_alert_to_monitoring",'
                            '"source_cell_id":"alert_decision","target_cell_id":"fetch_monitoring"}.'
                        ),
                        "items": {
                            "oneOf": [
                                {
                                    "type": "object",
                                    "description": "Add one complete mxCell. The new cell ID is read from new_xml.",
                                    "properties": {
                                        "operation": {"const": "add"},
                                        "cell_id": {
                                            "type": "string",
                                            "description": "Optional; when provided, must equal the mxCell ID in new_xml.",
                                        },
                                        "new_xml": {"type": "string", "description": "One complete mxCell element."},
                                    },
                                    "required": ["operation", "new_xml"],
                                },
                                {
                                    "type": "object",
                                    "description": "Replace one mxCell with the complete mxCell in new_xml.",
                                    "properties": {
                                        "operation": {"const": "update"},
                                        "cell_id": {
                                            "type": "string",
                                            "description": "Optional; when provided, must equal the mxCell ID in new_xml.",
                                        },
                                        "new_xml": {"type": "string", "description": "One complete replacement mxCell."},
                                    },
                                    "required": ["operation", "new_xml"],
                                },
                                {
                                    "type": "object",
                                    "description": "Delete one cell while leaving unrelated edges unchanged.",
                                    "properties": {
                                        "operation": {"const": "delete"},
                                        "cell_id": {"type": "string", "description": "ID of the cell to delete."},
                                        "target": {"type": "string", "enum": ["selected"]},
                                    },
                                    "required": ["operation"],
                                    "anyOf": [{"required": ["cell_id"]}, {"required": ["target"]}],
                                },
                                {
                                    "type": "object",
                                    "description": "Delete one cell, its descendants, and all connected edges.",
                                    "properties": {
                                        "operation": {"const": "delete_with_edges"},
                                        "cell_id": {"type": "string", "description": "ID of the cell to delete."},
                                        "target": {"type": "string", "enum": ["selected"]},
                                    },
                                    "required": ["operation"],
                                    "anyOf": [{"required": ["cell_id"]}, {"required": ["target"]}],
                                },
                                {
                                    "type": "object",
                                    "description": "Change one cell label.",
                                    "properties": {
                                        "operation": {"const": "update_label"},
                                        "cell_id": {"type": "string", "description": "ID of the cell to relabel."},
                                        "target": {"type": "string", "enum": ["selected"]},
                                        "label": {"type": "string", "description": "Complete replacement label."},
                                    },
                                    "required": ["operation", "label"],
                                    "anyOf": [{"required": ["cell_id"]}, {"required": ["target"]}],
                                },
                                {
                                    "type": "object",
                                    "description": "Patch selected style keys or replace the complete style string.",
                                    "properties": {
                                        "operation": {"const": "update_style"},
                                        "cell_id": {"type": "string", "description": "ID of the cell to restyle."},
                                        "target": {"type": "string", "enum": ["selected"]},
                                        "style": {"type": "string", "description": "Complete replacement style string."},
                                        "style_patch": {
                                            "type": "object",
                                            "description": "Style keys to merge into the current style.",
                                        },
                                    },
                                    "required": ["operation"],
                                    "allOf": [
                                        {"anyOf": [{"required": ["cell_id"]}, {"required": ["target"]}]},
                                        {"anyOf": [{"required": ["style"]}, {"required": ["style_patch"]}]},
                                    ],
                                },
                                {
                                    "type": "object",
                                    "description": "Move or resize one cell using a partial geometry object.",
                                    "properties": {
                                        "operation": {"const": "move_resize"},
                                        "cell_id": {"type": "string", "description": "ID of the cell to move or resize."},
                                        "target": {"type": "string", "enum": ["selected"]},
                                        "geometry": {
                                            "type": "object",
                                            "description": "One or more of x, y, width, and height.",
                                            "properties": {
                                                "x": {"type": "number"},
                                                "y": {"type": "number"},
                                                "width": {"type": "number"},
                                                "height": {"type": "number"},
                                            },
                                            "minProperties": 1,
                                        },
                                    },
                                    "required": ["operation", "geometry"],
                                    "anyOf": [{"required": ["cell_id"]}, {"required": ["target"]}],
                                },
                                {
                                    "type": "object",
                                    "description": (
                                        "Create a new edge. cell_id is required and must be a unique ID for the new edge; "
                                        "source_cell_id and target_cell_id are required endpoint IDs."
                                    ),
                                    "properties": {
                                        "operation": {"const": "connect"},
                                        "cell_id": {
                                            "type": "string",
                                            "description": "Required unique ID for the new edge; it must not already exist.",
                                        },
                                        "source_cell_id": {
                                            "type": "string",
                                            "description": "Required source cell ID; use selected to reference the selected cell.",
                                        },
                                        "target_cell_id": {
                                            "type": "string",
                                            "description": "Required target cell ID; use selected to reference the selected cell.",
                                        },
                                    },
                                    "required": ["operation", "cell_id", "source_cell_id", "target_cell_id"],
                                    "examples": [{
                                        "operation": "connect",
                                        "cell_id": "edge_alert_to_monitoring",
                                        "source_cell_id": "alert_decision",
                                        "target_cell_id": "fetch_monitoring",
                                    }],
                                },
                            ],
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
            return {
                "success": False,
                "data": {
                    "error_code": "artifact_identity_required",
                    "field": "artifact_id" if not safe_artifact_id else "title",
                    "retryable": True,
                },
                "metadata": {"tool_name": self.name, "generator": self.name},
                "summary": "画板生成失败：缺少 artifact_id 或 title。",
            }

        try:
            op = str(operation or "create").strip().lower()
            if op == "edit":
                before_xml = normalize_drawio_xml(current_xml or xml or "")
                requested_operations = operations or []
                if not requested_operations:
                    raise DrawioXmlError(
                        "operations are required for edit",
                        error_code="operations_required",
                        field="operations",
                    )
                normalized_xml = before_xml
                applied_operation_count = 0
                changed_cells: List[str] = []
                for operation_index, requested_operation in enumerate(requested_operations):
                    try:
                        next_xml = apply_drawio_operations(
                            normalized_xml,
                            [requested_operation],
                            selected_cells,
                        )
                    except DrawioXmlError as exc:
                        exc.operation_index = operation_index
                        raise
                    if next_xml != normalized_xml:
                        applied_operation_count += 1
                        for cell_id in _changed_cell_ids(normalized_xml, next_xml):
                            if cell_id not in changed_cells:
                                changed_cells.append(cell_id)
                    normalized_xml = next_xml
            elif op == "create":
                before_xml = ""
                normalized_xml = normalize_drawio_xml(xml or current_xml or "")
                applied_operation_count = 0
                changed_cells = []
            else:
                return {
                    "success": False,
                    "data": {
                        "error": "invalid_operation",
                        "error_code": "invalid_operation",
                        "field": "operation",
                        "retryable": True,
                    },
                    "metadata": {"tool_name": self.name, "generator": self.name},
                    "summary": f"画板生成失败：不支持 operation={op}",
                }
        except DrawioXmlError as exc:
            return {
                "success": False,
                "data": {
                    "error": str(exc),
                    "error_code": exc.error_code,
                    "operation_index": exc.operation_index,
                    "field": exc.field,
                    "retryable": exc.retryable,
                },
                "metadata": {"tool_name": self.name, "generator": self.name},
                "summary": f"画板生成失败：{exc}",
            }

        changed = op == "create" or normalized_xml != before_xml
        operation_count = applied_operation_count
        session_id = str(kwargs.get("_session_id") or "").strip()
        agent_run_id = str(kwargs.get("_agent_run_id") or "").strip()
        routing_metrics = None
        routing_status = None
        routing_issues: List[Dict[str, Any]] = []
        if session_id and agent_run_id:
            try:
                routing_result = route_drawio_candidate(normalized_xml)
            except DrawioRoutingError as exc:
                routing_status = "fallback"
                routing_issues = [_non_blocking_routing_issue(exc.issue)]
            except Exception as exc:
                routing_issue = {
                    "code": "edge_routing_failed",
                    "cause": "router_internal_error",
                    "repair_actions": [{"action": "regenerate_simplified_layout"}],
                    "retry_strategy": "regenerate_simplified_layout_then_edges",
                    "failure_fingerprint": "edge_routing_failed:router_internal_error",
                    "preserved_original_edge": True,
                    "message": "自动路由器出现异常；已保留原始连线并继续生成画板",
                    "error": str(exc),
                }
                routing_status = "fallback"
                routing_issues = [_non_blocking_routing_issue(routing_issue)]
            else:
                normalized_xml = routing_result.xml
                routing_metrics = routing_result.metrics
                routing_status = routing_result.status
                routing_issues = [dict(issue) for issue in routing_result.issues]
            logger.info(
                "drawio_routing_completed",
                session_id=session_id,
                agent_run_id=agent_run_id,
                status=routing_status,
                edge_count=(routing_metrics or {}).get("edge_count", 0),
                rerouted=(routing_metrics or {}).get("rerouted_edge_count", 0),
                unchanged_safe=(routing_metrics or {}).get("unchanged_safe_edge_count", 0),
                degraded=(routing_metrics or {}).get("degraded_edge_count", len(routing_issues)),
                remaining_intersections=(routing_metrics or {}).get("remaining_intersection_count", 0),
                failure_fingerprints=[
                    issue.get("failure_fingerprint")
                    for issue in routing_issues
                    if issue.get("failure_fingerprint")
                ],
            )
            if op == "edit" and normalized_xml != before_xml:
                changed = True
                for cell_id in _changed_cell_ids(before_xml, normalized_xml):
                    if cell_id not in changed_cells:
                        changed_cells.append(cell_id)
        xml_ref = (
            {}
            if session_id and agent_run_id
            else _store_drawio_xml(safe_artifact_id, normalized_xml)
        )
        base_revision = int(kwargs.get("_base_revision") or 0)
        server_board_id = str(kwargs.get("_board_id") or "").strip() or None
        candidate_payload = None
        quality_report = None
        if session_id and agent_run_id:
            static_report = evaluate_drawio_quality(normalized_xml)
            if routing_metrics:
                static_report["metrics"] = {
                    **static_report.get("metrics", {}),
                    **routing_metrics,
                }
            if routing_status:
                static_report["routing_status"] = routing_status
                static_report["routing_issues"] = routing_issues
                if routing_issues:
                    static_report.setdefault("warnings", []).extend(
                        {
                            "code": "edge_routing_degraded",
                            "edge_id": issue.get("edge_id"),
                            "message": issue.get("message") or "连线保留原始路径",
                        }
                        for issue in routing_issues
                    )
                    if static_report.get("status") == "passed":
                        static_report["status"] = "warning"
            if static_report["status"] == "failed":
                return {
                    "status": "error",
                    "success": False,
                    "data": {
                        "artifact_kind": "drawio_board",
                        "error_code": "board_quality_failed",
                        "quality_report": static_report,
                        "retryable": True,
                    },
                    "metadata": {"tool_name": self.name, "generator": self.name},
                    "summary": "画板质量硬校验失败，请根据质量报告修复后重试。",
                }
            quality_report = {**static_report, "render_status": "pending"}
            candidate_payload = await self.candidate_persister(
                session_id=session_id,
                board_id=server_board_id,
                title=safe_title,
                base_revision=base_revision,
                agent_run_id=agent_run_id,
                xml=normalized_xml,
                quality_status="pending",
                quality_report=quality_report,
                screenshot_ref=None,
                summary=_build_summary(safe_title, op, operation_count, changed, changed_cells),
            )
            xml_ref = candidate_payload.get("xml_ref") or _store_drawio_xml(
                safe_artifact_id, normalized_xml
            )
            if candidate_payload.get("lifecycle_status") == "accepted":
                return _accepted_retry_result(candidate_payload, safe_title)

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
            "xml_sha256": xml_ref.get("sha256") or hashlib.sha256(normalized_xml.encode("utf-8")).hexdigest(),
            "xml_ref": xml_ref,
        }
        if candidate_payload and quality_report:
            candidate_lifecycle = candidate_payload.get("lifecycle_status") or "candidate"
            data.update({
                "board_id": candidate_payload["board_id"],
                "candidate_version_id": candidate_payload["candidate_version_id"],
                "version_id": candidate_payload["candidate_version_id"],
                "version": candidate_payload["version_number"],
                "revision": candidate_payload["revision"],
                "lifecycle_status": candidate_lifecycle,
                "quality_status": "pending",
                "quality_report": quality_report,
                "render_status": "pending",
                "preview_candidate": candidate_lifecycle == "candidate",
                "requires_visual_review": candidate_lifecycle == "candidate",
            })
        if routing_status:
            data.update({
                "routing_status": routing_status,
                "routing_metrics": routing_metrics or {},
                "routing_issues": routing_issues,
                "routing_issue": routing_issues[0] if routing_issues else None,
            })
        metadata = {
            "generator": self.name,
            "artifact_kind": "drawio_board",
            "panel": "board",
            "editable": True,
            "schema_version": "v1.0",
        }
        result = {
            "status": "success",
            "success": True,
            "data": data,
            "metadata": metadata,
            "refs": {"artifacts": [xml_ref]},
            "resources": board_product(
                xml_path=xml_ref["local_path"],
                artifact_id=safe_artifact_id,
                tool_name=self.name,
            ),
            "summary": _build_summary(safe_title, op, operation_count, changed, changed_cells),
        }
        if candidate_payload:
            if routing_status == "fallback":
                result["summary"] += (
                    " 自动路由器整体异常，已完整使用路由前的规范化 XML 继续生成画板。"
                )
            elif routing_issues:
                result["summary"] += (
                    f" {len(routing_issues)} 条连线无法安全避让，已保留原始路径。"
                )
            result["summary"] += (
                " 候选画板已可在前端预览；建议调用 render_drawio_board_candidate "
                "生成截图并完成视觉检查。"
            )
        return result

    async def _persist_candidate(
        self,
        *,
        session_id: str,
        board_id: Optional[str],
        title: str,
        base_revision: int,
        agent_run_id: str,
        xml: str,
        quality_status: str,
        quality_report: Dict[str, Any],
        screenshot_ref: Optional[Dict[str, Any]],
        summary: str,
        lifecycle_status: str = "candidate",
    ) -> Dict[str, Any]:
        receipt = await BoardApplicationService(async_session).create_candidate(
            session_id=session_id,
            board_id=board_id,
            title=title,
            base_revision=base_revision,
            agent_run_id=agent_run_id,
            xml=xml,
            quality_status=quality_status,
            quality_report=quality_report,
            screenshot_ref=screenshot_ref,
            summary=summary,
            lifecycle_status=lifecycle_status,
        )
        return asdict(receipt)


def _operation_cell_ids(
    operations: List[Dict[str, Any]],
    selected_cells: Optional[List[Dict[str, Any]]],
) -> List[str]:
    cell_ids: List[str] = []
    for operation in operations:
        cell_id = str(operation.get("cell_id") or operation.get("edge_id") or "").strip()
        if not cell_id and str(operation.get("operation") or "").strip().lower() in {"add", "update"}:
            match = re.search(r'<mxCell\b[^>]*\bid=["\']([^"\']+)["\']', str(operation.get("new_xml") or ""))
            cell_id = match.group(1) if match else ""
        if not cell_id and str(operation.get("target") or "").strip() == "selected":
            cell_id = _first_selected_cell_id(selected_cells)
        if not cell_id and str(operation.get("operation") or "").strip().lower() == "connect":
            cell_id = str(operation.get("cell_id") or operation.get("edge_id") or "").strip()
        if cell_id and cell_id not in cell_ids:
            cell_ids.append(cell_id)
    return cell_ids


def _accepted_retry_result(payload: Dict[str, Any], title: str) -> Dict[str, Any]:
    xml_ref = payload["xml_ref"]
    return {
        "status": "success",
        "success": True,
        "data": {
            "artifact_kind": "drawio_board",
            "board_id": payload["board_id"],
            "title": title,
            "candidate_version_id": payload["candidate_version_id"],
            "version_id": payload["candidate_version_id"],
            "version": payload["version_number"],
            "revision": payload["revision"],
            "lifecycle_status": "accepted",
            "xml_ref": xml_ref,
            "requires_visual_review": False,
        },
        "metadata": {
            "tool_name": "create_drawio_board",
            "generator": "create_drawio_board",
            "artifact_kind": "drawio_board",
        },
        "refs": {"artifacts": [xml_ref]},
        "summary": "该画板内容已在本轮运行中提交，本次返回既有版本。",
    }


def _changed_cell_ids(before_xml: str, after_xml: str) -> List[str]:
    """Return IDs whose serialized mxCell was added, removed, or changed."""
    def cell_map(xml: str) -> tuple[List[str], Dict[str, str]]:
        root = ET.fromstring(xml)
        cells = [cell for cell in root.iter("mxCell") if cell.attrib.get("id") not in {None, "0", "1"}]
        order = [cell.attrib["id"] for cell in cells]
        return order, {cell.attrib["id"]: ET.tostring(cell, encoding="unicode") for cell in cells}

    before_order, before = cell_map(before_xml)
    after_order, after = cell_map(after_xml)
    ordered_ids = before_order + [cell_id for cell_id in after_order if cell_id not in before]
    return [cell_id for cell_id in ordered_ids if before.get(cell_id) != after.get(cell_id)]


def _first_selected_cell_id(selected_cells: Optional[List[Dict[str, Any]]]) -> str:
    for cell in selected_cells or []:
        if isinstance(cell, dict):
            cell_id = str(cell.get("id") or cell.get("cell_id") or cell.get("cellId") or "").strip()
            if cell_id:
                return cell_id
    return ""


def _non_blocking_routing_issue(issue: Dict[str, Any]) -> Dict[str, Any]:
    message = str(issue.get("message") or "自动避让未完成")
    continuation = "已保留原始连线并继续生成画板"
    if continuation not in message:
        message = f"{message.rstrip('；。')}；{continuation}"
    return {
        **issue,
        "message": message,
        "severity": "warning",
        "blocking": False,
        "retry_required": False,
        "preserved_original_edge": True,
    }


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
        "mime_type": "application/xml",
        "format": "drawio",
        "size_bytes": len(xml.encode("utf-8")),
        "sha256": digest,
    }
