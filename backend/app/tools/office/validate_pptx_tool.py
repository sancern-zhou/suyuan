"""
Validate PPTX deliverables by rendering and running lightweight QA checks.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.office.slides_qa.create_montage import create_montage
from app.tools.office.slides_qa.detect_fonts import detect_pdf_fonts
from app.tools.office.slides_qa.detect_overflow import (
    inspect_pptx_geometry,
    inspect_rendered_overflow,
    inspect_rendered_pages,
)
from app.tools.office.slides_qa.render_pptx import render_deck

logger = structlog.get_logger()


class ValidatePptxTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="validate_pptx",
            description=(
                "渲染PPTX并执行基础交付检查：PDF/PNG预览、montage、空页/越界/字体检测。\n\n"
                "⚠️ 使用前请先阅读：app/tools/office/PPT操作指南.md"
            ),
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False,
        )
        self.working_dir = Path.cwd().parent
        self.default_qa_root = self.working_dir / "backend" / "backend_data_registry" / "presentations" / "qa"

    async def execute(
        self,
        path: str,
        output_dir: Optional[str] = None,
        expected_fonts: Optional[List[str]] = None,
        render_png: bool = True,
        create_overview: bool = True,
        render_overflow_check: bool = True,
        dpi: int = 144,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            pptx_path = self._resolve_path(path)
            if not pptx_path.exists():
                return {
                    "success": False,
                    "data": {"error": f"文件不存在: {pptx_path}"},
                    "summary": "PPT验证失败：文件不存在",
                }
            if pptx_path.suffix.lower() != ".pptx":
                return {
                    "success": False,
                    "data": {"error": f"只支持 .pptx 文件，当前格式: {pptx_path.suffix}"},
                    "summary": "PPT验证失败：格式不支持",
                }

            qa_dir = self._resolve_output_dir(output_dir, pptx_path)
            qa_dir.mkdir(parents=True, exist_ok=True)

            geometry = inspect_pptx_geometry(pptx_path)
            render_result: Dict[str, Any] = {}
            rendered_checks: Dict[str, Any] = {"issues": [], "blank_pages": []}
            overflow_checks: Dict[str, Any] = {"enabled": False, "issues": []}
            font_checks: Dict[str, Any] = {"fonts": [], "issues": [], "missing_expected_fonts": []}
            design_quality = self._inspect_design_quality(pptx_path)
            visual_quality: Dict[str, Any] = {"enabled": False, "issues": []}
            montage_path = None

            if render_png:
                try:
                    render_result = render_deck(pptx_path, qa_dir, dpi=dpi)
                    page_pngs = [Path(path) for path in render_result.get("page_pngs", [])]
                    rendered_checks = inspect_rendered_pages(page_pngs)
                    visual_quality = self._inspect_rendered_visual_quality(page_pngs)
                    if render_overflow_check:
                        overflow_checks = inspect_rendered_overflow(pptx_path, qa_dir, dpi=dpi)
                    if create_overview:
                        montage_path = create_montage(page_pngs, qa_dir / "montage.png")
                    pdf_path = render_result.get("pdf_path")
                    if pdf_path:
                        font_checks = detect_pdf_fonts(Path(str(pdf_path)), expected_fonts=expected_fonts)
                except Exception as render_error:
                    rendered_checks = {
                        "issues": [
                            {
                                "type": "rendered_visual_qa_unavailable",
                                "message": str(render_error),
                            }
                        ],
                        "blank_pages": [],
                    }
                    visual_quality = {
                        "enabled": False,
                        "score": None,
                        "issues": rendered_checks["issues"],
                        "recommendations": ["安装 PyMuPDF/fitz 后可启用渲染级视觉质量检查。"],
                    }

            issues = []
            issues.extend(geometry.get("issues", []))
            issues.extend(rendered_checks.get("issues", []))
            issues.extend(overflow_checks.get("issues", []))
            issues.extend(font_checks.get("issues", []))
            issues.extend(design_quality.get("issues", []))
            issues.extend(visual_quality.get("issues", []))

            report = {
                "success": len(issues) == 0,
                "pptx_path": str(pptx_path),
                "qa_dir": str(qa_dir),
                "render": render_result,
                "montage_path": str(montage_path) if montage_path else None,
                "geometry": geometry,
                "rendered_pages": rendered_checks,
                "rendered_overflow": overflow_checks,
                "fonts": font_checks,
                "design_quality": design_quality,
                "visual_quality": visual_quality,
                "issues": issues,
                "issue_count": len(issues),
            }

            report_path = qa_dir / "report.json"
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["report_path"] = str(report_path)

            summary = (
                f"PPT验证完成：{pptx_path.name}，发现 {len(issues)} 个问题"
                if issues
                else f"PPT验证通过：{pptx_path.name}"
            )
            return {
                "success": True,
                "data": report,
                "summary": summary,
            }
        except Exception as e:
            logger.error("validate_pptx_failed", path=path, error=str(e), exc_info=True)
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"PPT验证失败：{str(e)[:80]}",
            }

    def _resolve_path(self, path: str) -> Path:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = self.working_dir / file_path
        return file_path.resolve()

    def _resolve_output_dir(self, output_dir: Optional[str], pptx_path: Path) -> Path:
        if output_dir:
            path = Path(output_dir)
            if not path.is_absolute():
                path = self.working_dir / path
            return path.resolve()
        return (self.default_qa_root / f"{pptx_path.stem}_{uuid.uuid4().hex[:8]}").resolve()

    def _inspect_rendered_visual_quality(self, page_pngs: List[Path]) -> Dict[str, Any]:
        try:
            from PIL import Image, ImageChops
        except ImportError:
            return {
                "enabled": False,
                "score": None,
                "issues": [{"type": "visual_quality_unavailable", "message": "Pillow 未安装"}],
            }

        slides: List[Dict[str, Any]] = []
        issues: List[Dict[str, Any]] = []
        for slide_index, path in enumerate(page_pngs, start=1):
            with Image.open(path) as image:
                rgb = image.convert("RGB")
                sample = rgb.resize((320, 180))

            bg = self._estimate_background_color(sample)
            bg_image = Image.new("RGB", sample.size, bg)
            diff = ImageChops.difference(sample, bg_image).convert("L")
            threshold = 18
            changed = diff.point(lambda value: 255 if value > threshold else 0)
            bbox = changed.getbbox()
            width, height = sample.size
            changed_pixels = sum(1 for value in changed.getdata() if value)
            ink_ratio = changed_pixels / float(width * height)

            score = 100
            slide_issues: List[Dict[str, Any]] = []
            margin_ratio = None
            if bbox:
                left, top, right, bottom = bbox
                margin_ratio = min(left / width, top / height, (width - right) / width, (height - bottom) / height)
                if margin_ratio < 0.015 and ink_ratio > 0.08:
                    score -= 18
                    slide_issues.append(
                        {
                            "type": "rendered_low_margin",
                            "slide": slide_index,
                            "margin_ratio": round(margin_ratio, 4),
                        }
                    )
            else:
                score -= 35
                slide_issues.append({"type": "rendered_nearly_blank", "slide": slide_index, "ink_ratio": 0})

            if ink_ratio > 0.58:
                score -= 30
                slide_issues.append(
                    {"type": "rendered_visual_overcrowding", "slide": slide_index, "ink_ratio": round(ink_ratio, 4)}
                )
            elif ink_ratio > 0.48:
                score -= 16
                slide_issues.append(
                    {"type": "rendered_dense_composition", "slide": slide_index, "ink_ratio": round(ink_ratio, 4)}
                )
            elif ink_ratio < 0.01:
                score -= 25
                slide_issues.append(
                    {"type": "rendered_sparse_or_blank", "slide": slide_index, "ink_ratio": round(ink_ratio, 4)}
                )

            score = max(0, score)
            issues.extend(
                issue
                for issue in slide_issues
                if issue["type"] in {"rendered_visual_overcrowding", "rendered_low_margin", "rendered_nearly_blank"}
            )
            slides.append(
                {
                    "slide": slide_index,
                    "score": score,
                    "ink_ratio": round(ink_ratio, 4),
                    "margin_ratio": round(margin_ratio, 4) if margin_ratio is not None else None,
                    "background_rgb": bg,
                    "issues": slide_issues,
                }
            )

        overall = round(sum(item["score"] for item in slides) / len(slides), 1) if slides else 0
        return {
            "enabled": True,
            "score": overall,
            "grade": self._design_grade(overall),
            "slides": slides,
            "issues": issues,
            "recommendations": self._visual_recommendations(slides),
        }

    def _estimate_background_color(self, image: Any) -> tuple[int, int, int]:
        width, height = image.size
        points = [
            image.getpixel((0, 0)),
            image.getpixel((width - 1, 0)),
            image.getpixel((0, height - 1)),
            image.getpixel((width - 1, height - 1)),
            image.getpixel((width // 2, 0)),
            image.getpixel((width // 2, height - 1)),
        ]
        return tuple(sorted(channel)[len(channel) // 2] for channel in zip(*points))

    def _visual_recommendations(self, slides: List[Dict[str, Any]]) -> List[str]:
        recommendations: List[str] = []
        if any(item["ink_ratio"] > 0.48 for item in slides):
            recommendations.append("渲染结果视觉占用过高，建议减少同页元素、拆页或把正文改成图表/流程。")
        if any((item["margin_ratio"] is not None and item["margin_ratio"] < 0.015) for item in slides):
            recommendations.append("渲染结果贴边明显，建议增加页边距并缩小主内容区域。")
        if any(item["ink_ratio"] < 0.01 for item in slides):
            recommendations.append("渲染结果接近空白，建议检查图片、图表或文字是否成功输出。")
        return recommendations

    def _inspect_design_quality(self, pptx_path: Path) -> Dict[str, Any]:
        try:
            from pptx import Presentation
            from pptx.enum.shapes import MSO_SHAPE_TYPE
        except ImportError:
            return {
                "enabled": False,
                "score": None,
                "issues": [{"type": "design_quality_unavailable", "message": "python-pptx 未安装"}],
            }

        prs = Presentation(str(pptx_path))
        slide_scores: List[Dict[str, Any]] = []
        issues: List[Dict[str, Any]] = []
        previous_signature = None
        repeated_layouts = 0

        for slide_index, slide in enumerate(prs.slides, start=1):
            text_chars = 0
            text_lines = 0
            text_boxes = 0
            visual_shapes = 0
            pictures = 0
            tables = 0
            charts = 0
            font_sizes: List[float] = []
            shape_signature = []

            for shape in slide.shapes:
                left = round(int(getattr(shape, "left", 0) or 0) / 914400, 1)
                top = round(int(getattr(shape, "top", 0) or 0) / 914400, 1)
                width = round(int(getattr(shape, "width", 0) or 0) / 914400, 1)
                height = round(int(getattr(shape, "height", 0) or 0) / 914400, 1)
                shape_signature.append((left, top, width, height))

                if getattr(shape, "has_text_frame", False):
                    text = (getattr(shape, "text", "") or "").strip()
                    if text:
                        text_boxes += 1
                        text_chars += len(text)
                        text_lines += max(1, len([line for line in text.splitlines() if line.strip()]))
                    if len(text) > 2:
                        for paragraph in shape.text_frame.paragraphs:
                            for run in paragraph.runs:
                                size = getattr(run.font, "size", None)
                                if size is not None:
                                    font_sizes.append(round(size.pt, 1))
                if getattr(shape, "has_table", False):
                    tables += 1
                    visual_shapes += 1
                if getattr(shape, "has_chart", False):
                    charts += 1
                    visual_shapes += 1
                shape_type = getattr(shape, "shape_type", None)
                if shape_type == MSO_SHAPE_TYPE.PICTURE:
                    pictures += 1
                    visual_shapes += 1
                elif not getattr(shape, "has_text_frame", False):
                    visual_shapes += 1

            signature = tuple(shape_signature[:8])
            if previous_signature == signature and slide_index > 1:
                repeated_layouts += 1
            previous_signature = signature

            score = 100
            slide_issues: List[Dict[str, Any]] = []
            if text_chars > 900 or text_lines > 14:
                score -= 25
                slide_issues.append(
                    {"type": "high_text_density", "slide": slide_index, "chars": text_chars, "lines": text_lines}
                )
            elif text_chars > 620 or text_lines > 10:
                score -= 15
                slide_issues.append(
                    {"type": "moderate_text_density", "slide": slide_index, "chars": text_chars, "lines": text_lines}
                )
            if visual_shapes == 0 and text_boxes >= 2 and slide_index > 1:
                score -= 20
                slide_issues.append({"type": "text_only_slide", "slide": slide_index})
            if font_sizes:
                max_font = max(font_sizes)
                min_font = min(font_sizes)
                if max_font < 24 and slide_index > 1:
                    score -= 10
                    slide_issues.append({"type": "weak_title_hierarchy", "slide": slide_index, "max_font": max_font})
                if min_font < 8:
                    score -= 10
                    slide_issues.append({"type": "tiny_text", "slide": slide_index, "min_font": min_font})
                if max_font - min_font < 8 and text_boxes >= 2:
                    score -= 8
                    slide_issues.append({"type": "low_typographic_contrast", "slide": slide_index})

            score = max(0, score)
            issues.extend(issue for issue in slide_issues if issue["type"] in {"high_text_density", "text_only_slide", "tiny_text"})
            slide_scores.append(
                {
                    "slide": slide_index,
                    "score": score,
                    "text_chars": text_chars,
                    "text_lines": text_lines,
                    "text_boxes": text_boxes,
                    "visual_shapes": visual_shapes,
                    "pictures": pictures,
                    "tables": tables,
                    "charts": charts,
                    "issues": slide_issues,
                }
            )

        if repeated_layouts >= max(2, len(prs.slides) // 3):
            issues.append({"type": "repeated_layout_pattern", "count": repeated_layouts})

        overall = round(sum(item["score"] for item in slide_scores) / len(slide_scores), 1) if slide_scores else 0
        if repeated_layouts:
            overall = max(0, overall - min(12, repeated_layouts * 3))
        return {
            "enabled": True,
            "score": overall,
            "grade": self._design_grade(overall),
            "repeated_layouts": repeated_layouts,
            "slides": slide_scores,
            "issues": issues,
            "recommendations": self._design_recommendations(slide_scores, repeated_layouts),
        }

    def _design_grade(self, score: float) -> str:
        if score >= 90:
            return "excellent"
        if score >= 78:
            return "good"
        if score >= 65:
            return "acceptable"
        return "needs_improvement"

    def _design_recommendations(self, slide_scores: List[Dict[str, Any]], repeated_layouts: int) -> List[str]:
        recommendations: List[str] = []
        if any(item["text_chars"] > 620 or item["text_lines"] > 10 for item in slide_scores):
            recommendations.append("拆分高文字密度页面，或改为主结论+卡片/图表结构。")
        if any(item["visual_shapes"] == 0 and item["text_boxes"] >= 2 and item["slide"] > 1 for item in slide_scores):
            recommendations.append("为纯文字页面补充图表、流程、指标卡或领域示意组件。")
        if repeated_layouts:
            recommendations.append("连续页面版式过于接近，建议交替使用双栏、卡片、图表和时间线布局。")
        if any(any(issue["type"] == "weak_title_hierarchy" for issue in item["issues"]) for item in slide_scores):
            recommendations.append("提高标题字号或降低正文强调，增强标题/正文层级。")
        return recommendations

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": "validate_pptx",
            "description": "渲染PPTX为PDF/PNG并执行基础QA检查，返回montage、report.json、字体信息和设计质量评分。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "PPTX文件路径"},
                    "output_dir": {"type": "string", "description": "QA输出目录，可选"},
                    "expected_fonts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "期望字体名称列表，可选",
                    },
                    "render_png": {"type": "boolean", "description": "是否渲染PNG页面", "default": True},
                    "create_overview": {"type": "boolean", "description": "是否生成montage总览图", "default": True},
                    "render_overflow_check": {
                        "type": "boolean",
                        "description": "是否执行渲染级溢出检测，默认开启",
                        "default": True,
                    },
                    "dpi": {"type": "integer", "description": "PNG渲染DPI，默认144"},
                },
                "required": ["path"],
            },
        }

    def is_available(self) -> bool:
        return True


tool = ValidatePptxTool()
