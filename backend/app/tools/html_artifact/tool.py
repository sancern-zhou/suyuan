"""Tool for creating standalone HTML presentation artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.tools.artifact_utils import attach_document_artifact
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
                "创建展示型 HTML 产物，用于演讲材料、视觉优先 PPT/deck、数据大屏、交互说明页、可视化叙事等。"
                "本工具会保存 index.html、复制资源、触发右侧面板 HTML 预览，并提供下载 HTML 和分享链接能力。"
                "不要用于正式报告；正式报告必须使用 create_report_package 生成 report.qmd 同源报告包。"
                "HTML 展示产物不承诺 Word/PPT/QMD 同源导出。"
                "生成时应优先设计完整可阅读的展示效果：清晰层级、响应式布局、适合投屏/分享的视觉密度。"
                "当 display_mode=presentation 且 layout_system=guizang 时，必须先用 read_file 读取对应内置资源，再生成 html_content："
                f"magazine 先读 {guizang_paths['template_magazine']}、{guizang_paths['layouts_magazine']}、"
                f"{guizang_paths['themes_magazine']}、{guizang_paths['checklist']}；"
                f"swiss 先读 {guizang_paths['template_swiss']}、{guizang_paths['layouts_swiss']}、"
                f"{guizang_paths['themes_swiss']}、{guizang_paths['checklist']}、{guizang_paths['swiss_layout_lock']}。"
                "不要从零自写一套 deck CSS；html_content 应基于所选模板和 layouts 骨架改写。"
                "数据密集型表格/图表汇报仍优先使用 create_pptx_from_deck。"
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
                        "description": "展示页ID，只允许字母、数字、下划线、连字符；其他字符会自动转义。",
                    },
                    "html_content": {
                        "type": "string",
                        "description": (
                            "完整 HTML 内容，建议包含完整 <!doctype html><html> 结构。"
                            "若 display_mode=presentation 且 layout_system=guizang，本字段必须基于对应 guizang 模板生成："
                            "magazine 基于 template_magazine + layouts_magazine；swiss 基于 template_swiss + layouts_swiss。"
                            "调用本工具前先读取 layout_system/presentation_style 指定的模板、layouts、themes 和 checklist，"
                            "不要凭空编写新的 deck 框架或 CSS。"
                        ),
                    },
                    "title": {"type": "string", "description": "展示页标题，可选。"},
                    "display_mode": {
                        "type": "string",
                        "enum": ["presentation", "dashboard", "story", "single_page", "custom"],
                        "description": (
                            "展示效果类型。presentation 适合演讲材料/类 PPT，dashboard 适合数据大屏，"
                            "story 适合可视化叙事，single_page 适合单页说明，custom 为自定义。"
                        ),
                    },
                    "presentation_kind": {
                        "type": "string",
                        "enum": ["deck", "page", "cover"],
                        "description": (
                            "presentation 模式下的产物形态。deck 表示横向翻页 HTML PPT，"
                            "page 表示普通展示页，cover 表示单张封面。"
                        ),
                    },
                    "layout_system": {
                        "type": "string",
                        "enum": ["guizang", "custom"],
                        "description": (
                            "presentation/deck 的版式系统。guizang 表示使用内置 guizang-ppt-skill 模板、"
                            "layouts、themes 和 checklist；custom 表示完全自定义 HTML。"
                            "选择 guizang 时，调用本工具前必须先读取对应资源路径："
                            f"template_magazine={guizang_paths['template_magazine']}；"
                            f"template_swiss={guizang_paths['template_swiss']}；"
                            f"layouts_magazine={guizang_paths['layouts_magazine']}；"
                            f"layouts_swiss={guizang_paths['layouts_swiss']}；"
                            f"themes_magazine={guizang_paths['themes_magazine']}；"
                            f"themes_swiss={guizang_paths['themes_swiss']}；"
                            f"checklist={guizang_paths['checklist']}。"
                        ),
                    },
                    "presentation_style": {
                        "type": "string",
                        "enum": ["magazine", "swiss"],
                        "description": (
                            "layout_system=guizang 时的视觉风格。magazine=电子杂志风；"
                            "swiss=瑞士国际主义风，需使用 layouts-swiss.md 中登记版式。"
                            "magazine 生成前先读 template_magazine、layouts_magazine、themes_magazine、checklist；"
                            "swiss 生成前先读 template_swiss、layouts_swiss、themes_swiss、checklist、swiss_layout_lock。"
                        ),
                    },
                    "validation": {
                        "type": "string",
                        "enum": ["none", "swiss"],
                        "description": (
                            "HTML deck 自检方式。swiss 表示产物应按内置 validate-swiss-deck.mjs 校验；"
                            "工具会把校验器路径写入 metadata，供 Agent 或后续流程执行。"
                        ),
                    },
                    "design_intent": {
                        "type": "string",
                        "description": (
                            "设计意图说明，例如目标受众、投屏/移动端/桌面优先、视觉风格、关键交互。"
                            "用于记录到元数据，帮助后续编辑保持一致。"
                        ),
                    },
                    "assets": {
                        "type": "array",
                        "description": "需要复制进展示产物 assets/ 的资源。元素可为路径字符串，或 {path, name}。",
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
                "data_dense_alternative": "create_pptx_from_deck",
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
        attach_document_artifact(
            data,
            data["file_path"],
            kind="html_artifact",
            format="html",
            title=title or data.get("artifact_id"),
            preview_key="html_preview",
            generator=self.name,
            metadata={"artifact_id": data.get("artifact_id")},
        )
        return {
            "success": True,
            "data": data,
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
