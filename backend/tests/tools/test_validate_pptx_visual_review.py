"""validate_pptx visual_review 纯函数测试：worst_pages 定位与挂载提示。"""
from app.tools.office.validate_pptx_tool import ValidatePptxTool


def _report_with_scores(scores):
    visual = {
        "enabled": True,
        "score": 90,
        "slides": [
            {"slide": index + 1, "score": score, "ink_ratio": 0.3, "margin_ratio": 0.05,
             "background_rgb": [255, 255, 255], "issues": []}
            for index, score in enumerate(scores)
        ],
        "issues": [],
        "recommendations": [],
    }
    pages = [
        {"slide": index + 1, "page_number": index + 1, "file_name": f"page-{index + 1:03d}.png",
         "png_path": f"/qa/pages/page-{index + 1:03d}.png"}
        for index in range(len(scores))
    ]
    return {"visual_quality": visual, "pages": pages, "montage_path": "/qa/montage.png"}


def test_visual_review_picks_lowest_score_pages_with_png_paths():
    review = ValidatePptxTool()._build_visual_review(_report_with_scores([95, 41, 88, 12, 77]))

    assert [item["slide"] for item in review["worst_pages"]] == [4, 2, 5]
    assert review["worst_pages"][0]["png_path"].endswith("page-004.png")
    assert review["worst_pages"][0]["score"] == 12
    assert "as_multimodal_attachment" in review["hint"]


def test_visual_review_handles_missing_visual_quality():
    review = ValidatePptxTool()._build_visual_review({"visual_quality": {"enabled": False}, "pages": []})

    assert review["worst_pages"] == []
    assert "as_multimodal_attachment" in review["hint"]


def test_visual_review_caps_at_three_pages():
    review = ValidatePptxTool()._build_visual_review(_report_with_scores([10, 20, 30, 40, 50, 60]))

    assert len(review["worst_pages"]) == 3


def _deck_with(problem: str):
    """构造问题页：overlap=两文本框大重叠；placeholder=占位符文本；clean=正常。"""
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    def box(x, y, w, h, text):
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        shape.text_frame.text = text
        return shape

    if problem == "overlap":
        box(1, 1, 4, 1, "左上文本框内容")
        box(2, 1.2, 4, 1, "与其大面积重叠的文本框")
    elif problem == "placeholder":
        box(1, 1, 6, 1, "站点数据：待补充")
        box(1, 2, 6, 1, "正常内容" * 3)
    else:
        box(1, 1, 6, 1, "正常标题内容" * 2)
        box(1, 2.5, 6, 1, "正常正文内容" * 3)
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / f"{problem}.pptx"
    prs.save(path)
    return path


def test_design_check_flags_text_overlap():
    report = ValidatePptxTool()._inspect_design_quality(_deck_with("overlap"))

    assert any(i["type"] == "text_shape_overlap" for i in report["issues"])


def test_design_check_flags_placeholder_residue():
    report = ValidatePptxTool()._inspect_design_quality(_deck_with("placeholder"))

    assert any(i["type"] == "text_placeholder_residue" for i in report["issues"])


def test_design_check_clean_deck_has_no_new_flags():
    report = ValidatePptxTool()._inspect_design_quality(_deck_with("clean"))

    assert not any(
        i["type"] in {"text_shape_overlap", "text_placeholder_residue"} for i in report["issues"]
    )


def test_text_overlap_pairs_threshold():
    pairs = ValidatePptxTool()._text_overlap_pairs([(0, 0, 4, 1), (0.2, 0.1, 4, 1)])
    assert pairs  # 重叠 >25%
    assert ValidatePptxTool()._text_overlap_pairs([(0, 0, 4, 1), (0, 3, 4, 1)]) == []
    # 相邻不重叠
    assert ValidatePptxTool()._text_overlap_pairs([(0, 0, 2, 1), (2.0, 0, 2, 1)]) == []
