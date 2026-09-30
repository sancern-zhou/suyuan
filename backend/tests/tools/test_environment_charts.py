import math

import matplotlib.pyplot as plt
import pytest

from app.utils.environment_charts import (
    AQI_COLORS, MISSING_COLOR, add_standard_limit, aqi_color,
    get_environment_limit, get_pollutant_scale, legend_below, pollutant_color,
    pollutant_iaqi,
)


def context(pollutant="PM2.5", average_time="24h", observed_on="2026-05-01"):
    return dict(pollutant=pollutant, average_time=average_time, observed_on=observed_on,
                unit="mg/m3" if pollutant == "CO" else "ug/m3")


@pytest.mark.parametrize("value,index", [(0, 0), (50, 0), (51, 1), (100, 1),
    (101, 2), (150, 2), (151, 3), (200, 3), (201, 4), (300, 4), (301, 5), (500, 5)])
def test_aqi_grade_boundaries(value, index):
    assert aqi_color(value) == AQI_COLORS[index]


@pytest.mark.parametrize("pollutant,value", [("PM2.5", 60), ("PM10", 120)])
def test_particle_daily_and_hourly_grading_use_2026_breakpoints(pollutant, value):
    for average_time in ("24h", "1h"):
        assert pollutant_iaqi(value, **context(pollutant, average_time)) == 100
        assert pollutant_color(value, **context(pollutant, average_time)) == AQI_COLORS[1]
        assert pollutant_color(value + 1, **context(pollutant, average_time)) == AQI_COLORS[2]


@pytest.mark.parametrize("pollutant,period,value,expected", [
    ("SO2", "1h", 900, 200), ("O3", "8h", 900, 300),
    ("NO2", "1h", 200, 100), ("CO", "24h", 4, 100),
    ("O3", "daily_max_8h", 160, 100), ("PM2.5", "24h", 500, 500),
])
def test_pollutant_specific_breakpoints_and_caps(pollutant, period, value, expected):
    assert pollutant_iaqi(value, **context(pollutant, period)) == expected


def test_concentration_rounding_and_missing_are_explicit():
    assert pollutant_iaqi(60.5, **context()) == 100
    assert pollutant_iaqi(60.6, **context()) == 101
    for missing in (None, math.nan):
        assert aqi_color(missing) == MISSING_COLOR
        assert pollutant_color(missing, **context()) == MISSING_COLOR
    for invalid in (-1, math.inf, -math.inf):
        with pytest.raises(ValueError):
            pollutant_color(invalid, **context())


@pytest.mark.parametrize("pollutant,period,transition,final", [
    ("PM2.5", "24h", (35, 60), (25, 50)),
    ("PM2.5", "annual", (15, 30), (10, 25)),
    ("PM10", "24h", (50, 120), (50, 100)),
    ("PM10", "annual", (40, 60), (20, 50)),
    ("SO2", "24h", (50, 150), (50, 50)),
    ("SO2", "annual", (20, 60), (20, 20)),
    ("SO2", "1h", (150, 500), (150, 150)),
    ("NO2", "24h", (80, 80), (50, 50)),
    ("NO2", "annual", (40, 40), (30, 30)),
    ("NO2", "1h", (200, 200), (200, 200)),
    ("CO", "24h", (4, 4), (4, 4)),
    ("CO", "1h", (10, 10), (10, 10)),
    ("O3", "daily_max_8h", (100, 160), (100, 160)),
    ("O3", "1h", (160, 200), (160, 200)),
])
def test_quality_limits_for_both_grades_and_implementation_phases(pollutant, period, transition, final):
    for day, values, phase in [("2030-12-31", transition, "过渡阶段"),
                               ("2031-01-01", final, "2031年起")]:
        for grade in (1, 2):
            limit = get_environment_limit(grade=grade, **context(pollutant, period, day))
            assert limit["value"] == values[grade - 1]
            assert limit["standard"] == "GB 3095-2026"
            assert limit["phase"] == phase
            assert limit["source"].startswith("https://www.mee.gov.cn/")


