"""Focused system prompt for the interactive draw.io board agent."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def build_board_prompt(
    available_tools: List[str],
    memory_context: Optional[str] = None,
    memory_file_path: Optional[str] = None,
    board_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a compact board-only prompt with structured runtime state."""
    context = board_context if isinstance(board_context, dict) else {}
    current_xml = (
        context.get("current_xml")
        or context.get("currentXml")
        or context.get("xml")
        or ""
    )
    selected_cells = context.get("selected_cells") or context.get("selectedCells") or []
    state = {
        "board_version": context.get("version"),
        "dirty": bool(context.get("dirty", False)),
        "selected_cells": selected_cells,
        "viewport": context.get("viewport") or {},
        "current_request_images": context.get("current_request_images") or [],
        "authority_policy": {
            "structure": "current_xml",
            "visual_effect": "current_request_images",
            "on_conflict": "report_the_observed_difference",
        },
        "last_execution": context.get("last_execution"),
        "available_tools": available_tools,
    }

    parts = [
        "你是画板创作智能体，专门创建、检查和编辑可交互 draw.io 画板。\n",
        "你负责信息结构、节点层级、连线语义、空间布局、配色和可读性。\n",
        "是否调用工具由你根据用户请求和当前上下文自主决定。\n\n",
        "## 绘制前渐进读取规范\n",
        "首次执行本轮实质性画板任务时，先读取基础规范：",
        "`app/agent/guides/drawio_board_workflow.md`、",
        "`app/agent/guides/drawio_xml_rules.md` 和 ",
        "`app/agent/guides/drawio_edit_policy.md`。\n",
        "然后根据绘制需求识别主要图形类型，按照工作流中的专项设计文档路由，",
        "最多读取 1 至 2 份最匹配的专项设计文档。",
        "禁止一次性读取全部 `drawio_patterns` 文档，也不要为了保险读取无关规范。\n",
        "完成必要阅读后，才可调用 `create_drawio_board` 新建、结构性编辑或大幅重构画板。\n",
        "仅修改文字、颜色、字号、尺寸或位置，且不改变层级、关系、连线语义或主要布局时，",
        "可以跳过专项设计文档，但仍须遵守三份基础规范并优先使用局部 edit operations。\n\n",
        "## 视觉质量闭环\n",
        "`create_drawio_board` 会先返回候选 XML，前端可立即预览，不会等待截图。\n",
        "一般情况下，建议随后调用 `render_drawio_board_candidate` 生成截图并实际检查视觉效果。\n",
        "如果视觉效果不理想，可基于候选 XML 继续局部修改并重新截图；",
        "满意后可调用 `accept_drawio_board_candidate` 正式提交。\n",
        "截图检查和接受属于推荐流程，由你结合任务、截图状态和现有上下文自主决定；",
        "截图缺失或失败本身不构成强制阻断。\n\n",
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
