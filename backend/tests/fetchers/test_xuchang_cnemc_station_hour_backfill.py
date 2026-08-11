from datetime import datetime

from app.fetchers.xuchang_cnemc_station_hour_backfill import (
    MISSING_VALUE,
    StationMetadata,
    aqi_level,
    insert_missing_records,
    load_complete_dates,
    parse_archive_csv,
)


def test_parse_archive_csv_pivots_only_xuchang_stations() -> None:
    content = b"""date,hour,type,2398A,3134A,1001A\n20240101,0,AQI,51,,99\n20240101,0,PM2.5,35,12,88\n20240101,0,PM10,50,21,77\n20240101,0,NO2,18,9,66\n20240101,0,SO2,6,4,55\n20240101,0,CO,0.7,0.3,44\n20240101,0,O3,80,91,33\n"""
    stations = {
        "2398A": StationMetadata("2398A", "开发区", 113.7904, 33.9949),
        "3134A": StationMetadata("3134A", "市一中", 113.8172, 34.0339),
    }

    records, station_ids = parse_archive_csv(content, stations)

    assert station_ids == {"2398A", "3134A"}
    assert len(records) == 2
    assert records[0] == {
        "station_id": "2398A",
        "name": "开发区",
        "lon": 113.7904,
        "lat": 33.9949,
        "aqi": 51,
        "pm10": 50,
        "pm25": 35,
        "no2": 18,
        "so2": 6,
        "co": 0.7,
        "o3": 80,
        "aqi_level": "良",
        "pollutant": None,
        "data_time": datetime(2024, 1, 1),
        "city_area_code": "411000",
    }
    assert records[1]["aqi"] == MISSING_VALUE
    assert records[1]["aqi_level"] is None


def test_parse_archive_csv_accepts_station_set_changes() -> None:
    content = b"""date,hour,type,3338A,4180A,4259A\n20260808,23,AQI,40,42,43\n20260808,23,PM2.5,10,11,12\n"""
    stations = {
        code: StationMetadata(code, code, 113.8, 34.0)
        for code in ("3338A", "4180A", "4259A")
    }

    records, station_ids = parse_archive_csv(content, stations)

    assert station_ids == {"3338A", "4180A", "4259A"}
    assert [record["station_id"] for record in records] == ["3338A", "4180A", "4259A"]
    assert all(record["data_time"] == datetime(2026, 8, 8, 23) for record in records)


def test_aqi_level_boundaries() -> None:
    assert aqi_level(-99) is None
    assert aqi_level(50) == "优"
    assert aqi_level(51) == "良"
    assert aqi_level(300) == "重度污染"
    assert aqi_level(301) == "严重污染"


class FakeCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.rows = []
        self.rowcount = 1
        self._results = []

    def execute(self, sql: str, *params) -> None:
        self.statements.append(sql)
        self._results = [("INSERT",)] if "OUTPUT $action" in sql else []

    def executemany(self, sql: str, rows) -> None:
        self.statements.append(sql)
        self.rows = list(rows)

    def fetchall(self):
        return self._results


def test_insert_missing_records_uses_insert_only_merge() -> None:
    cursor = FakeCursor()
    record = {
        "station_id": "2398A", "name": "开发区", "lon": 113.7, "lat": 33.9,
        "aqi": 50, "aqi_level": "优", "pm10": 40, "pm25": 20,
        "no2": 10, "so2": 5, "co": 0.4, "o3": 80, "pollutant": None,
        "data_time": datetime(2024, 1, 1), "city_area_code": "411000",
    }

    inserted = insert_missing_records(cursor, [record])

    merge = next(statement for statement in cursor.statements if "MERGE dbo.dat_station_hour" in statement)
    assert inserted == 1
    assert "WHEN NOT MATCHED THEN INSERT" in merge
    assert "WHEN MATCHED" not in merge
    assert cursor.rows[0][0] == "2398A"


def test_load_complete_dates_uses_four_station_day_threshold() -> None:
    class QueryCursor:
        def __init__(self):
            self.statements = []

        def execute(self, sql, params):
            self.statements.append(sql)

        def fetchall(self):
            return [(datetime(2024, 1, 1).date(),)]

    class Connection:
        def cursor(self):
            return cursor

    cursor = QueryCursor()

    result = load_complete_dates(Connection(), datetime(2024, 1, 1).date(), datetime(2024, 1, 2).date())

    assert result == {datetime(2024, 1, 1).date()}
    assert "HAVING COUNT_BIG(*) >= ?" in cursor.statements[0]
