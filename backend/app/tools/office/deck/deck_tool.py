from __future__ import annotations

import json
from typing import Any, Dict, Optional

from pydantic import ValidationError

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.create_pptx_tool import CreatePptxTool
from app.tools.office.deck.models import DeckSpec
from app.tools.office.deck.normalizer import normalize_deck_for_create_pptx
from app.tools.office.deck.validators import validate_deck_design


class CreatePptxFromDeckTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="create_pptx_from_deck",
            description=(
                "从 suyuan.deck.v2 设计稿生成可编辑 PPTX。"
                "调用前必须先阅读 backend/app/tools/office/deck/references/index.md、"
                "archetypes.md 和 checklist.md。"
                "本工具不兼容 suyuan.deck.v1，也不接受 create_pptx 的 title/bullets/table/image_full 等底层 slide type。"
            ),
            category=ToolCategory.QUERY,
            version="2.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        deck: Optional[Any] = None,
        output_file: Optional[str] = None,
        quality: str = "standard",
        run_validation: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if deck is None:
            return {
                "success": False,
                "data": {"error": "deck 参数缺失"},
                "summary": "创建PPT失败：deck 参数缺失",
            }

        if isinstance(deck, str):
            try:
                deck = json.loads(deck)
            except json.JSONDecodeError as exc:
                return {
                    "success": False,
                    "data": {"error": "deck_schema_invalid", "detail": f"deck 不是有效 JSON: {exc}"},
                    "summary": "创建PPT失败：deck 参数格式错误，必须是 suyuan.deck.v2 JSON 对象",
                }

        if not isinstance(deck, dict):
            return {
                "success": False,
                "data": {"error": "deck_schema_invalid", "detail": "deck 必须是对象"},
                "summary": "创建PPT失败：deck 必须是 suyuan.deck.v2 对象",
            }

        try:
            spec = DeckSpec.model_validate(deck)
        except ValidationError as exc:
            return {
                "success": False,
                "data": {
                    "error": "deck_schema_invalid",
                    "detail": str(exc),
                    "expected_version": "suyuan.deck.v2",
                    "hint": "create_pptx_from_deck 2.0 只接受 archetype 设计稿；底层 title/bullets/table/image_full 请改用 create_pptx。",
                },
                "summary": "创建PPT失败：deck 必须符合 suyuan.deck.v2，使用 slide.archetype 而不是 slide.type",
            }

        issues = validate_deck_design(spec)
        if issues:
            return {
                "success": False,
                "data": {"error": "deck_design_invalid", "issues": issues},
                "summary": f"Deck 设计规则校验失败：{issues[0]['type']}",
            }

        normalized = normalize_deck_for_create_pptx(spec)
        return await CreatePptxTool().execute(
            title=normalized["title"],
            slides=normalized["slides"],
            output_file=output_file,
            theme=normalized.get("theme"),
            design_brief=normalized.get("design_brief"),
            quality=quality,
            run_validation=run_validation,
            **kwargs,
        )

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": "create_pptx_from_deck",
            "description": "从 suyuan.deck.v2 设计稿生成可编辑 PPTX。调用前先读 deck/references 设计文档。",
            "parameters": {
                "type": "object",
                "properties": {
                    "deck": {"type": "object", "description": "符合 suyuan.deck.v2 的 PPT 设计稿"},
                    "output_file": {"type": "string", "description": "输出 PPTX 路径，可选"},
                    "quality": {"type": "string", "enum": ["draft", "standard", "strict"], "default": "standard"},
                    "run_validation": {"type": "boolean", "default": True},
                },
                "required": ["deck"],
            },
        }
