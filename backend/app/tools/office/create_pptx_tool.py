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

import structlog

from app.tools.artifact_utils import attach_document_artifact
from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?$")
ALLOWED_SLIDE_TYPES = {
    "title",
    "section",
    "agenda",
    "bullets",
    "text",
    "key_message",
    "card_grid",
    "two_column",
    "table",
    "image",
    "image_text",
    "chart",
    "data_story",
    "quote",
    "toc",
    "summary",
    "comparison",
    "timeline",
    "process",
    "process_timeline",
    "metrics",
}
TYPE_ALIASES = {
    "cover": "title",
    "content": "key_message",
    "data": "data_story",
    "data_visualization": "data_story",
    "agenda": "toc",
    "process_timeline": "process",
}
DESIGN_DEFAULTS = {
    "audience": "professional",
    "tone": "clean, structured, data-aware",
    "style": "Soft & Balanced",
    "content_density": "standard",
    "rules": [
        "one core message per slide",
        "prefer cards, charts, callouts, and timelines over dense paragraphs",
        "split or restructure slides with too much text",
    ],
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
    "spacingPageMargin": 0.6,
    "spacingBlockGap": 0.35,
    "radiusCard": 0.08,
    "fontTitle": 28,
    "fontBody": 15,
    "fontCaption": 10,
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
            description=(
                "⚠️ 仅用于从头创建PPT（不基于模板）。"
                "如果要基于现有模板生成PPT，请使用 create_pptx_from_template 工具（推荐方式）。\n\n"
                "功能：使用 PptxGenJS 从结构化 JSON 一步生成可编辑 PPTX 演示文稿。\n\n"
                "适用场景：\n"
                "- ✅ 没有模板文件时使用\n"
                "- ✅ 需要完全自定义设计时使用\n"
                "- ❌ 不推荐：有模板时请用 create_pptx_from_template\n\n"
                "用法：传入 title 和 slides 数组，支持多种幻灯片类型（title/bullets/image/chart等）。\n\n"
                "详细说明：使用前请阅读 app/tools/office/PPT操作指南.md"
            ),
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
            design_brief = self._normalize_design_brief(kwargs.get("design_brief"), title, slides)
            normalized_slides, slide_plan, density_report = self._normalize_slides(
                slides,
                normalized_theme,
                design_brief,
                auto_design=kwargs.get("auto_design", True),
            )
            output_path = self._resolve_output_file(output_file, title)
            spec = {
                "title": title,
                "slides": normalized_slides,
                "theme": normalized_theme,
                "designBrief": design_brief,
                "slidePlan": slide_plan,
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

            result_data: Dict[str, Any] = {
                "file_path": str(output_path),
                "output_file": str(output_path),
                "file_name": output_path.name,
                "slide_count": len(slides),
                "theme": normalized_theme,
                "design_brief": design_brief,
                "slide_plan": slide_plan,
                "density_report": density_report,
                "size": output_path.stat().st_size,
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
                    validation_report = validation.get("data")
                    result_data["validation"] = validation_report
                    result_data["quality_gate"] = self._quality_gate(validation_report)
                except Exception as validation_error:
                    logger.warning("create_pptx_validation_failed", error=str(validation_error))
                    result_data["validation_error"] = str(validation_error)

            attach_document_artifact(
                result_data,
                output_path,
                kind="office",
                format="pptx",
                title=title,
                preview_key="pdf_preview",
                generator=self.name,
            )

            quality_gate = result_data.get("quality_gate")
            summary_suffix = ""
            if isinstance(quality_gate, dict) and quality_gate.get("status") == "rewrite_required":
                summary_suffix = f"，其中 {len(quality_gate.get('rewrite_pages', []))} 页建议重写"
            return {
                "success": True,
                "data": result_data,
                "summary": f"已生成PPT：{output_path.name}，共 {len(slides)} 页{summary_suffix}",
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
            elif target_key in {
                "spacingPageMargin",
                "spacingBlockGap",
                "radiusCard",
                "fontTitle",
                "fontBody",
                "fontCaption",
            }:
                normalized[target_key] = self._normalize_number(value, normalized[target_key])

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

    def _normalize_number(self, value: Any, fallback: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return fallback
        return parsed if 0 <= parsed <= 120 else fallback

    def _normalize_design_brief(
        self,
        design_brief: Any,
        title: str,
        slides: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        brief = dict(DESIGN_DEFAULTS)
        if isinstance(design_brief, dict):
            for key in ("audience", "tone", "style", "content_density"):
                value = design_brief.get(key)
                if isinstance(value, str) and value.strip():
                    brief[key] = value.strip()
            if isinstance(design_brief.get("rules"), list):
                brief["rules"] = [str(item).strip() for item in design_brief["rules"] if str(item).strip()]

        if not design_brief:
            joined = f"{title} " + " ".join(
                str(slide.get("title", "")) for slide in slides if isinstance(slide, dict)
            )
            if any(keyword in joined for keyword in ("数据", "分析", "指标", "污染", "臭氧", "PM", "VOCs", "报告")):
                brief.update(
                    {
                        "audience": "technical or management report readers",
                        "tone": "professional, evidence-led, concise",
                        "style": "Sharp & Compact",
                        "content_density": "dense",
                    }
                )
        return brief

    def _normalize_slides(
        self,
        slides: List[Dict[str, Any]],
        theme: Dict[str, Any],
        design_brief: Dict[str, Any],
        auto_design: bool = True,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        normalized_slides: List[Dict[str, Any]] = []
        slide_plan: List[Dict[str, Any]] = []
        density_report: Dict[str, Any] = {"rewritten_slides": [], "warnings": []}
        for index, slide in enumerate(slides, start=1):
            if not isinstance(slide, dict):
                normalized = self._auto_design_slide(
                    {"type": "text", "title": f"第 {index} 页", "text": str(slide)},
                    index,
                    design_brief,
                    density_report,
                )
                normalized_slides.append(normalized)
                slide_plan.append(self._slide_plan_item(index, normalized))
                continue

            normalized = dict(slide)
            slide_type = str(normalized.get("type", "bullets")).lower()
            slide_type = TYPE_ALIASES.get(slide_type, slide_type)
            if slide_type not in ALLOWED_SLIDE_TYPES:
                slide_type = "bullets" if normalized.get("bullets") else "text"
            normalized["type"] = slide_type

            if "background" in normalized:
                normalized["background"] = self._normalize_color(normalized["background"], theme["bg"])

            self._normalize_text_items(normalized)
            if auto_design:
                normalized = self._auto_design_slide(normalized, index, design_brief, density_report)
            normalized_slides.append(normalized)
            slide_plan.append(self._slide_plan_item(index, normalized))
        return normalized_slides, slide_plan, density_report

    def _auto_design_slide(
        self,
        slide: Dict[str, Any],
        index: int,
        design_brief: Dict[str, Any],
        density_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized = dict(slide)
        slide_type = normalized.get("type", "bullets")
        text_payload = self._slide_text_payload(normalized)
        char_count = len(text_payload)
        bullet_count = len(normalized.get("bullets", [])) if isinstance(normalized.get("bullets"), list) else 0

        if slide_type == "text" and char_count > 260:
            normalized["type"] = "key_message"
            normalized["message"] = self._first_sentence(normalized.get("text", ""), normalized.get("title", ""))
            normalized["items"] = self._chunk_text_items(normalized.get("text", ""))
            density_report["rewritten_slides"].append(
                {"slide": index, "from": "text", "to": "key_message", "reason": "正文过长，改为结论+卡片结构"}
            )
        elif slide_type == "bullets" and bullet_count > 4:
            normalized["type"] = "card_grid"
            normalized["items"] = self._bullet_items_as_cards(normalized.get("bullets", []))
            density_report["rewritten_slides"].append(
                {"slide": index, "from": "bullets", "to": "card_grid", "reason": "列表项过多，改为卡片网格"}
            )
        elif slide_type in {"bullets", "text"} and char_count > 160:
            normalized["type"] = "key_message"
            normalized["message"] = self._first_sentence(text_payload, normalized.get("title", ""))
            normalized["items"] = self._bullet_items_as_cards(normalized.get("bullets", [])) or self._chunk_text_items(text_payload)
            density_report["rewritten_slides"].append(
                {"slide": index, "from": slide_type, "to": "key_message", "reason": "文字密度偏高，改为主结论页"}
            )

        if char_count > 520:
            density_report["warnings"].append(
                {"slide": index, "warning": "单页文字仍然偏多，建议上游拆分为多页", "chars": char_count}
            )

        normalized.setdefault("designRole", self._design_role(normalized, design_brief))
        return normalized

    def _slide_plan_item(self, index: int, slide: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "index": index,
            "type": slide.get("type", "bullets"),
            "title": slide.get("title", ""),
            "message": slide.get("message") or slide.get("subtitle") or self._first_sentence(self._slide_text_payload(slide), ""),
            "visual_strategy": self._visual_strategy(slide),
        }

    def _design_role(self, slide: Dict[str, Any], design_brief: Dict[str, Any]) -> str:
        slide_type = slide.get("type", "")
        if slide_type in {"chart", "data_story", "metrics", "table"}:
            return "data evidence"
        if slide_type in {"timeline", "process", "process_timeline"}:
            return "sequence explanation"
        if slide_type in {"key_message", "card_grid", "summary"}:
            return "scannable insight"
        return str(design_brief.get("tone", "content")).split(",")[0].strip() or "content"

    def _visual_strategy(self, slide: Dict[str, Any]) -> str:
        slide_type = slide.get("type", "")
        if slide_type in {"key_message", "card_grid"}:
            return "主结论突出，正文拆成卡片，避免整页纯文本"
        if slide_type in {"chart", "data_story"}:
            return "图表占主区，右侧或底部保留关键发现"
        if slide_type in {"timeline", "process"}:
            return "编号步骤横向排布"
        if slide_type == "metrics":
            return "大数字指标卡"
        return "标题、正文和辅助图形保持清晰层级"

    def _slide_text_payload(self, slide: Dict[str, Any]) -> str:
        parts = []
        for key in ("title", "subtitle", "text", "message", "quote"):
            if slide.get(key):
                parts.append(str(slide[key]))
        for key in ("bullets", "items", "left", "right", "steps", "takeaways", "metrics"):
            value = slide.get(key)
            if isinstance(value, list):
                parts.extend(str(self._text_from_item(item)) for item in value)
            elif value:
                parts.append(str(value))
        return "\n".join(part for part in parts if part)

    def _text_from_item(self, item: Any) -> str:
        if isinstance(item, dict):
            return " ".join(str(item.get(key, "")) for key in ("title", "label", "text", "body", "description", "value"))
        return str(item)

    def _first_sentence(self, value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        if not text:
            return str(fallback or "")
        parts = re.split(r"(?<=[。！？!?；;])\s*", text)
        first = parts[0].strip() if parts else text
        return first[:80]

    def _chunk_text_items(self, value: Any, max_items: int = 4) -> List[Dict[str, str]]:
        text = str(value or "").strip()
        if not text:
            return []
        chunks = [chunk.strip() for chunk in re.split(r"[。；;\n]+", text) if chunk.strip()]
        return [
            {"title": f"要点 {idx}", "body": chunk[:120]}
            for idx, chunk in enumerate(chunks[:max_items], start=1)
        ]

    def _bullet_items_as_cards(self, bullets: Any, max_items: int = 6) -> List[Dict[str, str]]:
        if not isinstance(bullets, list):
            return []
        cards = []
        for idx, item in enumerate(bullets[:max_items], start=1):
            text = self._text_from_item(item).strip()
            if not text:
                continue
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("label") or f"要点 {idx}")
                body = str(item.get("body") or item.get("description") or item.get("text") or "")
            else:
                title, body = self._split_card_text(text, idx)
            cards.append({"title": title[:32], "body": body[:110]})
        return cards

    def _split_card_text(self, text: str, idx: int) -> tuple[str, str]:
        for sep in ("：", ":", "，", ","):
            if sep in text:
                head, tail = text.split(sep, 1)
                return head.strip()[:32] or f"要点 {idx}", tail.strip()
        return f"要点 {idx}", text

    def _quality_gate(self, validation_report: Any) -> Dict[str, Any]:
        if not isinstance(validation_report, dict):
            return {
                "status": "unknown",
                "rewrite_required": False,
                "rewrite_pages": [],
                "reasons": ["验证报告缺失，无法判断设计质量"],
                "recommendations": [],
            }

        blocking_types = {
            "high_text_density",
            "text_only_slide",
            "tiny_text",
            "repeated_layout_pattern",
            "rendered_visual_overcrowding",
            "rendered_low_margin",
            "rendered_nearly_blank",
            "rendered_content_overflow",
            "shape_out_of_bounds",
            "rendered_blank_page",
        }
        warning_types = {
            "moderate_text_density",
            "weak_title_hierarchy",
            "low_typographic_contrast",
            "rendered_dense_composition",
            "rendered_sparse_or_blank",
            "rendered_visual_qa_unavailable",
        }
        rewrite_pages: Dict[int, Dict[str, Any]] = {}
        reasons: List[str] = []
        warnings: List[Dict[str, Any]] = []

        for issue in validation_report.get("issues", []):
            if not isinstance(issue, dict):
                continue
            issue_type = str(issue.get("type", ""))
            slide = issue.get("slide")
            if issue_type in blocking_types:
                reasons.append(self._quality_issue_reason(issue))
                if isinstance(slide, int):
                    page = rewrite_pages.setdefault(slide, {"slide": slide, "issues": [], "action": ""})
                    page["issues"].append(issue)
            elif issue_type in warning_types:
                warnings.append(issue)

        design_quality = validation_report.get("design_quality", {})
        visual_quality = validation_report.get("visual_quality", {})
        design_score = design_quality.get("score") if isinstance(design_quality, dict) else None
        visual_score = visual_quality.get("score") if isinstance(visual_quality, dict) else None
        if isinstance(design_score, (int, float)) and design_score < 78:
            reasons.append(f"结构设计评分 {design_score} 低于 78，需要复核页面信息分层。")
            for slide in self._low_score_slides(design_quality):
                rewrite_pages.setdefault(slide, {"slide": slide, "issues": [], "action": ""})
        if isinstance(visual_score, (int, float)) and visual_score < 78:
            reasons.append(f"渲染视觉评分 {visual_score} 低于 78，需要复核实际页面密度和边距。")
            for slide in self._low_score_slides(visual_quality):
                rewrite_pages.setdefault(slide, {"slide": slide, "issues": [], "action": ""})

        for page in rewrite_pages.values():
            page["action"] = self._rewrite_action(page["issues"])

        recommendations = []
        for key in ("design_quality", "visual_quality"):
            section = validation_report.get(key, {})
            if isinstance(section, dict):
                recommendations.extend(section.get("recommendations", []))

        status = "pass"
        if rewrite_pages or reasons:
            status = "rewrite_required"
        elif warnings:
            status = "warning"

        return {
            "status": status,
            "rewrite_required": status == "rewrite_required",
            "rewrite_pages": sorted(rewrite_pages.values(), key=lambda item: item["slide"]),
            "reasons": list(dict.fromkeys(reasons)),
            "warnings": warnings,
            "recommendations": list(dict.fromkeys(recommendations)),
        }

    def _low_score_slides(self, quality_section: Any, threshold: float = 78) -> List[int]:
        if not isinstance(quality_section, dict):
            return []
        slides = []
        for item in quality_section.get("slides", []):
            if isinstance(item, dict) and isinstance(item.get("slide"), int):
                score = item.get("score")
                if isinstance(score, (int, float)) and score < threshold:
                    slides.append(item["slide"])
        return slides

    def _quality_issue_reason(self, issue: Dict[str, Any]) -> str:
        issue_type = issue.get("type", "")
        slide = issue.get("slide")
        prefix = f"第 {slide} 页" if isinstance(slide, int) else "全局"
        mapping = {
            "high_text_density": "文字密度过高",
            "text_only_slide": "仍是纯文字页",
            "tiny_text": "存在过小文字",
            "repeated_layout_pattern": "连续版式重复",
            "rendered_visual_overcrowding": "渲染后视觉过密",
            "rendered_low_margin": "渲染后内容贴边",
            "rendered_nearly_blank": "渲染后接近空白",
            "rendered_content_overflow": "渲染后内容溢出",
            "shape_out_of_bounds": "存在越界元素",
            "rendered_blank_page": "渲染为空白页",
        }
        return f"{prefix}：{mapping.get(issue_type, issue_type)}。"

    def _rewrite_action(self, issues: List[Dict[str, Any]]) -> str:
        issue_types = {str(issue.get("type", "")) for issue in issues if isinstance(issue, dict)}
        if issue_types & {"high_text_density", "text_only_slide", "rendered_visual_overcrowding"}:
            return "拆分内容，改为主结论+图表/卡片/流程，减少同页文字。"
        if issue_types & {"rendered_low_margin", "rendered_content_overflow", "shape_out_of_bounds"}:
            return "缩小主内容区域，增加页边距，重新计算元素位置。"
        if issue_types & {"rendered_nearly_blank", "rendered_blank_page"}:
            return "检查渲染数据源、图片和图表是否成功输出。"
        if issue_types & {"tiny_text"}:
            return "提高最小字号，删减低优先级注释。"
        return "复核页面层级和视觉策略后重写该页。"

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
                "process/metrics。返回file_path和可选pdf_preview。"
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
                            "headFontFace/bodyFontFace，以及spacingPageMargin/spacingBlockGap/radiusCard/"
                            "fontTitle/fontBody/fontCaption。颜色只使用6位hex，可带或不带#。"
                        ),
                    },
                    "design_brief": {
                        "type": "object",
                        "description": (
                            "可选设计简报，字段: audience/tone/style/content_density/rules。"
                            "未提供时工具会按标题和内容自动推断。"
                        ),
                    },
                    "auto_design": {
                        "type": "boolean",
                        "description": "是否自动将高密度text/bullets改写为key_message/card_grid等更适合展示的版式。",
                        "default": True,
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
