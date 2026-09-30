from datetime import datetime, timedelta

import numpy as np
import pytest

from app.tools.visualization.create_report_chart.domain import weather_timeseries as weather
from app.tools.visualization.create_report_chart.validation import ChartDataError


def records(count=56):
    start = datetime(2026, 9, 11, 2)
    return [dict(forecast_time=(start + timedelta(hours=3 * i)).isoformat(),
                 wind_speed=2, wind_direction_degrees=90, temperature=25,
                 precipitation_probability=10, humidity=70) for i in range(count)]


def render(rows, **options):
    return weather.render_weather_timeseries(title='七天气象', data={'records': rows},
                                            options=options, output_context='word', style_profile='report')


def test_seven_days_produce_one_image_with_all_points(monkeypatch):
    figures = []
    original = weather.plt.subplots

    def capture(*args, **kwargs):
        fig, ax = original(*args, **kwargs)
        figures.append(fig)
        return fig, ax

    monkeypatch.setattr(weather.plt, 'subplots', capture)
    encoded, metadata, _ = render(list(reversed(records())))
    assert encoded and len(figures) == 1
    assert metadata['day_count'] == 7 and metadata['valid_point_count'] == 56
    assert metadata['start_time'] == '2026-09-11 02:00:00'
    assert metadata['end_time'] == '2026-09-17 23:00:00'
    assert len(figures[0].axes[0].lines[0].get_xdata()) == 56
    assert 0 < metadata['direction_arrow_count'] < metadata['valid_point_count']


def test_missing_slot_breaks_curve_without_counting_synthetic_values(monkeypatch):
    lines = []
    original = weather.plt.close

    def capture(fig):
        if hasattr(fig, 'axes'):
            lines.extend(fig.axes[0].lines)
        return original(fig)

    monkeypatch.setattr(weather.plt, 'close', capture)
    rows = records()
    del rows[8]
    _, metadata, _ = render(rows)
    assert metadata['gap_count'] == 1 and metadata['valid_point_count'] == 55
    assert np.isnan(lines[0].get_ydata()).sum() == 1


def test_single_day_uses_the_same_interface():
    _, metadata, _ = render(records(8))
    assert metadata['day_count'] == 1 and not metadata['multi_day']


def test_rejects_span_longer_than_seven_days():
    with pytest.raises(ChartDataError, match='7个自然日'):
        render(records(57))


@pytest.mark.parametrize('interval', [0, -1, float('nan'), 'invalid'])
def test_rejects_invalid_sample_interval(interval):
    with pytest.raises(ChartDataError, match='expected_interval_hours'):
        render(records(), expected_interval_hours=interval)


def test_direction_arrows_have_true_angles_and_calm_has_no_arrow(monkeypatch):
    from matplotlib.offsetbox import AnnotationBbox
    from matplotlib.patches import FancyArrowPatch

    figures = []
    original = weather.plt.subplots

    def capture(*args, **kwargs):
        fig, ax = original(*args, **kwargs)
        figures.append(fig)
        return fig, ax

    monkeypatch.setattr(weather.plt, 'subplots', capture)
    rows = records(7)
    for row, direction in zip(rows, [0, 90, 180, 270, 45, 90, None]):
        row['wind_direction_degrees'] = direction
    rows[5]['wind_speed'] = 0
    render(rows)
    ax = figures[0].axes[0]
    arrows = [artist for artist in ax.artists if isinstance(artist, AnnotationBbox)]
    assert len(arrows) == 5
    expected = [(0, -18), (-18, 0), (0, 18), (18, 0), (-18 / np.sqrt(2), -18 / np.sqrt(2))]
    for artist, delta in zip(arrows, expected):
        patch = next(child for child in artist.offsetbox.get_children() if isinstance(child, FancyArrowPatch))
        start, end = patch._posA_posB
        np.testing.assert_allclose(np.subtract(end, start), delta, atol=1e-10)
    assert len(next(line for line in ax.lines if line.get_label() == '静风（方向未定义）').get_xdata()) == 1
    labels = [text.get_text() for text in ax.get_legend().get_texts()]
    assert '风向（等长箭头，指向气流去向）' in labels


def test_negative_wind_speed_is_not_drawn_as_a_valid_forecast():
    rows = records(3)
    rows[1]['wind_speed'] = -1
    with pytest.raises(ChartDataError, match='风速不能为负数'):
        render(rows)


@pytest.mark.parametrize('speeds', [[0, 2, 0], [0, 0, 0]])
def test_wind_vectors_explain_speed_scale_and_separate_calm(monkeypatch, speeds):
    from matplotlib.quiver import QuiverKey
    from app.tools.visualization.create_report_chart.domain import wind_timeseries as wind

    figures = []
    original = wind._figure_to_base64

    def capture(fig):
        figures.append(fig)
        return original(fig)

    monkeypatch.setattr(wind, '_figure_to_base64', capture)
    moving = sum(speed > 0 for speed in speeds)
    _, metadata, _ = wind.render_wind_timeseries(
        title='Wind vectors',
        data={'timestamps': ['2026-09-30 00:00', '2026-09-30 01:00', '2026-09-30 02:00'],
              'wind_speeds': speeds, 'wind_directions': [0, 90, 180],
              'concentrations': [20, 30, 25], 'wind_direction_convention': 'meteorological_from'},
        options={}, output_context='word', style_profile='report',
    )
    assert metadata['rendered_vector_count'] == moving
    assert metadata['calm_point_count'] == 3 - moving
    keys = figures[0].axes[1].findobj(QuiverKey)
    assert len(keys) == int(moving > 0)
    if keys:
        assert 'm/s' in keys[0].label and '气流去向' in keys[0].label
