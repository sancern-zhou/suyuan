from datetime import date, timedelta

import pytest

from app.fetchers.xuchang_weather_com_daily_forecast import parse_daily_forecast_page


def page_for(days):
    return ''.join(
        f'<li><span class="time">{day.day}日</span>'
        '<span class="wea">多云</span><span class="tem">28℃/19℃</span>'
        '<span class="wind">北风转南风</span><span class="wind1">&lt;3级</span></li>'
        for day in days
    )


@pytest.mark.parametrize('reference', [date(2026, 9, 11), date(2026, 9, 27), date(2026, 12, 27)])
def test_extended_forecast_keeps_all_eight_dates_across_month_and_year(reference):
    expected = [reference + timedelta(days=i) for i in range(7, 15)]
    rows = parse_daily_forecast_page(page_for(expected), reference)
    assert [row.forecast_date for row in rows] == expected
    assert all(row.temp_max == 28 and row.temp_min == 19 for row in rows)
    assert all(row.wind_direction_day == '北风转南风' for row in rows)


def test_stale_yesterday_and_day_sixteen_are_not_rolled_into_forecast():
    reference = date(2026, 9, 11)
    dates = [reference - timedelta(days=1), reference, reference + timedelta(days=14), reference + timedelta(days=15)]
    rows = parse_daily_forecast_page(page_for(dates), reference)
    assert [row.forecast_date for row in rows] == [reference, reference + timedelta(days=14)]
