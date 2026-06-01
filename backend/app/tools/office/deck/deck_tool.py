from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.create_pptx_from_template_tool import CreatePptxFromTemplateTool
from app.tools.office.create_pptx_tool import CreatePptxTool
from app.tools.office.deck.models import DeckSpec
from app.tools.office.deck.normalizer import normalize_deck_for_create_pptx
from app.tools.office.deck.template_manifest import TemplateManifest
from app.tools.office.deck.visual_rules import validate_visual_rules


def build_semantic_values_from_deck(deck: DeckSpec) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for slide in deck.slides:
        prefix = slide.type
        if slide.type == "cover":
            values["cover.title"] = slide.title
            if slide.subtitle:
                values["cover.subtitle"] = slide.subtitle
            continue
        values[f"{prefix}.title"] = slide.title
        if slide.message:
            values[f"{prefix}.message"] = slide.message
        if slide.visual and slide.visual.asset:
            key = "main_map" if slide.visual.kind == "map" else "main_visual"
            values[f"{prefix}.{key}"] = {"type": "image", "path": slide.visual.asset}
        if slide.insights:
            values[f"{prefix}.key_findings"] = "\n".join(slide.insights)
        if slide.actions:
            values[f"{prefix}.actions"] = "\n".join(slide.actions)
        if slide.metrics:
            values[f"{prefix}.metrics"] = "\n".join(
                f"{metric.label}: {metric.value}{metric.unit or ''}" for metric in slide.metrics
            )
            for index, metric in enumerate(slide.metrics[:4], start=1):
                values[f"metric_{index}.label"] = metric.label
                values[f"metric_{index}.value"] = f"{metric.value}{metric.unit or ''}"
                note = metric.delta or metric.tone
                if note:
                    values[f"metric_{index}.note"] = note
        if slide.table is not None:
            values[f"{prefix}.table"] = slide.table
    return values


class CreatePptxFromDeckTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="create_pptx_from_deck",
            description=(
                "从 Agent 友好的 deck.yaml/json 业务结构生成 PPTX。"
                "Agent 只描述业务页面意图，工具负责转换为 create_pptx 可渲染结构。"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        deck: Optional[Any] = None,
        output_file: Optional[str] = None,
        quality: str = "standard",
        run_validation: bool = True,
        template_path: Optional[str] = None,
        template_manifest: Optional[Dict[str, Any]] = None,
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
                    "data": {"error": f"deck 不是有效 JSON: {exc}"},
                    "summary": "创建PPT失败：deck 参数格式错误",
                }

        if not isinstance(deck, dict):
            return {
                "success": False,
                "data": {"error": "deck 必须是对象"},
                "summary": "创建PPT失败：deck 参数无效",
            }

        spec = DeckSpec.model_validate(deck)
        issues = validate_visual_rules(spec)
        if issues:
            return {
                "success": False,
                "data": {"issues": issues},
                "summary": f"Deck 视觉规则校验失败：{issues[0]['type']}",
            }

        if template_path and template_manifest:
            manifest = TemplateManifest.model_validate(template_manifest)
            semantic_values = build_semantic_values_from_deck(spec)
            unknown = manifest.unknown_semantic_slots(semantic_values)
            replacements = manifest.to_physical_replacements(semantic_values)
            result = await CreatePptxFromTemplateTool().execute(
                template_path=template_path,
                replacements=replacements,
                output_file=output_file,
                quality=quality,
                run_validation=run_validation,
            )
            if isinstance(result.get("data"), dict):
                result["data"]["semantic_unknown_slots"] = unknown
                result["data"]["semantic_replacement_count"] = len(replacements)
            return result

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
            "description": "从 deck.yaml/json 业务结构生成可编辑 PPTX。",
            "parameters": {
                "type": "object",
                "properties": {
                    "deck": {"type": "object", "description": "符合 suyuan.deck.v1 的业务 deck spec"},
                    "output_file": {"type": "string", "description": "输出 PPTX 路径，可选"},
                    "quality": {"type": "string", "enum": ["draft", "standard", "strict"], "default": "standard"},
                    "run_validation": {"type": "boolean", "default": True},
                    "template_path": {"type": "string", "description": "可选 PPTX 模板路径"},
                    "template_manifest": {"type": "object", "description": "可选语义槽位到物理 slot_id 的映射"},
                },
                "required": ["deck"],
            },
        }
