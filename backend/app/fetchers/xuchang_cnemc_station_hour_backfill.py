"""Backfill Xuchang CNEMC station hours from the quotsoft daily archive."""

from __future__ import annotations

import argparse
import csv
import io
import json
import threading
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pyodbc
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.integrations.xcai_station_sql import xcai_connection_string

CNEMC_LIVE_URL = "https://air.cnemc.cn:18007/CityData/GetAQIDataPublishLive"
XUCHANG_CITY_NAME = "许昌市"
XUCHANG_CITY_AREA_CODE = "411000"
MISSING_VALUE = -99
ARCHIVE_URL_TEMPLATE = "https://quotsoft.net/air/data/china_sites_{date}.csv"
ARCHIVE_TYPES = {
    "AQI": "aqi",
    "PM10": "pm10",
    "PM2.5": "pm25",
    "NO2": "no2",
    "SO2": "so2",
    "CO": "co",
    "O3": "o3",
}
NUMERIC_FIELDS = ("aqi", "pm10", "pm25", "no2", "so2", "co", "o3")


@dataclass(frozen=True)
class StationMetadata:
    station_id: str
    name: str
    lon: float
    lat: float


# These four stations cover the 2024-2025 archive. Current live metadata is
# merged at runtime so newly published stations are picked up automatically.
HISTORICAL_XUCHANG_STATIONS = {
    "2398A": StationMetadata("2398A", "开发区", 113.7904, 33.9949),
    "3134A": StationMetadata("3134A", "市一中", 113.8172, 34.0339),
    "3337A": StationMetadata("3337A", "许昌学院", 113.8611, 34.0443),
    "3338A": StationMetadata("3338A", "芙蓉广场", 113.8428, 34.0825),
}


