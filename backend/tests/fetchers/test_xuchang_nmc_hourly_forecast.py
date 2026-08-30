from datetime import datetime

import pytest

from app.fetchers.xuchang_nmc_hourly_forecast import (
    NMCXuchangHourlyForecastClient,
    XuchangNmcHourlyForecastFetcher,
    XuchangNmcHourlyForecastStorage,
    parse_nmc_hourly_forecast,
)

PAGE_HTML = """
<input type=hidden name="页面生成时间" value="2026-08-30 10:25:53">
<input type=hidden name=stationId value=ZzMTA>
<div class=values id=hourValues><div style="width:4704px;position: relative;">
<div id=day0 class="clearfix pull-left">
<div class="hour3 hbg"><div> 11:00 </div><div class=hourimg style="padding-top: 10px;"><img src="https://image.nmc.cn/assets/img/w/40x40/3/1.png"></div><div> - </div><div class=tmp_lte_30> 28.6℃ </div><div> 3.3m/s </div><div> 北风 </div><div class=hide> 1002.1hPa </div><div> 83% </div><div class=hide> 75.7% </div></div>
<div class="hour3 hbg"><div> 23:00 </div><div class=hourimg style="padding-top: 10px;"><img src="https://image.nmc.cn/assets/img/w/40x40/3/0.png"></div><div> - </div><div class=tmp_lte_25> 23.5℃ </div><div> 2.7m/s </div><div> 北风 </div><div class=hide> 1003hPa </div><div> 89.3% </div><div class=hide> 1.1% </div></div>
<div class="hour3 "><div> 31日02:00 </div><div class=hourimg style="padding-top: 10px;"><img src="https://image.nmc.cn/assets/img/w/40x40/3/2.png"></div><div> - </div><div class=tmp_lte_25> 22℃ </div><div> 2.4m/s </div><div> 东北风 </div><div class=hide> 1002.4hPa </div><div> 92.4% </div><div class=hide> 1.5% </div></div>
<div class="hour3 "><div> 05:00 </div><div class=hourimg style="padding-top: 10px;"><img src="https://image.nmc.cn/assets/img/w/40x40/3/2.png"></div><div> - </div><div class=tmp_lte_25> 21.2℃ </div><div> 2.6m/s </div><div> 旋转风 </div><div class=hide> 1001.5hPa </div><div> 96.5% </div><div class=hide> 0.3% </div></div>
</div>
<div id=day1 class="clearfix pull-left">
<div class="hour3 hbg"><div> 01日02:00 </div><div class=hourimg style="padding-top: 10px;"><img src="https://image.nmc.cn/assets/img/w/40x40/3/2.png"></div><div> - </div><div class=tmp_lte_25> 20.8℃ </div><div> 2m/s </div><div> 北风 </div><div class=hide> 1005.7hPa </div><div> 78.8% </div><div class=hide> 0% </div></div>
<div class="hour3 hbg"><div> 05:00 </div><div class=hourimg style="padding-top: 10px;"><img src="https://image.nmc.cn/assets/img/w/40x40/3/9999.png"></div><div> - </div><div class=tmp_lte_25> 19.5℃ </div><div> 3m/s </div><div> 北风 </div><div class=hide> 1007.1hPa </div><div> 89.1% </div><div class=hide> 10% </div></div>
</div>
</div></div>
"""


def test_parse_extracts_station_publish_time_and_rows():
    rows = parse_nmc_hourly_forecast(PAGE_HTML)

    assert len(rows) == 6
    assert all(row.station_id == "ZzMTA" for row in rows)
    assert rows[0].publish_time == datetime(2026, 8, 30, 10, 25, 53)


def test_parse_resolves_times_across_day_and_month_boundaries():
    rows = parse_nmc_hourly_forecast(PAGE_HTML)
    times = [row.forecast_time for row in rows]

    assert times == [
        datetime(2026, 8, 30, 11, 0),
        datetime(2026, 8, 30, 23, 0),
        datetime(2026, 8, 31, 2, 0),
        datetime(2026, 8, 31, 5, 0),
        datetime(2026, 9, 1, 2, 0),
        datetime(2026, 9, 1, 5, 0),
    ]


