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
            description="渲染PPTX并执行基础交付检查：PDF/PNG预览、montage、空页/越界/字体检测。",
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
            montage_path = None

            if render_png:
                render_result = render_deck(pptx_path, qa_dir, dpi=dpi)
                page_pngs = [Path(path) for path in render_result.get("page_pngs", [])]
                rendered_checks = inspect_rendered_pages(page_pngs)
                if render_overflow_check:
                    overflow_checks = inspect_rendered_overflow(pptx_path, qa_dir, dpi=dpi)
                if create_overview:
                    montage_path = create_montage(page_pngs, qa_dir / "montage.png")
                pdf_path = render_result.get("pdf_path")
                if pdf_path:
                    font_checks = detect_pdf_fonts(Path(str(pdf_path)), expected_fonts=expected_fonts)

            issues = []
            issues.extend(geometry.get("issues", []))
            issues.extend(rendered_checks.get("issues", []))
            issues.extend(overflow_checks.get("issues", []))
            issues.extend(font_checks.get("issues", []))

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

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": "validate_pptx",
            "description": "渲染PPTX为PDF/PNG并执行基础QA检查，返回montage、report.json、问题列表和字体信息。",
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
