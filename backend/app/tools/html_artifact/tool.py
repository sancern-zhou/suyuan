"""Tool for creating standalone HTML presentation artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.tools.artifact_utils import (
    attach_document_resources,
    build_artifact_resume_context,
    preview_output_path,
)
from app.services.html_artifact_service import html_artifact_service
from app.tools.base.tool_interface import LLMTool, ToolCategory


DECK_ASSET_ROOT = Path(__file__).resolve().parent / "deck_assets"
GUIZANG_ASSETS = DECK_ASSET_ROOT / "guizang_assets"
GUIZANG_REFERENCES = DECK_ASSET_ROOT / "guizang_references"
GUIZANG_SCRIPTS = DECK_ASSET_ROOT / "guizang_scripts"


def guizang_deck_asset_paths() -> Dict[str, str]:
    """Return stable local paths Agent can read before composing HTML decks."""
    return {
        "template_magazine": str(GUIZANG_ASSETS / "template.html"),
        "template_swiss": str(GUIZANG_ASSETS / "template-swiss.html"),
        "layouts_magazine": str(GUIZANG_REFERENCES / "layouts.md"),
        "layouts_swiss": str(GUIZANG_REFERENCES / "layouts-swiss.md"),
        "themes_magazine": str(GUIZANG_REFERENCES / "themes.md"),
        "themes_swiss": str(GUIZANG_REFERENCES / "themes-swiss.md"),
        "index": str(GUIZANG_REFERENCES / "index.md"),
        "checklist": str(GUIZANG_REFERENCES / "checklist.md"),
        "swiss_layout_lock": str(GUIZANG_REFERENCES / "swiss-layout-lock.md"),
        "image_prompts": str(GUIZANG_REFERENCES / "image-prompts.md"),
        "screenshot_framing": str(GUIZANG_REFERENCES / "screenshot-framing.md"),
        "validate_swiss": str(GUIZANG_SCRIPTS / "validate-swiss-deck.mjs"),
    }


class CreateHtmlArtifactTool(LLMTool):
    """Create a previewable/shareable HTML presentation artifact."""

    def __init__(self):
        guizang_paths = guizang_deck_asset_paths()
        super().__init__(
            name="create_html_artifact",
            description=(
                "创建 HTML 展示；正式报告用 create_report_package。"
                f"guizang 先用 read_file 读取 {guizang_paths['index']}，"
                "再按 style 读模板/layouts/themes/checklist.md。"
            ),
            category=ToolCategory.REPORTING,
            version="1.0.0",
        )
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "artifact_id": {
                        "type": "string",
                        "description": "展示页ID，会安全转义。",
                    },
                    "html_content": {
                        "type": "string",
                        "description": (
                            "完整 HTML。guizang 调用本工具前先读取模板、layouts、themes、checklist；"
                            "不要凭空编写新的 deck 框架。"
                        ),
                    },
                    "title": {"type": "string", "description": "展示页标题，可选。"},
                    "display_mode": {
                        "type": "string",
                        "enum": ["presentation", "dashboard", "story", "single_page", "custom"],
                        "description": "展示类型。",
                    },
                    "presentation_kind": {
                        "type": "string",
                        "enum": ["deck", "page", "cover"],
                        "description": "presentation 形态。",
                    },
                    "layout_system": {
                        "type": "string",
                        "enum": ["guizang", "custom"],
                        "description": (
                            "guizang 先读 guizang_references/index.md 和 checklist.md。"
                            f"template_magazine={guizang_paths['template_magazine']}; "
                            f"template_swiss={guizang_paths['template_swiss']}"
                        ),
                    },
                    "presentation_style": {
                        "type": "string",
                        "enum": ["magazine", "swiss"],
                        "description": "guizang 风格：magazine 或 swiss。",
                    },
                    "validation": {
                        "type": "string",
                        "enum": ["none", "swiss"],
                        "description": "HTML deck 自检方式。",
                    },
                    "design_intent": {
                        "type": "string",
                        "description": "设计意图，写入元数据。",
                    },
                    "assets": {
                        "type": "array",
                        "description": "复制到 assets/ 的资源：路径或 {path,name}。",
                        "items": {
                            "oneOf": [
                                {"type": "string"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "path": {"type": "string"},
                                        "name": {"type": "string"},
                                    },
                                    "required": ["path"],
                                },
                            ]
                        },
                    },
                    "metadata": {
                        "type": "object",
                        "description": "额外元数据，写入 meta.json。",
                    },
                },
                "required": ["artifact_id", "html_content"],
            },
        }

    async def execute(
        self,
        artifact_id: str,
        html_content: str,
        title: str | None = None,
        display_mode: str | None = None,
        presentation_kind: str | None = None,
        layout_system: str | None = None,
        presentation_style: str | None = None,
        validation: str | None = None,
        design_intent: str | None = None,
        assets: Optional[List[Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        artifact_metadata = dict(metadata or {})
        if display_mode:
            artifact_metadata["display_mode"] = display_mode
        if presentation_kind:
            artifact_metadata["presentation_kind"] = presentation_kind
        if layout_system:
            artifact_metadata["layout_system"] = layout_system
        if presentation_style:
            artifact_metadata["presentation_style"] = presentation_style
        if validation:
            artifact_metadata["validation"] = validation
        if design_intent:
            artifact_metadata["design_intent"] = design_intent
        if display_mode == "presentation" and layout_system == "guizang":
            artifact_metadata["deck_mode"] = "visual_first"
            artifact_metadata["deck_asset_paths"] = guizang_deck_asset_paths()
            artifact_metadata["deck_generation_rules"] = {
                "route": "visual_priority_html_deck",
                "data_dense_alternative": "create_pptx_with_ppt_master",
                "style": presentation_style or "magazine",
                "required_preread": _guizang_required_preread(presentation_style),
            }

        data = html_artifact_service.create_artifact(
            artifact_id,
            html_content,
            title=title,
            assets=assets,
            metadata=artifact_metadata,
        )
        data.pop("download_url", None)
        data.pop("share_endpoint", None)
        attach_document_resources(
            data,
            data["file_path"],
            kind="html_artifact",
            format="html",
            title=title or data.get("artifact_id"),
            preview_path=preview_output_path(data.get("html_preview")),
            generator=self.name,
            metadata={"artifact_id": data.get("artifact_id")},
        )
        resume_context = build_artifact_resume_context(
            data,
            data["file_path"],
            extra_resume={"artifact_id": data.get("artifact_id")},
        )
        return {
            "success": True,
            "data": data,
            "resources": data.get("resources", []),
            **resume_context,
            "metadata": {"generator": "create_html_artifact", "schema_version": "html_artifact.v1"},
            "summary": (
                f"HTML展示页已生成：{data['artifact_id']}。"
                "右侧预览已生成，预览和下载由右侧文档面板处理。"
            ),
        }

    def get_function_schema(self) -> Dict[str, Any]:
        return self.function_schema


def _guizang_required_preread(style: str | None) -> List[str]:
    paths = guizang_deck_asset_paths()
    if style == "swiss":
        return [
            paths["template_swiss"],
            paths["layouts_swiss"],
            paths["themes_swiss"],
            paths["checklist"],
            paths["swiss_layout_lock"],
        ]
    return [
        paths["template_magazine"],
        paths["layouts_magazine"],
        paths["themes_magazine"],
        paths["checklist"],
    ]
