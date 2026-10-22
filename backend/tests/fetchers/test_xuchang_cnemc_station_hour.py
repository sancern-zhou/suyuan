from datetime import datetime

import pytest

from app.fetchers.xuchang_cnemc_station_hour import (
    MISSING_VALUE,
    XuchangCnemcStationHourFetcher,
)


def _source_row(**updates):
    row = {
        "StationCode": "2398A",
        "PositionName": "开发区",
        "Longitude": "113.7904",
        "Latitude": "33.9949",
        "TimePoint": "2026-08-24T23:00:00",
        "AQI": "80",
        "Quality": "良",
        "PM10_24h": "68",
        "PM2_5_24h": "76",
        "NO2_24h": "31",
        "SO2_24h": "8",
        "CO_24h": "0.7",
        "O3_24h": "120",
        "O3_8h_24h": "168",
        "PrimaryPollutant": "细颗粒物(PM2.5)",
    }
    row.update(updates)
    return row


def test_day_record_uses_source_published_daily_metrics():
    record = XuchangCnemcStationHourFetcher._day_record(_source_row())

    assert record is not None
    assert record["data_time"] == datetime(2026, 8, 24)
    assert record["pm25"] == 76
    assert record["o3_8h"] == 168
    assert record["co"] == 0.7


def test_day_record_preserves_missing_source_value_without_calculation():
    record = XuchangCnemcStationHourFetcher._day_record(
        _source_row(PM2_5_24h=None, O3_8h_24h="")
    )

    assert record is not None
    assert record["pm25"] == MISSING_VALUE
    assert record["o3_8h"] == MISSING_VALUE


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return [_source_row()]


class _Session:
    def __init__(self):
        self.headers = {}

    def get(self, *args, **kwargs):
        return _Response()


class _Cursor:
    def __init__(self):
        self.statements = []

    def execute(self, statement, *args):
        self.statements.append(statement)


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_fetcher_persists_hour_and_published_day_rows(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(
        "app.fetchers.xuchang_cnemc_station_hour.pyodbc.connect",
        lambda *args, **kwargs: connection,
    )
    fetcher = XuchangCnemcStationHourFetcher(session=_Session())

    result = await fetcher.fetch_and_store()

    assert result["saved"] == 1
    assert result["daily_saved"] == 1
    assert any("dbo.dat_station_hour" in statement for statement in connection.cursor_instance.statements)
    assert any("dbo.dat_station_day" in statement for statement in connection.cursor_instance.statements)
    assert connection.committed is True
    assert connection.closed is True
