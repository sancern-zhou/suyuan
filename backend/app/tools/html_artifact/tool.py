"""Tool for creating standalone HTML presentation artifacts."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.tools.artifact_utils import attach_document_artifact
from app.services.html_artifact_service import html_artifact_service
from app.tools.base.tool_interface import LLMTool, ToolCategory


class CreateHtmlArtifactTool(LLMTool):
    """Create a previewable/shareable HTML presentation artifact."""

    def __init__(self):
        super().__init__(
            name="create_html_artifact",
            description=(
                "创建展示型 HTML 产物，用于演讲材料、数据大屏、交互说明页、可视化叙事等。"
                "本工具会保存 index.html、复制资源、触发右侧面板 HTML 预览，并提供下载 HTML 和分享链接能力。"
                "不要用于正式报告；正式报告必须使用 create_report_package 生成 report.qmd 同源报告包。"
                "HTML 展示产物不承诺 Word/PPT/QMD 同源导出。"
                "生成时应优先设计完整可阅读的展示效果：清晰层级、响应式布局、适合投屏/分享的视觉密度。"
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
                        "description": "完整 HTML 内容，建议包含完整 <!doctype html><html> 结构。",
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
        design_intent: str | None = None,
        assets: Optional[List[Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        artifact_metadata = dict(metadata or {})
        if display_mode:
            artifact_metadata["display_mode"] = display_mode
        if design_intent:
            artifact_metadata["design_intent"] = design_intent

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