def _number(value: Any) -> float | int | None:
    if value in (None, "", "NA", "—", "-"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=0,
        connect=0,
        read=0,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update(
        {
            "User-Agent": "suyuan-xuchang-history-backfill/1.0",
            "Accept": "text/csv,application/octet-stream,*/*",
        }
    )
    return session


def load_station_metadata(session: requests.Session | None = None) -> dict[str, StationMetadata]:
    """Merge stable historical stations with the current official live list."""
    stations = dict(HISTORICAL_XUCHANG_STATIONS)
    client = session or _session()
    try:
        response = client.get(CNEMC_LIVE_URL, params={"cityName": XUCHANG_CITY_NAME}, timeout=30)
        response.raise_for_status()
        rows = response.json()
    except (requests.RequestException, ValueError):
        return stations

    if not isinstance(rows, list):
        return stations
    for row in rows:
        station_id = str(row.get("StationCode") or "").strip()
        lon = _number(row.get("Longitude"))
        lat = _number(row.get("Latitude"))
        if not station_id or lon is None or lat is None:
            continue
        stations[station_id] = StationMetadata(
            station_id=station_id,
            name=str(row.get("PositionName") or station_id).strip(),
            lon=float(lon),
            lat=float(lat),
        )
    return stations


def aqi_level(aqi: int | float | None) -> str | None:
    if aqi is None or aqi < 0:
        return None
    for upper, label in ((50, "优"), (100, "良"), (150, "轻度污染"), (200, "中度污染"), (300, "重度污染")):
        if aqi <= upper:
            return label
    return "严重污染"


def parse_archive_csv(
    content: bytes,
    stations: dict[str, StationMetadata],
) -> tuple[list[dict[str, Any]], set[str]]:
    """Pivot a daily wide archive CSV into dat_station_hour records."""
    reader = csv.reader(io.StringIO(content.decode("utf-8-sig")))
    try:
        header = next(reader)
    except StopIteration:
        return [], set()
    if len(header) < 4 or header[:3] != ["date", "hour", "type"]:
        raise ValueError("archive CSV has an unexpected header")

    station_columns = {
        index: stations[station_id]
        for index, station_id in enumerate(header)
        if station_id in stations
    }
    records: dict[tuple[datetime, str], dict[str, Any]] = {}
    archive_station_ids = {metadata.station_id for metadata in station_columns.values()}

    for row in reader:
        if len(row) < 3 or row[2] not in ARCHIVE_TYPES:
            continue
        try:
            timestamp = datetime.strptime(row[0], "%Y%m%d") + timedelta(hours=int(row[1]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"archive CSV has an invalid date/hour row: {row[:3]}") from exc
        field = ARCHIVE_TYPES[row[2]]
        for index, metadata in station_columns.items():
            key = (timestamp, metadata.station_id)
            record = records.setdefault(
                key,
                {
                    "station_id": metadata.station_id,
                    "name": metadata.name,
                    "lon": metadata.lon,
                    "lat": metadata.lat,
                    **{numeric_field: MISSING_VALUE for numeric_field in NUMERIC_FIELDS},
                    "aqi_level": None,
                    "pollutant": None,
                    "data_time": timestamp,
                    "city_area_code": XUCHANG_CITY_AREA_CODE,
                },
            )
            value = _number(row[index]) if index < len(row) else None
            record[field] = value if value is not None else MISSING_VALUE

    result = sorted(records.values(), key=lambda item: (item["data_time"], item["station_id"]))
    for record in result:
        record["aqi_level"] = aqi_level(record["aqi"])
        record["co"] = float(record["co"])
    return result, archive_station_ids


class ArchiveClient:
    def __init__(self) -> None:
        self._local = threading.local()

    def _client(self) -> requests.Session:
        if not hasattr(self._local, "session"):
            self._local.session = _session()
        return self._local.session

    def fetch_day(self, target_date: date) -> tuple[date, bytes | None, str | None]:
        url = ARCHIVE_URL_TEMPLATE.format(date=target_date.strftime("%Y%m%d"))
        try:
            response = self._client().get(url, timeout=(10, 60))
            if response.status_code == 404:
                return target_date, None, "not_found"
            response.raise_for_status()
            return target_date, response.content, None
        except requests.RequestException as exc:
            return target_date, None, str(exc)


def insert_missing_records(cursor: pyodbc.Cursor, records: Sequence[dict[str, Any]]) -> int:
    """Insert only absent station/time keys, preserving official live rows."""
    if not records:
        return 0
    cursor.execute(
        """
        CREATE TABLE #xuchang_station_backfill (
            station_id nvarchar(50) NOT NULL,
            name nvarchar(100) NOT NULL,
            lon float NOT NULL,
            lat float NOT NULL,
            aqi int NOT NULL,
            aqi_level nvarchar(50) NULL,
            pm10 int NOT NULL,
            pm25 int NOT NULL,
            no2 int NOT NULL,
            so2 int NOT NULL,
            co float NOT NULL,
            o3 int NOT NULL,
            pollutant nvarchar(255) NULL,
            data_time datetime NOT NULL,
            city_area_code nvarchar(50) NOT NULL,
            PRIMARY KEY (station_id, data_time)
        )
        """
    )
    cursor.executemany(
        """
        INSERT INTO #xuchang_station_backfill
            (station_id, name, lon, lat, aqi, aqi_level, pm10, pm25, no2, so2,
             co, o3, pollutant, data_time, city_area_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                record["station_id"], record["name"], record["lon"], record["lat"],
                record["aqi"], record["aqi_level"], record["pm10"], record["pm25"],
                record["no2"], record["so2"], record["co"], record["o3"],
                record["pollutant"], record["data_time"], record["city_area_code"],
            )
            for record in records
        ],
    )
    cursor.execute(
        """
        MERGE dbo.dat_station_hour WITH (HOLDLOCK) AS target
        USING #xuchang_station_backfill AS source
          ON target.station_id = source.station_id
         AND target.data_time = source.data_time
        WHEN NOT MATCHED THEN INSERT
          (station_id, name, lon, lat, aqi, aqi_level, pm10, pm25, no2, so2,
           co, o3, pollutant, data_time, city_area_code, CreateTime)
        VALUES
          (source.station_id, source.name, source.lon, source.lat, source.aqi,
           source.aqi_level, source.pm10, source.pm25, source.no2, source.so2,
           source.co, source.o3, source.pollutant, source.data_time,
           source.city_area_code, GETDATE())
        OUTPUT $action AS merge_action;
        """
    )
    inserted = sum(1 for row in cursor.fetchall() if str(row[0]).upper() == "INSERT")
    cursor.execute("DROP TABLE #xuchang_station_backfill")
    return inserted


def _dates(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _batches(values: Sequence[date], size: int = 31) -> Iterable[Sequence[date]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def load_complete_dates(connection: pyodbc.Connection, start: date, end: date) -> set[date]:
    """Return days already containing all 24 hours for the four historical stations."""
    station_ids = sorted(HISTORICAL_XUCHANG_STATIONS)
    placeholders = ",".join("?" for _ in station_ids)
    cursor = connection.cursor()
    cursor.execute(
        f"""
        SELECT CAST(data_time AS date) AS data_date
        FROM dbo.dat_station_hour
        WHERE city_area_code = ?
          AND station_id IN ({placeholders})
          AND data_time >= ?
          AND data_time < DATEADD(day, 1, ?)
        GROUP BY CAST(data_time AS date)
        HAVING COUNT_BIG(*) >= ?
        """,
        [XUCHANG_CITY_AREA_CODE, *station_ids, start, end, 24 * len(station_ids)],
    )
    return {row[0] for row in cursor.fetchall()}


def run_backfill(
    *,
    start: date,
    end: date,
    write: bool,
    workers: int = 4,
    progress: bool = False,
) -> dict[str, Any]:
    if end < start:
        raise ValueError("end date must not be before start date")
    stations = load_station_metadata()
    target_dates = list(_dates(start, end))
    archive_client = ArchiveClient()
    connection = pyodbc.connect(xcai_connection_string(), timeout=30) if write else None
    complete_dates = load_complete_dates(connection, start, end) if connection is not None else set()
    target_dates = [target_date for target_date in target_dates if target_date not in complete_dates]
    summary: dict[str, Any] = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "write": write,
        "days_requested": (end - start).days + 1,
        "days_skipped_complete": len(complete_dates),
        "days_downloaded": 0,
        "days_missing": [],
        "days_failed": [],
        "records_parsed": 0,
        "records_inserted": 0,
        "station_ids": [],
        "known_station_ids": sorted(stations),
    }
    seen_station_ids: set[str] = set()
    try:
        days_processed = len(complete_dates)
        for batch in _batches(target_dates, size=max(workers * 2, 1)):
            parsed_batch: list[dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = executor.map(archive_client.fetch_day, batch)
                for target_date, content, error in results:
                    if content is None:
                        key = "days_missing" if error == "not_found" else "days_failed"
                        summary[key].append({"date": target_date.isoformat(), "error": error})
                        continue
                    try:
                        records, archive_station_ids = parse_archive_csv(content, stations)
                    except (UnicodeDecodeError, ValueError) as exc:
                        summary["days_failed"].append(
                            {"date": target_date.isoformat(), "error": str(exc)}
                        )
                        continue
                    summary["days_downloaded"] += 1
                    summary["records_parsed"] += len(records)
                    seen_station_ids.update(archive_station_ids)
                    parsed_batch.extend(records)
            if write and parsed_batch:
                assert connection is not None
                cursor = connection.cursor()
                summary["records_inserted"] += insert_missing_records(cursor, parsed_batch)
                connection.commit()
            days_processed += len(batch)
            if progress:
                print(
                    json.dumps(
                        {
                            "progress": f"{days_processed}/{summary['days_requested']}",
                            "days_downloaded": summary["days_downloaded"],
                            "days_failed": len(summary["days_failed"]),
                            "records_inserted": summary["records_inserted"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()
    summary["station_ids"] = sorted(seen_station_ids)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回补许昌国控站历史小时发布数据")
    parser.add_argument("--years", nargs="+", type=int, help="年份，例如 --years 2024 2025 2026")
    parser.add_argument("--start", type=date.fromisoformat, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 17))
    parser.add_argument("--write", action="store_true", help="写入数据库；默认仅解析校验")
    args = parser.parse_args()
    if args.years and (args.start or args.end):
        parser.error("--years 不能与 --start/--end 同时使用")
    if args.years:
        args.start = date(min(args.years), 1, 1)
        args.end = min(date(max(args.years), 12, 31), date.today() - timedelta(days=1))
    elif not args.start or not args.end:
        parser.error("请提供 --years，或同时提供 --start 和 --end")
    return args


def main() -> None:
    args = _parse_args()
    result = run_backfill(
        start=args.start,
        end=args.end,
        write=args.write,
        workers=args.workers,
        progress=True,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
