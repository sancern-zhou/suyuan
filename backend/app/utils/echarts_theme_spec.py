from app.utils.echarts_theme import apply_echarts_report_theme


def test_echarts_theme_applies_defaults_without_overwriting_semantic_colors():
    option = apply_echarts_report_theme({
        "title": {"text": "趋势"},
        "legend": {"data": ["PM2.5"]},
        "xAxis": {"name": "日期"},
        "yAxis": {"name": "浓度（μg/m³）"},
        "series": [{"type": "line", "data": [1, 2]}],
    })

    assert option["color"]
    assert option["textStyle"]["fontFamily"]
    assert option["legend"]["textStyle"]["fontFamily"]
    assert option["yAxis"]["name"] == "浓度（μg/m³）"


def test_echarts_theme_preserves_explicit_palette_and_background():
    option = apply_echarts_report_theme({"color": ["#123456"], "backgroundColor": "#fff"})

    assert option["color"] == ["#123456"]
    assert option["backgroundColor"] == "#fff"
