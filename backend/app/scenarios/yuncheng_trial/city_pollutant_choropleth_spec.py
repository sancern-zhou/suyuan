from app.scenarios.yuncheng_trial.city_pollutant_choropleth import (
    _legend_labels,
    _scale_bar_degrees,
)


def test_legend_labels_use_pollutant_threshold_ranges() -> None:
    assert _legend_labels("O3") == [
        "0~160",
        "160~200",
        "200~300",
        "300~400",
        "400~800",
        ">800",
        "无数据",
    ]


def test_scale_bar_degrees_converts_kilometers_at_latitude() -> None:
    scale_degrees = _scale_bar_degrees(20, latitude=35.0)

    assert 0.21 < scale_degrees < 0.23
