"""Fetch NMC hourly weather forecasts for Xuchang from the public forecast page."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

import pyodbc
import requests
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client

logger = structlog.get_logger()

NMC_XUCHANG_FORECAST_PAGE = "https://www.nmc.cn/publish/forecast/AHA/xuchang.html"
XUCHANG_CITY_NAME = "许昌市"
XUCHANG_CITY_CODE = "411000"
NMC_ICON_SENTINEL = 9999

_STATION_ID_PATTERN = re.compile(
    r'<input[^>]*name=["\']?stationId["\']?[^>]*value=["\']?(?P<station_id>[A-Za-z0-9]+)',
    re.IGNORECASE,
)
_PAGE_TIME_PATTERN = re.compile(
    r'<input[^>]*name=["\']?页面生成时间["\']?[^>]*value=["\']?(?P<page_time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',
)
_HOUR3_OPEN_PATTERN = re.compile(r'<div class="hour3[^"]*">')
_DAY_BLOCK_OPEN_PATTERN = re.compile(r"<div id=day\d")
_INNER_TEXT_PATTERN = re.compile(r"<div[^>]*>([^<]*)</div>")
_IMAGE_PATTERN = re.compile(r'<img[^>]*src=["\']?(?P<url>[^"\'\s>]+)')
_DAY_PREFIX_TIME_PATTERN = re.compile(r"^(?P<day>\d{1,2})日(?P<hour>\d{1,2}):(?P<minute>\d{2})$")
_PLAIN_TIME_PATTERN = re.compile(r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})$")

NMC_WEATHER_TEXT = {
    0: "晴",
    1: "多云",
    2: "阴",
    3: "阵雨",
    4: "雷阵雨",
    5: "雷阵雨伴有冰雹",
    6: "雨夹雪",
    7: "小雨",
    8: "中雨",
    9: "大雨",
    10: "暴雨",
    11: "大暴雨",
    12: "特大暴雨",
    13: "阵雪",
    14: "小雪",
    15: "中雪",
    16: "大雪",
    17: "暴雪",
    18: "雾",
    19: "冻雨",
    20: "沙尘暴",
    21: "小到中雨",
    22: "中到大雨",
    23: "大到暴雨",
    24: "暴雨到大暴雨",
    25: "大暴雨到特大暴雨",
    26: "小到中雪",
    27: "中到大雪",
    28: "大到暴雪",
    29: "浮尘",
    30: "扬沙",
    31: "强沙尘暴",
    53: "霾",
    99: "无",
}

WIND_DIRECTION_DEGREES = {
    "北": 0.0,
    "东北": 45.0,
    "东": 90.0,
    "东南": 135.0,
    "南": 180.0,
    "西南": 225.0,
    "西": 270.0,
    "西北": 315.0,
}


def _first_of_next_month(anchor: date) -> date:
    if anchor.month == 12:
        return anchor.replace(year=anchor.year + 1, month=1, day=1)
    return anchor.replace(month=anchor.month + 1, day=1)


def _parse_page_time(html: str, now_factory: Callable[[], datetime]) -> datetime:
    match = _PAGE_TIME_PATTERN.search(html)
    if not match:
        return now_factory()
    try:
        return datetime.strptime(match.group("page_time"), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return now_factory()


def _parse_station_id(html: str) -> str:
    match = _STATION_ID_PATTERN.search(html)
    if not match:
        raise ValueError("NMC Xuchang forecast page is missing the stationId input")
    return match.group("station_id")


def _iter_hour3_segments(html: str) -> list[str]:
    """Return the raw inner HTML of each hourly forecast block, in page order."""
    markers = sorted(
        [
            *((match.start(), match.end()) for match in _HOUR3_OPEN_PATTERN.finditer(html)),
            *((match.start(), match.end()) for match in _DAY_BLOCK_OPEN_PATTERN.finditer(html)),
        ],
        key=lambda item: item[0],
    )
    segments: list[str] = []
    for index, (start, end) in enumerate(markers):
        if _HOUR3_OPEN_PATTERN.match(html, start) is None:
            continue
        segment_end = markers[index + 1][0] if index + 1 < len(markers) else len(html)
        segments.append(html[end:segment_end])
    return segments


def _resolve_forecast_datetime(
    text: str,
    cursor: date,
    previous: datetime,
) -> tuple[datetime, date]:
    """Resolve a page time label ("11:00" or "31日02:00") into an absolute datetime."""
    day_match = _DAY_PREFIX_TIME_PATTERN.match(text)
    if day_match:
        day = int(day_match.group("day"))
        month_anchor = cursor
        if day < month_anchor.day:
            month_anchor = _first_of_next_month(month_anchor)
        try:
            resolved_date = month_anchor.replace(day=day)
        except ValueError as exc:
            raise ValueError(f"Invalid NMC hourly forecast time label: {text}") from exc
        return (
            datetime.combine(
                resolved_date,
                time(int(day_match.group("hour")), int(day_match.group("minute"))),
            ),
            resolved_date,
        )

    plain_match = _PLAIN_TIME_PATTERN.match(text)
    if not plain_match:
        raise ValueError(f"Unrecognised NMC hourly forecast time label: {text}")
    candidate = datetime.combine(
        cursor,
        time(int(plain_match.group("hour")), int(plain_match.group("minute"))),
    )
    if candidate <= previous:
        candidate += timedelta(days=1)
    return candidate, candidate.date()


def _text_number(pattern: re.Pattern[str], texts: list[str]) -> float | None:
    for text in texts:
        match = pattern.search(text)
        if match:
            return float(match.group(1))
    return None


_TEMPERATURE_PATTERN = re.compile(r"^(-?[\d.]+)℃$")
_WIND_SPEED_PATTERN = re.compile(r"^([\d.]+)\s*m/s$")
_PRESSURE_PATTERN = re.compile(r"^([\d.]+)\s*hPa$")
_PERCENT_PATTERN = re.compile(r"^([\d.]+)%$")


@dataclass(frozen=True)
class NMCHourlyForecastRow:
    station_id: str
    city_code: str
    city_name: str
    forecast_time: datetime
    publish_time: datetime
    temperature: float | None
    humidity: float | None
    pressure: float | None
    wind_speed: float | None
    wind_direction: str | None
    wind_direction_degrees: float | None
    precipitation_probability: float | None
    precipitation_text: str | None
    weather_code: int | None
    weather_text: str | None
    weather_icon_url: str | None

    def to_record(self, fetched_at: datetime) -> dict[str, Any]:
        return {
            "station_id": self.station_id,
            "city_code": self.city_code,
            "city_name": self.city_name,
            "forecast_time": self.forecast_time,
            "publish_time": self.publish_time,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "pressure": self.pressure,
            "wind_speed": self.wind_speed,
            "wind_direction": self.wind_direction,
            "wind_direction_degrees": self.wind_direction_degrees,
            "precipitation_probability": self.precipitation_probability,
            "precipitation_text": self.precipitation_text,
            "weather_code": self.weather_code,
            "weather_text": self.weather_text,
            "weather_icon_url": self.weather_icon_url,
            "fetched_at": fetched_at,
        }


def parse_nmc_hourly_forecast(
    html: str,
    now_factory: Callable[[], datetime] = datetime.now,
) -> list[NMCHourlyForecastRow]:
    """Parse the server-rendered 3-hourly forecast blocks from the NMC city page."""
    station_id = _parse_station_id(html)
    publish_time = _parse_page_time(html, now_factory)
    rows: list[NMCHourlyForecastRow] = []
    cursor = publish_time.date()
    previous = publish_time

    for segment in _iter_hour3_segments(html):
        texts = [text.strip() for text in _INNER_TEXT_PATTERN.findall(segment)]
        if not texts:
            continue
        try:
            forecast_time, cursor = _resolve_forecast_datetime(texts[0], cursor, previous)
        except ValueError:
            continue
        previous = forecast_time

        image_match = _IMAGE_PATTERN.search(segment)
        weather_icon_url = image_match.group("url") if image_match else None
        weather_code: int | None = None
        if weather_icon_url:
            code_match = re.search(r"/(\d+)\.(?:png|gif|jpg)$", weather_icon_url, re.IGNORECASE)
            if code_match and int(code_match.group(1)) != NMC_ICON_SENTINEL:
                weather_code = int(code_match.group(1))

        percent_values = [
            float(match.group(1)) for text in texts if (match := _PERCENT_PATTERN.match(text))
        ]
        direction = next((text for text in texts if text.endswith("风")), None)

        rows.append(
            NMCHourlyForecastRow(
                station_id=station_id,
                city_code=XUCHANG_CITY_CODE,
                city_name=XUCHANG_CITY_NAME,
                forecast_time=forecast_time,
                publish_time=publish_time,
                temperature=_text_number(_TEMPERATURE_PATTERN, texts),
                humidity=percent_values[0] if percent_values else None,
                pressure=_text_number(_PRESSURE_PATTERN, texts),
                wind_speed=_text_number(_WIND_SPEED_PATTERN, texts),
                wind_direction=direction,
                wind_direction_degrees=(
                    WIND_DIRECTION_DEGREES.get(direction.replace("风", "")) if direction else None
                ),
                precipitation_probability=percent_values[1] if len(percent_values) > 1 else None,
                precipitation_text=(
                    texts[1] if len(texts) > 1 and texts[1] and texts[1] != "-" else None
                ),
                weather_code=weather_code,
                weather_text=NMC_WEATHER_TEXT.get(weather_code)
                if weather_code is not None
                else None,
                weather_icon_url=weather_icon_url,
            )
        )

    return rows


class NMCXuchangHourlyForecastClient:
    def __init__(
        self,
        page_url: str = NMC_XUCHANG_FORECAST_PAGE,
        session: requests.Session | None = None,
    ) -> None:
        self.page_url = page_url
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def fetch_page(self) -> str:
        response = self.session.get(self.page_url, timeout=30)
        response.raise_for_status()
        # NMC omits the charset in Content-Type; requests would otherwise fall
        # back to ISO-8859-1 and mojibake the ℃/风向 labels used for parsing.
        response.encoding = "utf-8"
        return response.text


class XuchangNmcHourlyForecastStorage:
    """Store NMC hourly forecast rows in SQL Server with upsert semantics."""

    table_name = "XuchangNmcHourlyWeatherForecast"

    def __init__(self) -> None:
        self.sql_client = get_sql_server_client()

    def ensure_table(self, cursor: pyodbc.Cursor) -> None:
        cursor.execute(
            f"""
            IF OBJECT_ID(N'dbo.{self.table_name}', N'U') IS NULL
            CREATE TABLE dbo.{self.table_name} (
                id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                station_id NVARCHAR(16) NOT NULL,
                city_code NVARCHAR(20) NOT NULL,
                city_name NVARCHAR(32) NOT NULL,
                forecast_time DATETIME2 NOT NULL,
                publish_time DATETIME2 NULL,
                temperature FLOAT NULL,
                humidity FLOAT NULL,
                pressure FLOAT NULL,
                wind_speed FLOAT NULL,
                wind_direction NVARCHAR(16) NULL,
                wind_direction_degrees FLOAT NULL,
                precipitation_probability FLOAT NULL,
                precipitation_text NVARCHAR(32) NULL,
                weather_code INT NULL,
                weather_text NVARCHAR(32) NULL,
                weather_icon_url NVARCHAR(255) NULL,
                source NVARCHAR(16) NOT NULL DEFAULT 'NMC',
                fetched_at DATETIME2 NOT NULL,
                created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
            );
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_{self.table_name}_StationForecastTime'
                AND object_id = OBJECT_ID(N'dbo.{self.table_name}'))
            CREATE UNIQUE INDEX UX_{self.table_name}_StationForecastTime
                ON dbo.{self.table_name} (station_id, forecast_time);
            """
        )

    def save(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        columns = (
            "station_id",
            "city_code",
            "city_name",
            "forecast_time",
            "publish_time",
            "temperature",
            "humidity",
            "pressure",
            "wind_speed",
            "wind_direction",
            "wind_direction_degrees",
            "precipitation_probability",
            "precipitation_text",
            "weather_code",
            "weather_text",
            "weather_icon_url",
            "fetched_at",
        )
        update_columns = [
            column for column in columns if column not in {"station_id", "forecast_time"}
        ]
        update_set = ", ".join(f"target.{column}=?" for column in update_columns)
        merge_sql = f"""
        MERGE dbo.{self.table_name} AS target
        USING (SELECT ? AS station_id, ? AS forecast_time) AS source
          ON target.station_id = source.station_id AND target.forecast_time = source.forecast_time
        WHEN MATCHED THEN UPDATE SET
          {update_set}, updated_at=SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (
            {", ".join(columns)}
        ) VALUES (
            {", ".join("?" for _ in columns)}
        );
        """
        rows = [
            (
                record["station_id"],
                record["forecast_time"],
                *[record[column] for column in update_columns],
                *[record[column] for column in columns],
            )
            for record in records
        ]
        conn = pyodbc.connect(self.sql_client.connection_string, timeout=30)
        cursor = conn.cursor()
        try:
            self.ensure_table(cursor)
            cursor.fast_executemany = True
            cursor.executemany(merge_sql, rows)
            conn.commit()
            return len(rows)
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()


class XuchangNmcHourlyForecastFetcher(DataFetcher):
    """Fetch and persist NMC 3-hourly weather forecasts for Xuchang."""

    def __init__(
        self,
        client: NMCXuchangHourlyForecastClient | None = None,
        storage: XuchangNmcHourlyForecastStorage | None = None,
        now_factory: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__(
            name="xuchang_nmc_hourly_forecast_fetcher",
            description="中央气象台许昌市小时（3小时间隔）天气预报抓取",
            schedule="40 * * * *",
            version="1.0.0",
        )
        self.client = client or NMCXuchangHourlyForecastClient()
        self.storage = storage or XuchangNmcHourlyForecastStorage()
        self.now_factory = now_factory

    async def fetch_and_store(self) -> dict[str, Any]:
        html = self.client.fetch_page()
        rows = parse_nmc_hourly_forecast(html, now_factory=self.now_factory)
        if not rows:
            raise ValueError("NMC Xuchang forecast page contained no hourly forecast rows")

        fetched_at = self.now_factory().replace(microsecond=0)
        records = [row.to_record(fetched_at) for row in rows]
        saved = self.storage.save(records)
        result = {
            "city": XUCHANG_CITY_NAME,
            "station_id": rows[0].station_id,
            "fetched": len(rows),
            "saved": saved,
            "first_forecast_time": rows[0].forecast_time.isoformat(),
            "last_forecast_time": rows[-1].forecast_time.isoformat(),
            "publish_time": rows[0].publish_time.isoformat(),
        }
        logger.info("xuchang_nmc_hourly_forecast_fetch_completed", **result)
        return result