def test_no_legacy_version_or_guessed_units_and_periods():
    with pytest.raises(ValueError, match="不适用"):
        get_environment_limit(grade=2, **context(observed_on="2026-02-28"))
    with pytest.raises(ValueError, match="不适用"):
        pollutant_color(60, **context(observed_on="2025-05-01"))
    assert get_environment_limit(grade=2, **context(observed_on="2026-03-01"))["value"] == 60
    with pytest.raises(ValueError, match="单位"):
        get_environment_limit(grade=2, **{**context("CO"), "unit": "ug/m3"})
    for pollutant, period in [("PM2.5", "1h"), ("O3", "8h"), ("PM10", "monthly"), ("VOC", "24h")]:
        with pytest.raises(ValueError):
            get_environment_limit(grade=2, **context(pollutant, period))
    with pytest.raises(ValueError):
        pollutant_color(20, **context(average_time="annual"))
    with pytest.raises(ValueError):
        get_environment_limit(grade=True, **context())
    with pytest.raises(TypeError):
        get_environment_limit(grade=2, standard_version="2012", **context())


def test_shared_scale_does_not_expose_mutable_configuration():
    scale = get_pollutant_scale(**context())
    assert scale["concentration_breakpoints"][:3] == [0, 35, 60]
    scale["concentration_breakpoints"][2] = 75
    assert get_pollutant_scale(**context())["concentration_breakpoints"][2] == 60


def test_limit_line_rejects_mismatched_period_and_remains_visible():
    fig, ax = plt.subplots()
    try:
        ax.set_ylim(0, 30)
        with pytest.raises(ValueError, match="不匹配"):
            add_standard_limit(ax, data_average_time="1h", grade=2, **context())
        assert not ax.lines
        line = add_standard_limit(ax, data_average_time="1h", reference_only=True,
                                  grade=2, **context())
        assert list(line.get_ydata()) == [60, 60]
        assert "不作该时段达标判定" in line.get_label()
        assert ax.get_ylim()[1] > 60
        assert line.environment_standard["reference_only"] is True
    finally:
        plt.close(fig)


def test_legend_below_merges_twin_axes_without_overlap(tmp_path):
    fig, ax = plt.subplots(figsize=(8, 5))
    right = ax.twinx()
    try:
        ax.plot([1, 2], [10, 20], label="Concentration")
        right.plot([1, 2], [2, 3], label="Wind speed")
        ax.set_xlabel("Date and time")
        ax.tick_params(axis="x", labelrotation=45)
        ax.legend()
        right.legend()
        legend = legend_below(ax, right, ncols=2)
        assert [item.get_text() for item in legend.get_texts()] == ["Concentration", "Wind speed"]
        assert right.get_legend() is None
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        assert legend.get_window_extent(renderer).y1 < ax.xaxis.label.get_window_extent(renderer).y0
        fig.savefig(tmp_path / "environment-legend.png", bbox_inches="tight")
    finally:
        plt.close(fig)


def test_legend_requires_meaningful_labels():
    fig, ax = plt.subplots()
    try:
        ax.plot([1, 2], [3, 4])
        with pytest.raises(ValueError, match="label"):
            legend_below(ax)
    finally:
        plt.close(fig)


def test_business_calendar_shares_official_colors_and_2026_breakpoints():
    from app.tools.visualization.create_report_chart.domain.aqi_calendar import (
        AQI_COLOR_MAP, calculate_iaqi, get_aqi_color, get_text_color,
    )
    assert list(AQI_COLOR_MAP.values())[:6] == list(AQI_COLORS)
    assert get_aqi_color(100) == aqi_color(100)
    assert calculate_iaqi(60, "PM2_5") == 100
    assert calculate_iaqi(120, "PM10") == 100
    assert calculate_iaqi(60.5, "PM2_5") == pollutant_iaqi(60.5, **context())
    assert calculate_iaqi(None, "PM2_5") is None
    assert get_text_color(AQI_COLORS[0]) == "black"
    assert get_text_color(AQI_COLORS[4]) == "white"
