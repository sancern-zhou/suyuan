from pathlib import Path

import pytest

from app.tools.office.create_pptx_tool import CreatePptxTool
from app.tools.office.validate_pptx_tool import ValidatePptxTool


def test_create_pptx_auto_design_rewrites_dense_text_and_bullets():
    tool = CreatePptxTool()
    theme = tool._normalize_theme({})
    brief = tool._normalize_design_brief(None, "污染分析报告", [])
    slides = [
        {
            "type": "text",
            "title": "核心结论",
            "text": "臭氧污染过程受高温、低湿、弱风和VOCs活性组分共同影响。" * 12,
        },
        {
            "type": "bullets",
            "title": "治理建议",
            "bullets": [
                "强化VOCs重点行业错峰管控",
                "午后加强臭氧前体物协同削峰",
                "关注交通源NOx排放变化",
                "结合气象扩散条件动态调整预警",
                "对高值站点开展走航溯源",
            ],
        },
    ]

    normalized, slide_plan, density_report = tool._normalize_slides(slides, theme, brief)

    assert normalized[0]["type"] == "key_message"
    assert normalized[0]["message"]
    assert normalized[0]["items"]
    assert normalized[1]["type"] == "card_grid"
    assert len(normalized[1]["items"]) == 5
    assert [item["type"] for item in slide_plan] == ["key_message", "card_grid"]
    assert len(density_report["rewritten_slides"]) == 2


def test_create_pptx_auto_design_can_be_disabled():
    tool = CreatePptxTool()
    theme = tool._normalize_theme({})
    brief = tool._normalize_design_brief(None, "普通汇报", [])
    slides = [{"type": "bullets", "title": "列表", "bullets": [f"项目 {idx}" for idx in range(6)]}]

    normalized, _, density_report = tool._normalize_slides(slides, theme, brief, auto_design=False)

    assert normalized[0]["type"] == "bullets"
    assert density_report["rewritten_slides"] == []


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


def test_create_pptx_quality_gate_returns_rewrite_pages():
    report = {
        "design_quality": {
            "score": 72,
            "recommendations": ["拆分高文字密度页面。"],
            "slides": [{"slide": 2, "score": 70}],
        },
        "visual_quality": {
            "score": 76,
            "recommendations": ["增加页边距。"],
            "slides": [{"slide": 3, "score": 74}],
        },
        "issues": [
            {"type": "high_text_density", "slide": 2},
            {"type": "rendered_low_margin", "slide": 3},
        ],
    }

    gate = CreatePptxTool()._quality_gate(report)

    assert gate["status"] == "rewrite_required"
    assert gate["rewrite_required"] is True
    assert [item["slide"] for item in gate["rewrite_pages"]] == [2, 3]
    assert gate["recommendations"] == ["拆分高文字密度页面。", "增加页边距。"]
