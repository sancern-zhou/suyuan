"""Fetch Xuchang daily forecasts from weather.com.cn (1-15 days)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

import pyodbc
import requests
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client

logger = structlog.get_logger()

WEATHER_7D_URL = "https://www.weather.com.cn/weather/101180401.shtml"
WEATHER_15D_URL = "https://www.weather.com.cn/weather15d/101180401.shtml"
# 101180401 is the weather.com.cn code for Xuchang urban area (城区).
CITY_CODE = "101180401"
CITY_NAME = "许昌市"


@dataclass(frozen=True)
class DailyForecast:
    forecast_date: date
    date_label: str
    weather_text: str | None
    temp_max: float | None
    temp_min: float | None
    wind_direction_day: str | None
    wind_direction_night: str | None
    wind_force: str | None
    source_update_time: str | None

    def to_record(self, fetched_at: datetime) -> dict[str, Any]:
        return {
            "city_code": CITY_CODE, "city_name": CITY_NAME,
            "forecast_date": self.forecast_date, "date_label": self.date_label,
            "weather_text": self.weather_text, "temp_max": self.temp_max,
            "temp_min": self.temp_min, "wind_direction_day": self.wind_direction_day,
            "wind_direction_night": self.wind_direction_night, "wind_force": self.wind_force,
            "source_update_time": self.source_update_time, "fetched_at": fetched_at,
        }


_LI_RE = re.compile(r"<li(?:\s[^>]*)?>(?P<body>.*?)</li>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_DATE_RE = re.compile(r"(?P<day>\d{1,2})日")
_TEMP_RE = re.compile(r"(?P<max>-?\d+(?:\.\d+)?)\s*(?:℃|°C)?\s*/\s*(?P<min>-?\d+(?:\.\d+)?)")


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", value))).strip()


def _attr_text(body: str, tag_class: str) -> list[str]:
    pattern = re.compile(rf'<span[^>]*class=["\'][^"\']*\b{tag_class}\b[^"\']*["\'][^>]*>(.*?)</span>', re.I | re.S)
    return [_text(match) for match in pattern.findall(body)]


def _parse_date(label: str, reference: date) -> date | None:
    match = _DATE_RE.search(label)
    if not match:
        return None
    day = int(match.group("day"))
    for offset in range(0, 370):
        candidate = reference + timedelta(days=offset)
        if candidate.day == day:
            return candidate
    return None


def parse_daily_forecast_page(page: str, reference: date, source_update_time: str | None = None) -> list[DailyForecast]:
    """Parse either weather.com.cn 7-day or 15-day forecast HTML."""
    rows: list[DailyForecast] = []
    for match in _LI_RE.finditer(page):
        body = match.group("body")
        label_match = re.search(r"<(?:h1|span)[^>]*class=[\"'](?:time|date)[\"'][^>]*>(.*?)</(?:h1|span)>", body, re.I | re.S)
        if not label_match:
            label_match = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.I | re.S)
        if not label_match:
            continue
        label = _text(label_match.group(1))
        forecast_date = _parse_date(label, reference)
        if forecast_date is None:
            continue
        weather_match = re.search(r"<(?:p|span)[^>]*class=[\"'][^\"']*\bwea\b[^\"']*[\"'][^>]*>(.*?)</(?:p|span)>", body, re.I | re.S)
        temp_html = re.search(r"<(?:p|span)[^>]*class=[\"'][^\"']*\btem\b[^\"']*[\"'][^>]*>(.*?)</(?:p|span)>", body, re.I | re.S)
        temp_match = _TEMP_RE.search(_text(temp_html.group(1)) if temp_html else "")
        if temp_match is None and temp_html:
            temp_match = re.search(r"(?P<max>-?\d+(?:\.\d+)?)\s*/\s*(?P<min>-?\d+(?:\.\d+)?)", _text(temp_html.group(1)))
        if temp_match is None:
            temp_match = re.search(r"<span>\s*(?P<max>-?\d+(?:\.\d+)?)\s*</span>\s*/\s*<i>\s*(?P<min>-?\d+(?:\.\d+)?)", body, re.I | re.S)
        wind_titles = re.findall(r'<span[^>]*title=["\']([^"\']+)["\'][^>]*class=["\'][^"\']+["\']', body, re.I)
        force_match = re.search(r'class=["\'][^"\']*wind1[^"\']*["\'][^>]*>(.*?)</(?:i|span)>', body, re.I | re.S)
        if not force_match:
            force_match = re.search(r'<i[^>]*>(?P<value>.*?(?:级|风).*?)</i>', body, re.I | re.S)
        force_value = None
        raw_force = force_match.group(1) if force_match else ""
        force_value_match = re.search(r"<?\s*\d+(?:-\d+)?级(?:\s*转\s*<?\s*\d+(?:-\d+)?级)?", raw_force)
        if force_value_match:
            force_value = re.sub(r"\s+", "", force_value_match.group(0))
        rows.append(DailyForecast(
            forecast_date=forecast_date, date_label=label,
            weather_text=_text(weather_match.group(1)) if weather_match else None,
            temp_max=float(temp_match.group("max")) if temp_match else None,
            temp_min=float(temp_match.group("min")) if temp_match else None,
            wind_direction_day=wind_titles[0] if wind_titles else (_text(re.search(r'<(?:span|p)[^>]*class=["\'][^"\']*\bwind\b[^"\']*["\'][^>]*>(.*?)</(?:span|p)>', body, re.I | re.S).group(1)) if re.search(r'class=["\'][^"\']*\bwind\b', body, re.I) else None),
            wind_direction_night=wind_titles[1] if len(wind_titles) > 1 else None,
            wind_force=force_value,
            source_update_time=source_update_time,
        ))
    return rows


class WeatherComClient:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/html"})

    def fetch(self, url: str) -> str:
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text


class XuchangWeatherComDailyForecastStorage:
    table_name = "XuchangWeatherComDailyForecast"

    def __init__(self):
        self.sql_client = get_sql_server_client()

    def save(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        columns = ("city_code", "city_name", "forecast_date", "date_label", "weather_text", "temp_max", "temp_min", "wind_direction_day", "wind_direction_night", "wind_force", "source_update_time", "fetched_at")
        update = [c for c in columns if c not in {"city_code", "forecast_date"}]
        sql = f"""MERGE dbo.{self.table_name} AS target USING (SELECT ? AS city_code, ? AS forecast_date) AS source
        ON target.city_code=source.city_code AND target.forecast_date=source.forecast_date
        WHEN MATCHED THEN UPDATE SET {', '.join(f'target.{c}=?' for c in update)}, updated_at=SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)});"""
        values = [(r["city_code"], r["forecast_date"], *[r[c] for c in update], *[r[c] for c in columns]) for r in records]
        conn = pyodbc.connect(self.sql_client.connection_string, timeout=30)
        cursor = conn.cursor()
        try:
            cursor.execute(f"""IF OBJECT_ID(N'dbo.{self.table_name}', N'U') IS NULL CREATE TABLE dbo.{self.table_name} (
                id BIGINT IDENTITY(1,1) PRIMARY KEY, city_code NVARCHAR(20) NOT NULL, city_name NVARCHAR(32) NOT NULL,
                forecast_date DATE NOT NULL, date_label NVARCHAR(32) NULL, weather_text NVARCHAR(64) NULL,
                temp_max FLOAT NULL, temp_min FLOAT NULL, wind_direction_day NVARCHAR(32) NULL,
                wind_direction_night NVARCHAR(32) NULL, wind_force NVARCHAR(32) NULL, source_update_time NVARCHAR(32) NULL,
                fetched_at DATETIME2 NOT NULL, created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(), updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
                CONSTRAINT UX_{self.table_name}_CityDate UNIQUE (city_code, forecast_date));""")
            cursor.fast_executemany = True
            cursor.executemany(sql, values)
            conn.commit()
            return len(values)
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close(); conn.close()


class XuchangWeatherComDailyForecastFetcher(DataFetcher):
    def __init__(self, client: WeatherComClient | None = None, storage: XuchangWeatherComDailyForecastStorage | None = None, now_factory: Callable[[], datetime] = datetime.now):
        super().__init__(name="xuchang_weather_com_daily_forecast_fetcher", description="中国天气网许昌未来1-15天日气象预报抓取", schedule="20 6 * * *", version="1.0.0")
        self.client = client or WeatherComClient(); self.storage = storage or XuchangWeatherComDailyForecastStorage(); self.now_factory = now_factory

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory().replace(microsecond=0); reference = now.date()
        page7, page15 = self.client.fetch(WEATHER_7D_URL), self.client.fetch(WEATHER_15D_URL)
        rows = parse_daily_forecast_page(page7, reference) + parse_daily_forecast_page(page15, reference)
        unique = {row.forecast_date: row for row in rows}
        records = [row.to_record(now) for row in sorted(unique.values(), key=lambda r: r.forecast_date)[:15]]
        if not records: raise ValueError("weather.com.cn returned no Xuchang daily forecast rows")
        saved = self.storage.save(records)
        return {"city": CITY_NAME, "fetched": len(records), "saved": saved, "first_date": records[0]["forecast_date"].isoformat(), "last_date": records[-1]["forecast_date"].isoformat()}
