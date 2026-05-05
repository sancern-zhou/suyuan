"""
Create editable PPTX files through a PptxGenJS renderer.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?$")
ALLOWED_SLIDE_TYPES = {
    "title",
    "section",
    "bullets",
    "text",
    "two_column",
    "table",
    "image",
    "image_text",
    "chart",
    "quote",
    "toc",
    "summary",
    "comparison",
    "timeline",
    "process",
    "metrics",
}
DEFAULT_THEME = {
    "primary": "2563EB",
    "secondary": "0F766E",
    "accent": "DC2626",
    "text": "1F2937",
    "muted": "6B7280",
    "bg": "FFFFFF",
    "surface": "F8FAFC",
    "line": "D1D5DB",
    "headFontFace": "Microsoft YaHei",
    "bodyFontFace": "Microsoft YaHei",
}


def get_pdf_converter():
    try:
        from app.services.pdf_converter import pdf_converter
        return pdf_converter
    except ImportError:
        logger.warning("pdf_converter_not_available")
        return None


class CreatePptxTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="create_pptx",
            description="使用PptxGenJS从结构化JSON一步生成可编辑PPTX演示文稿，并返回下载链接和PDF预览。",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False,
        )
        self.working_dir = Path.cwd().parent
        self.renderer_path = Path(__file__).resolve().parent / "pptxgen_renderer.js"
        self.default_output_dir = self.working_dir / "backend" / "backend_data_registry" / "presentations"

    async def execute(
        self,
        title: str,
        slides: List[Dict[str, Any]],
        output_file: Optional[str] = None,
        theme: Optional[Dict[str, Any]] = None,
        layout: str = "LAYOUT_WIDE",
        author: str = "suyuan-agent",
        enable_preview: bool = True,
        run_validation: bool = False,
        quality: str = "draft",
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            if not isinstance(slides, list):
                return {
                    "success": False,
                    "data": {"error": "slides 必须是数组"},
                    "summary": "创建PPT失败：slides 参数无效",
                }

            normalized_theme = self._normalize_theme(theme or {})
            normalized_slides = self._normalize_slides(slides, normalized_theme)
            output_path = self._resolve_output_file(output_file, title)
            spec = {
                "title": title,
                "slides": normalized_slides,
                "theme": normalized_theme,
                "layout": layout,
                "author": author,
                "lang": kwargs.get("lang", "zh-CN"),
                "footer": kwargs.get("footer", True),
            }

            with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as tmp:
                json.dump(spec, tmp, ensure_ascii=False)
                spec_path = Path(tmp.name)

            try:
                completed = subprocess.run(
                    ["node", str(self.renderer_path), str(spec_path), str(output_path)],
                    cwd=str(self.working_dir),
                    capture_output=True,
                    text=True,
                    timeout=int(kwargs.get("timeout", 90)),
                )
            finally:
                spec_path.unlink(missing_ok=True)

            if completed.returncode != 0:
                logger.error(
                    "create_pptx_renderer_failed",
                    stderr=completed.stderr,
                    stdout=completed.stdout,
                )
                return {
                    "success": False,
                    "data": {
                        "error": completed.stderr.strip() or completed.stdout.strip() or "PptxGenJS 渲染失败",
                    },
                    "summary": "创建PPT失败：PptxGenJS 渲染失败",
                }

            if not output_path.exists() or output_path.stat().st_size == 0:
                return {
                    "success": False,
                    "data": {"error": "PPTX文件未生成或为空"},
                    "summary": "创建PPT失败：输出文件为空",
                }

            from config.settings import settings

            api_base = settings.backend_host.rstrip("/")
            encoded_path = quote(str(output_path))
            result_data: Dict[str, Any] = {
                "file_path": str(output_path),
                "output_file": str(output_path),
                "file_name": output_path.name,
                "slide_count": len(slides),
                "theme": normalized_theme,
                "size": output_path.stat().st_size,
                "doc_url": f"{api_base}/api/utility/file/{encoded_path}",
                "doc_download_filename": output_path.name,
            }

            if enable_preview:
                try:
                    converter = get_pdf_converter()
                    if converter:
                        result_data["pdf_preview"] = await converter.convert_to_pdf(str(output_path))
                except Exception as preview_error:
                    logger.warning("create_pptx_preview_failed", error=str(preview_error))

            quality_mode = str(quality or "draft").lower()
            if quality_mode not in {"draft", "standard", "strict"}:
                quality_mode = "draft"

            if run_validation or quality_mode in {"standard", "strict"}:
                try:
                    from app.tools.office.validate_pptx_tool import ValidatePptxTool

                    validation = await ValidatePptxTool().execute(
                        str(output_path),
                        expected_fonts=[
                            normalized_theme.get("headFontFace", ""),
                            normalized_theme.get("bodyFontFace", ""),
                        ],
                        render_overflow_check=quality_mode == "strict" or run_validation,
                    )
                    result_data["validation"] = validation.get("data")
                except Exception as validation_error:
                    logger.warning("create_pptx_validation_failed", error=str(validation_error))
                    result_data["validation_error"] = str(validation_error)

            return {
                "success": True,
                "data": result_data,
                "summary": f"已生成PPT：{output_path.name}，共 {len(slides)} 页",
            }
        except FileNotFoundError as e:
            return {
                "success": False,
                "data": {"error": f"缺少运行时依赖: {e}"},
                "summary": "创建PPT失败：缺少 Node 或 PptxGenJS 运行环境",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "data": {"error": "PptxGenJS 渲染超时"},
                "summary": "创建PPT失败：渲染超时",
            }
        except Exception as e:
            logger.error("create_pptx_failed", error=str(e), exc_info=True)
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"创建PPT失败：{str(e)[:80]}",
            }

    def _resolve_output_file(self, output_file: Optional[str], title: str) -> Path:
        if output_file:
            path = Path(output_file)
            if not path.is_absolute():
                path = self.working_dir / path
        else:
            safe_title = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in title).strip("_")
            if not safe_title:
                safe_title = "presentation"
            path = self.default_output_dir / f"{safe_title}_{uuid.uuid4().hex[:8]}.pptx"

        if path.suffix.lower() != ".pptx":
            path = path.with_suffix(".pptx")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    def _normalize_theme(self, theme: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize MiniMax-style theme contract and legacy aliases."""
        aliases = {
            "background": "bg",
            "foreground": "text",
            "accentColor": "accent",
        }
        normalized = dict(DEFAULT_THEME)
        for key, value in (theme or {}).items():
            target_key = aliases.get(key, key)
            if target_key in {
                "primary",
                "secondary",
                "accent",
                "text",
                "muted",
                "bg",
                "surface",
                "line",
            }:
                normalized[target_key] = self._normalize_color(value, normalized[target_key])
            elif target_key in {"headFontFace", "bodyFontFace"} and isinstance(value, str) and value.strip():
                normalized[target_key] = value.strip()

        # Backward-compatible aliases consumed by older prompts.
        normalized["background"] = normalized["bg"]
        normalized["foreground"] = normalized["text"]
        return normalized

    def _normalize_color(self, value: Any, fallback: str) -> str:
        if not isinstance(value, str):
            return fallback
        match = HEX_COLOR_RE.match(value.strip())
        if not match:
            return fallback
        return match.group(1).upper()

    def _normalize_slides(
        self,
        slides: List[Dict[str, Any]],
        theme: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        normalized_slides: List[Dict[str, Any]] = []
        for index, slide in enumerate(slides, start=1):
            if not isinstance(slide, dict):
                normalized_slides.append(
                    {
                        "type": "text",
                        "title": f"第 {index} 页",
                        "text": str(slide),
                    }
                )
                continue

            normalized = dict(slide)
            slide_type = str(normalized.get("type", "bullets")).lower()
            if slide_type not in ALLOWED_SLIDE_TYPES:
                slide_type = "bullets" if normalized.get("bullets") else "text"
            normalized["type"] = slide_type

            if "background" in normalized:
                normalized["background"] = self._normalize_color(normalized["background"], theme["bg"])

            self._normalize_text_items(normalized)
            normalized_slides.append(normalized)
        return normalized_slides

    def _normalize_text_items(self, slide: Dict[str, Any]) -> None:
        for key in ("bullets", "left", "right"):
            value = slide.get(key)
            if isinstance(value, list):
                slide[key] = [self._normalize_bullet_item(item) for item in value]

    def _normalize_bullet_item(self, item: Any) -> Any:
        if isinstance(item, str):
            text = item.strip()
            while text[:1] in {"•", "-", "*", "·"}:
                text = text[1:].strip()
            return text
        if isinstance(item, dict):
            normalized = dict(item)
            if "text" in normalized and isinstance(normalized["text"], str):
                normalized["text"] = self._normalize_bullet_item(normalized["text"])
            return normalized
        return item

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": "create_pptx",
                "description": (
                    "用PptxGenJS生成可编辑PPTX。slides支持type: title/section/bullets/text/"
                "two_column/table/image/image_text/chart/quote/toc/summary/comparison/timeline/"
                "process/metrics。返回file_path、doc_url和可选pdf_preview。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "演示文稿标题"},
                    "slides": {
                        "type": "array",
                        "description": "幻灯片数组，每页是结构化对象",
                        "items": {"type": "object"},
                    },
                    "output_file": {"type": "string", "description": "输出PPTX路径，可选"},
                    "theme": {
                        "type": "object",
                        "description": (
                            "主题配置，推荐字段: primary/secondary/accent/text/muted/bg/surface/line/"
                            "headFontFace/bodyFontFace。颜色只使用6位hex，可带或不带#。"
                        ),
                    },
                    "layout": {"type": "string", "description": "PPT布局，默认LAYOUT_WIDE"},
                    "author": {"type": "string", "description": "作者", "default": "suyuan-agent"},
                    "enable_preview": {"type": "boolean", "description": "是否生成PDF预览", "default": True},
                    "run_validation": {
                        "type": "boolean",
                        "description": "是否生成后调用validate_pptx执行QA检查",
                        "default": False,
                    },
                    "quality": {
                        "type": "string",
                        "description": "生成质量模式：draft只生成；standard生成后渲染验证；strict额外执行渲染级溢出检测。",
                        "default": "draft",
                        "enum": ["draft", "standard", "strict"],
                    },
                },
                "required": ["title", "slides"],
            },
        }

    def is_available(self) -> bool:
        return True


tool = CreatePptxTool()