def test_parse_maps_weather_values():
    rows = parse_nmc_hourly_forecast(PAGE_HTML)
    first = rows[0]

    assert first.temperature == 28.6
    assert first.humidity == 83.0
    assert first.pressure == 1002.1
    assert first.wind_speed == 3.3
    assert first.wind_direction == "北风"
    assert first.wind_direction_degrees == 0.0
    assert first.precipitation_probability == 75.7
    assert first.precipitation_text is None
    assert first.weather_code == 1
    assert first.weather_text == "多云"
    assert first.weather_icon_url == "https://image.nmc.cn/assets/img/w/40x40/3/1.png"

    second = rows[1]
    assert second.weather_code == 0
    assert second.weather_text == "晴"

    third = rows[2]
    assert third.wind_direction == "东北风"
    assert third.wind_direction_degrees == 45.0

    rotating = rows[3]
    assert rotating.wind_direction == "旋转风"
    assert rotating.wind_direction_degrees is None

    sentinel = rows[5]
    assert sentinel.weather_code is None
    assert sentinel.weather_text is None
    assert sentinel.temperature == 19.5


class _Response:
    def __init__(self, text):
        self.encoding = "ISO-8859-1"
        self._content = text.encode("utf-8")

    def raise_for_status(self):
        return None

    @property
    def text(self):
        return self._content.decode(self.encoding)


class _Session:
    def __init__(self, text):
        self.headers = {}
        self._text = text

    def get(self, *args, **kwargs):
        return _Response(self._text)


def test_client_forces_utf8_decoding():
    client = NMCXuchangHourlyForecastClient(session=_Session(PAGE_HTML))

    html = client.fetch_page()

    assert "℃" in html
    rows = parse_nmc_hourly_forecast(html)
    assert rows[0].temperature == 28.6
    assert rows[0].wind_direction == "北风"


class _Cursor:
    def __init__(self):
        self.statements = []
        self.batches = []

    def execute(self, statement, *args):
        self.statements.append(statement)

    def executemany(self, statement, rows):
        self.statements.append(statement)
        self.batches.extend(rows)

    def close(self):
        return None


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_fetcher_parses_and_persists_hourly_forecast(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(
        "app.fetchers.xuchang_nmc_hourly_forecast.pyodbc.connect",
        lambda *args, **kwargs: connection,
    )
    fetcher = XuchangNmcHourlyForecastFetcher(
        client=NMCXuchangHourlyForecastClient(session=_Session(PAGE_HTML)),
    )

    result = await fetcher.fetch_and_store()

    assert result["station_id"] == "ZzMTA"
    assert result["fetched"] == 6
    assert result["saved"] == 6
    assert result["first_forecast_time"] == "2026-08-30T11:00:00"
    assert result["last_forecast_time"] == "2026-09-01T05:00:00"
    merge_statements = [
        statement
        for statement in connection.cursor_instance.statements
        if "MERGE dbo.XuchangNmcHourlyWeatherForecast" in statement
    ]
    assert merge_statements
    assert all(
        "UX_XuchangNmcHourlyWeatherForecast_StationForecastTime" in statement
        or "MERGE" in statement
        for statement in connection.cursor_instance.statements
    )
    assert len(connection.cursor_instance.batches) == 6
    assert connection.committed is True
    assert connection.closed is True


def test_storage_table_name_and_registration():
    assert XuchangNmcHourlyForecastStorage.table_name == "XuchangNmcHourlyWeatherForecast"
    fetcher = XuchangNmcHourlyForecastFetcher(
        client=NMCXuchangHourlyForecastClient(session=_Session(PAGE_HTML)),
    )
    assert fetcher.name == "xuchang_nmc_hourly_forecast_fetcher"
    assert fetcher.schedule == "40 * * * *"
