from app.tools.office.editable_ppt.visual_compare import compare_slide_renders


def test_visual_compare_reports_missing_and_shifted_critical_elements():
    result = compare_slide_renders(
        html_png=None,
        pptx_png=None,
        html_elements=[
            {"id": "title", "box": [80, 60, 800, 70], "critical": True},
            {"id": "chart", "box": [80, 180, 700, 400], "critical": True},
        ],
        pptx_elements=[{"id": "title", "box": [88, 60, 800, 70], "critical": True}],
        geometry_tolerance_px=4,
    )
    assert [issue["code"] for issue in result.issues] == [
        "CRITICAL_ELEMENT_GEOMETRY_DRIFT", "CRITICAL_ELEMENT_MISSING"
    ]
