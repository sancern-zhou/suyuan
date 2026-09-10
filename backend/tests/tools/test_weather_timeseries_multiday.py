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
    encoded, metadata, _ = render(list(reversed(records())), multi_day=True)
    assert encoded and len(figures) == 1
    assert metadata['day_count'] == 7 and metadata['valid_point_count'] == 56
    assert metadata['start_time'] == '2026-09-11 02:00:00'
    assert metadata['end_time'] == '2026-09-17 23:00:00'
    assert len(figures[0].axes[0].lines[0].get_xdata()) == 56


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
    _, metadata, _ = render(rows, multi_day=True)
    assert metadata['gap_count'] == 1 and metadata['valid_point_count'] == 55
    assert np.isnan(lines[0].get_ydata()).sum() == 1


def test_single_day_still_works_and_multiday_requires_opt_in():
    _, metadata, _ = render(records(8))
    assert metadata['day_count'] == 1 and not metadata['multi_day']
    with pytest.raises(ChartDataError, match='multi_day'):
        render(records())


def test_rejects_span_longer_than_seven_days():
    with pytest.raises(ChartDataError, match='7个自然日'):
        render(records(57), multi_day=True)


@pytest.mark.parametrize('interval', [0, -1, float('nan'), 'invalid'])
def test_rejects_invalid_sample_interval(interval):
    with pytest.raises(ChartDataError, match='expected_interval_hours'):
        render(records(), multi_day=True, expected_interval_hours=interval)
