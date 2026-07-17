"""Focused system prompt for the interactive draw.io board agent."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def build_board_prompt(
    available_tools: List[str],
    memory_context: Optional[str] = None,
    memory_file_path: Optional[str] = None,
    board_context: Optional[Dict[str, Any]] = None,
    run_contract: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a compact board-only prompt with structured runtime state."""
    context = board_context if isinstance(board_context, dict) else {}
    contract = run_contract if isinstance(run_contract, dict) else {}
    current_xml = (
        context.get("current_xml")
        or context.get("currentXml")
        or context.get("xml")
        or ""
    )
    selected_cells = context.get("selected_cells") or context.get("selectedCells") or []
    state = {
        "board_run_contract": contract,
        "board_version": context.get("version"),
        "dirty": bool(context.get("dirty", False)),
        "selected_cells": selected_cells,
        "viewport": context.get("viewport") or {},
        "available_tools": available_tools,
    }

    parts = [
        "你是画板创作智能体，专门创建、检查和编辑可交互 draw.io 画板。\n",
        "你负责信息结构、节点层级、连线语义、空间布局、配色和可读性。\n",
        "运行时会通过 board_run_contract、工具结果和完成门禁管理是否需要执行修改；",
        "不要自行臆测工具是否成功。\n\n",
        "## 当前运行状态\n```json\n",
        json.dumps(state, ensure_ascii=False, indent=2, default=str),
        "\n```\n\n",
        "## 当前画板 XML\n```xml\n",
        str(current_xml),
        "\n```\n",
    ]
    if memory_context and memory_context.strip():
        parts.extend(["\n## 长期偏好\n", memory_context.strip(), "\n"])
    return "".join(parts)
