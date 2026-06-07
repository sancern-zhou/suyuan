from pathlib import Path

import pytest

from app.tools.office.ppt_master_tool import CreatePptxWithPptMasterTool
from app.tools.office.validate_pptx_tool import ValidatePptxTool


def test_ppt_master_theme_normalizes_color_aliases():
    palette = CreatePptxWithPptMasterTool()._palette(
        "business_clean",
        {
            "primary_color": "#1E88E5",
            "secondary_color": "#43A047",
            "accent_color": "#FFA726",
        },
    )

    assert palette["primary"] == "1E88E5"
    assert palette["secondary"] == "43A047"
    assert palette["accent"] == "FFA726"


def test_validate_pptx_design_quality_report(tmp_path: Path):
    pptx = pytest.importorskip("pptx")
    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    text_box = slide.shapes.add_textbox(914400, 914400, 7315200, 914400)
    text_box.text = "设计质量测试"
    body = slide.shapes.add_textbox(914400, 1828800, 9144000, 3657600)
    body.text = "\n".join([f"这是一段用于模拟文字密度的内容 {idx}" for idx in range(16)])
    pptx_path = tmp_path / "quality.pptx"
    presentation.save(pptx_path)

    report = ValidatePptxTool()._inspect_design_quality(pptx_path)

    assert report["enabled"] is True
    assert "score" in report
    assert report["grade"] in {"excellent", "good", "acceptable", "needs_improvement"}
    assert report["slides"][0]["text_lines"] >= 16
    assert any(issue["type"] == "high_text_density" for issue in report["issues"])


def test_validate_pptx_toc_like_slide_is_not_flagged_text_only(tmp_path: Path):
    pptx = pytest.importorskip("pptx")
    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    title = slide.shapes.add_textbox(914400, 914400, 7315200, 914400)
    title.text = "汇报大纲"
    item1 = slide.shapes.add_textbox(1828800, 2286000, 9144000, 365760)
    item1.text = "1. 我们做了什么"
    item2 = slide.shapes.add_textbox(1828800, 2743200, 9144000, 365760)
    item2.text = "2. 怎么做的"
    pptx_path = tmp_path / "toc_like.pptx"
    presentation.save(pptx_path)

    report = ValidatePptxTool()._inspect_design_quality(pptx_path)

    assert not any(issue["type"] == "text_only_slide" for issue in report["issues"])


def test_validate_pptx_rendered_visual_quality_flags_overcrowding(tmp_path: Path):
    image_module = pytest.importorskip("PIL.Image")
    draw_module = pytest.importorskip("PIL.ImageDraw")
    image = image_module.new("RGB", (640, 360), "white")
    draw = draw_module.Draw(image)
    for x in range(8, 620, 20):
        for y in range(8, 340, 20):
            draw.rectangle((x, y, x + 17, y + 17), fill=(20, 20, 20))
    png_path = tmp_path / "dense.png"
    image.save(png_path)

    report = ValidatePptxTool()._inspect_rendered_visual_quality([png_path])

    assert report["enabled"] is True
    assert report["score"] < 100
    assert any(issue["type"] == "rendered_visual_overcrowding" for issue in report["issues"])


def test_ppt_master_quality_gate_returns_rewrite_when_validation_fails():
    gate = CreatePptxWithPptMasterTool()._workflow_quality_gate(
        [
            {"slide": 1, "layout": "cover_statement", "role": "cover"},
            {"slide": 2, "layout": "card_grid", "role": "content"},
        ],
        {
            "success": False,
            "design_quality": {"issues": [{"type": "text_only_slide", "slide": 2}]},
            "overflow_issues": [{"type": "rendered_low_margin", "slide": 3}],
        },
    )

    assert gate["status"] == "rewrite_required"
    assert gate["rewrite_required"] is True
    assert gate["qa_status"] == "needs_revision"
    assert gate["affected_slides"] == [2, 3]
    assert gate["issue_summary"]["validation_failed"] == 1
    assert any(issue["type"] == "validation_failed" for issue in gate["issues"])
    assert any(issue["type"] == "text_only_slide" for issue in gate["issues"])
    assert any(task["slide"] == 2 and task["action"] for task in gate["revision_tasks"])
    assert any(task["slide"] == 3 and task["priority"] == "high" for task in gate["revision_tasks"])


def test_ppt_master_quality_gate_distinguishes_qa_failed_from_revision_needed():
    gate = CreatePptxWithPptMasterTool()._workflow_quality_gate(
        [{"slide": 1, "layout": "cover_statement", "role": "cover"}],
        {
            "success": False,
            "issues": [{"type": "validation_error", "message": "render failed"}],
        },
    )

    assert gate["status"] == "qa_failed"
    assert gate["qa_status"] == "qa_failed"
    assert gate["rewrite_required"] is False
    assert gate["revision_tasks"] == []


def test_ppt_master_quality_summary_promotes_revision_loop():
    tool = CreatePptxWithPptMasterTool()
    summary = tool._build_summary(
        output_name="demo.pptx",
        slide_count=5,
        quality_gate={
            "qa_status": "needs_revision",
            "revision_tasks": [
                {"slide": 2, "type": "text_only_slide", "action": "补充视觉元素。"},
                {"slide": 4, "type": "rendered_low_margin", "action": "增加页边距。"},
            ],
        },
    )

    assert "已生成PPT初稿" in summary
    assert "QA发现 2 项需优化任务" in summary
    assert "继续迭代" in summary
