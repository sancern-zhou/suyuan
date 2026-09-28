from app.utils.echarts_layout import normalize_echarts_layout


def _base_option(**overrides):
    option = {
        "legend": {"bottom": 0, "data": ["A", "B"]},
        "grid": {"left": 70, "right": 40, "top": 80, "bottom": 70},
        "xAxis": {"type": "category", "name": "时间", "nameLocation": "end", "nameGap": 30},
        "yAxis": {"type": "value"},
        "series": [{"type": "line", "data": [1, 2]}],
    }
    option.update(overrides)
    return option


def test_bottom_legend_is_anchored_and_grid_hugs_the_labels():
    option = normalize_echarts_layout(_base_option())

    # 图例抬到底部上方 35px，grid 预留 35 + 25(图例) + 24(刻度) = 84
    assert option["legend"]["bottom"] == 35
    assert option["grid"]["bottom"] == 84


def test_centered_x_axis_name_reserves_an_extra_row():
    option = normalize_echarts_layout(_base_option(
        xAxis={"type": "category", "name": "时间", "nameLocation": "middle", "nameGap": 30}
    ))

    # 35 + 25 + 24 + (30 + 16) = 130
    assert option["grid"]["bottom"] == 130


def test_grid_bottom_never_shrinks_below_existing_value():
    option = normalize_echarts_layout(_base_option(grid={"bottom": 200}))

    assert option["grid"]["bottom"] == 200


def test_top_legend_does_not_touch_grid_bottom():
    option = normalize_echarts_layout(
        _base_option(legend={"top": 15, "data": ["A", "B"]}, grid={"bottom": 40})
    )

    assert option["grid"]["bottom"] == 40


def test_missing_legend_position_defaults_to_bottom():
    option = normalize_echarts_layout(_base_option(legend={"data": ["A", "B"]}))

    assert option["legend"]["bottom"] == 35
    assert option["grid"]["bottom"] == 84


def test_side_legend_does_not_reserve_bottom_space():
    option = normalize_echarts_layout(
        _base_option(legend={"right": 10, "data": ["A", "B"]}, grid={"bottom": 40})
    )

    assert option["grid"]["bottom"] == 40


def test_option_without_grid_is_unchanged():
    option = normalize_echarts_layout({"legend": {"bottom": 0}, "series": [{"type": "pie"}]})

    assert "grid" not in option
    assert option["legend"]["bottom"] == 0
