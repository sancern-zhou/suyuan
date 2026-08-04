from __future__ import annotations

import asyncio
from typing import Any

from app.services.map_program_receipts import map_program_receipt_store
from app.tools.base.tool_interface import LLMTool, ToolCategory


def _layer_render_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    layers = receipt.get("layers") if isinstance(receipt, dict) else []
    layers = layers if isinstance(layers, list) else []
    rendered_layers: list[dict[str, Any]] = []
    empty_layers: list[dict[str, Any]] = []

    for layer in layers:
        if not isinstance(layer, dict):
            continue
        layer_status = layer.get("status")
        feature_count = layer.get("feature_count") or 0
        layer_summary = {
            "layer_id": layer.get("layer_id"),
            "status": layer_status,
            "feature_count": feature_count,
        }
        file_path = layer.get("file_path")
        if file_path:
            layer_summary["file_path"] = file_path
        if layer_status == "layer_rendered" and feature_count > 0:
            rendered_layers.append(layer_summary)
        elif layer_status == "layer_empty" or feature_count == 0:
            empty_layers.append(layer_summary)

    return {
        "rendered_layers": rendered_layers,
        "empty_layers": empty_layers,
        "visual_interaction_completed": receipt.get("status") == "executed" and bool(rendered_layers),
    }


def _receipt_success_summary(program_id: str, render_summary: dict[str, Any]) -> str:
    if render_summary["visual_interaction_completed"]:
        layer_text = ", ".join(
            " ".join(
                part
                for part in [
                    str(layer.get("layer_id")),
                    f"feature_count={layer.get('feature_count')}",
                    f"file_path={layer.get('file_path')}" if layer.get("file_path") else "",
                ]
                if part
            )
            for layer in render_summary["rendered_layers"]
        )
        return (
            f"前端地图程序 {program_id} 已执行完成，已渲染图层：{layer_text}。"
            "本轮视觉交互目标已完成，用户已真实看见对应地图变化；请不要再次调用相同 visual_interaction，直接向用户说明地图已更新。"
        )
    if render_summary["empty_layers"]:
        layer_text = ", ".join(
            " ".join(
                part
                for part in [
                    str(layer.get("layer_id")),
                    f"feature_count={layer.get('feature_count')}",
                    f"file_path={layer.get('file_path')}" if layer.get("file_path") else "",
                ]
                if part
            )
            for layer in render_summary["empty_layers"]
        )
        return (
            f"前端地图程序 {program_id} 已回传执行回执，但图层未渲染出要素：{layer_text}。"
            "请检查 file_path、字段或筛选条件，不要回复已显示成功。"
        )
    return f"前端地图程序 {program_id} 已回传执行回执，但未确认有图层真实渲染。"


MAP_PROGRAM_RECEIPT_SCHEMA = {
    "name": "get_map_program_receipt",
    "description": (
        "查询前端地图对 map_program 的执行回执。用于确认 visual_interaction 生成的视觉交互程序是否真的被前端执行、"
        "用户真实看见的图层是否已渲染、feature_count 是否大于 0。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "问数会话 ID。",
            },
            "program_id": {
                "type": "string",
                "description": "visual_interaction 返回的 map_program.program_id。",
            },
        },
        "required": ["session_id", "program_id"],
    },
}


WAIT_MAP_PROGRAM_RECEIPT_SCHEMA = {
    "name": "wait_map_program_receipt",
    "description": (
        "等待前端视觉交互执行回执。visual_interaction 返回 map_program 后，前端会异步执行地图渲染并回传 receipt；"
        "本工具用于等待该 receipt，确认用户真实看见图层、视图或要素变化，避免在地图真实渲染前提前宣布成功。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "问数会话 ID。"},
            "program_id": {"type": "string", "description": "visual_interaction 返回的 map_program.program_id。"},
            "wait_timeout": {
                "type": "number",
                "description": "最多等待秒数，默认8，范围0-60。",
                "default": 8,
            },
            "wait_interval": {
                "type": "number",
                "description": "检查间隔秒数，默认0.5，范围0.05-5。",
                "default": 0.5,
            },
        },
        "required": ["session_id", "program_id"],
    },
}


class MapProgramReceiptTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="get_map_program_receipt",
            description="Read frontend visual interaction receipts for a map_program.",
            category=ToolCategory.QUERY,
            function_schema=MAP_PROGRAM_RECEIPT_SCHEMA,
            version="0.1.0",
            requires_context=False,
        )

    async def execute(self, session_id: str, program_id: str, **_: Any) -> dict[str, Any]:
        receipt = map_program_receipt_store.get(session_id, program_id)
        if receipt is None:
            return {
                "success": False,
                "error": {
                    "code": "MAP_PROGRAM_RECEIPT_NOT_FOUND",
                    "message": f"No frontend receipt for session_id={session_id}, program_id={program_id}",
                },
                "data": {
                    "session_id": session_id,
                    "program_id": program_id,
                    "receipt": None,
                },
            }

        return {
            "success": True,
            "data": {
                "session_id": session_id,
                "program_id": program_id,
                "receipt": receipt,
            },
        }


class WaitMapProgramReceiptTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="wait_map_program_receipt",
            description="Wait until the frontend confirms the user-visible map_program result.",
            category=ToolCategory.QUERY,
            function_schema=WAIT_MAP_PROGRAM_RECEIPT_SCHEMA,
            version="0.1.0",
            requires_context=False,
        )

    async def execute(
        self,
        session_id: str,
        program_id: str,
        wait_timeout: float = 8.0,
        wait_interval: float = 0.5,
        **_: Any,
    ) -> dict[str, Any]:
        session_id = (session_id or "").strip()
        program_id = (program_id or "").strip()
        if not session_id or not program_id:
            return self._failed(
                session_id=session_id,
                program_id=program_id,
                code="MAP_PROGRAM_RECEIPT_WAIT_ARGUMENTS_REQUIRED",
                message="session_id and program_id are required.",
                wait_timed_out=False,
                wait_polls=0,
            )

        wait_timeout = self._clamp_float(wait_timeout, 0.0, 60.0, 8.0)
        wait_interval = self._clamp_float(wait_interval, 0.05, 5.0, 0.5)
        max_polls = max(1, int(wait_timeout / wait_interval) + 1)

        for poll_index in range(max_polls):
            receipt = map_program_receipt_store.get(session_id, program_id)
            if receipt is not None:
                render_summary = _layer_render_summary(receipt)
                completed = render_summary["visual_interaction_completed"]
                next_action = "answer_user" if completed else "inspect_or_fix_map_program"
                return {
                    "status": "success",
                    "success": True,
                    "metadata": {
                        "tool_name": "wait_map_program_receipt",
                        "generator": "wait_map_program_receipt",
                        "schema_version": "0.1",
                        "session_id": session_id,
                        "program_id": program_id,
                        "wait_timed_out": False,
                        "wait_polls": poll_index + 1,
                        "map_control_completed": completed,
                        "visual_interaction_completed": completed,
                        "next_action": next_action,
                        "do_not_repeat_visual_interaction": completed,
                    },
                    "data": {
                        "session_id": session_id,
                        "program_id": program_id,
                        "receipt": receipt,
                        "program": map_program_receipt_store.get_program_status(session_id, program_id),
                        "wait_timed_out": False,
                        "wait_polls": poll_index + 1,
                        "map_control_completed": completed,
                        "visual_interaction_completed": completed,
                        "next_action": next_action,
                        "do_not_repeat_visual_interaction": completed,
                        "rendered_layers": render_summary["rendered_layers"],
                        "empty_layers": render_summary["empty_layers"],
                    },
                    "summary": _receipt_success_summary(program_id, render_summary),
                }
            if poll_index < max_polls - 1:
                await asyncio.sleep(wait_interval)

        return {
            "status": "success",
            "success": True,
            "metadata": {
                "tool_name": "wait_map_program_receipt",
                "generator": "wait_map_program_receipt",
                "schema_version": "0.1",
                "session_id": session_id,
                "program_id": program_id,
                "wait_timed_out": True,
                "wait_polls": max_polls,
            },
            "data": {
                "session_id": session_id,
                "program_id": program_id,
                "receipt": None,
                "program": map_program_receipt_store.get_program_status(session_id, program_id),
                "wait_timed_out": True,
                "wait_polls": max_polls,
            },
            "summary": f"等待前端地图程序 {program_id} 回执超过 {wait_timeout:g} 秒。",
        }

    def _failed(
        self,
        *,
        session_id: str,
        program_id: str,
        code: str,
        message: str,
        wait_timed_out: bool,
        wait_polls: int,
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": {"code": code, "message": message},
            "metadata": {
                "tool_name": "wait_map_program_receipt",
                "generator": "wait_map_program_receipt",
                "schema_version": "0.1",
                "session_id": session_id,
                "program_id": program_id,
                "wait_timed_out": wait_timed_out,
                "wait_polls": wait_polls,
            },
            "data": None,
            "summary": f"等待地图回执失败：{message}",
        }

    def _clamp_float(self, value: Any, minimum: float, maximum: float, default: float) -> float:
        try:
            parsed = float(value)
        except Exception:
            return default
        return max(minimum, min(maximum, parsed))
