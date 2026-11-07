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
