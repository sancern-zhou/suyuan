"""Fetch Henan city month/year cumulative air-quality rankings into SQL Server.

数据来源为河南省空气质量发布 APP (com.henan.agencyweibao) 的"空气质量"页接口,
覆盖河南省 17 省辖市 + 济源 + 航空港 + 市平均 + 省直管县 + 县平均:
  月累计: /hnAqi/v1.0/api/air/airreport2018?month=YYYY-MM
  年累计: /hnAqi/v1.0/api/air/airreport2018?start=YYYY-01-01&end=YYYY-MM-DD
入库 XcAiDb.dbo.HenanCityAccumulateRanking, 按 (period_type, period, city)
MERGE 整体替换当期数据(当月/当年文件每日运行时更新);
同时按期归档 JSON 便于前端直接读取。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pyodbc
import requests
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.xcai_station_sql import xcai_connection_string
from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

CITY_RANKING_URL = "http://1.192.88.18:8115/hnAqi/v1.0/api/air/airreport2018"
XUCHANG_CITY = "许昌"
REQUEST_TIMEOUT_SECONDS = 120
FETCH_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5


def accumulate_output_root() -> Path:
    return get_data_registry() / "xuchang_henan_month_year_accumulate"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _city_rank(rows: list[dict[str, Any]], city: str) -> dict[str, Any] | None:
    for rank, row in enumerate(rows, start=1):
        if row.get("city") == city:
            return {"rank": rank, "row": row}
    return None


class HenanCityAccumulateStorage:
    """Upsert city ranking rows into XcAiDb.dbo.HenanCityAccumulateRanking."""

    table_name = "HenanCityAccumulateRanking"

    _UPSERT_SQL = f"""
        MERGE dbo.{table_name} AS target
        USING (SELECT ? AS period_type, ? AS period, ? AS city) AS source
          ON target.period_type = source.period_type
             AND target.period = source.period
             AND target.city = source.city
        WHEN MATCHED THEN UPDATE SET
          city_rank=?, is_pro_city=?, zong=?, pm25=?, pm10=?, so2=?, no2=?, co=?, o3=?,
          zong_change_rate=?, change_rate=?, ratio=?, o3_exceed_days=?, heavy_pollution_days=?,
          valid_days=?, pm_valid_days=?, stat_start=?, stat_end=?, lastyear_json=?,
          fetched_at=?
        WHEN NOT MATCHED THEN INSERT (
          period_type, period, city, city_rank, is_pro_city,
          zong, pm25, pm10, so2, no2, co, o3,
          zong_change_rate, change_rate, ratio, o3_exceed_days, heavy_pollution_days,
          valid_days, pm_valid_days, stat_start, stat_end, lastyear_json, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    def __init__(
        self, connection_string_factory: Callable[[], str] = xcai_connection_string
    ) -> None:
        self.connection_string_factory = connection_string_factory

    def ensure_table(self, cursor: pyodbc.Cursor) -> None:
        cursor.execute(
            f"""
            IF OBJECT_ID(N'dbo.{self.table_name}', N'U') IS NULL
            CREATE TABLE dbo.{self.table_name} (
                id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                period_type NVARCHAR(10) NOT NULL,
                period NVARCHAR(10) NOT NULL,
                city NVARCHAR(50) NOT NULL,
                city_rank INT NOT NULL,
                is_pro_city TINYINT NULL,
                zong FLOAT NULL,
                pm25 FLOAT NULL,
                pm10 FLOAT NULL,
                so2 FLOAT NULL,
                no2 FLOAT NULL,
                co FLOAT NULL,
                o3 FLOAT NULL,
                zong_change_rate NVARCHAR(20) NULL,
                change_rate FLOAT NULL,
                ratio FLOAT NULL,
                o3_exceed_days INT NULL,
                heavy_pollution_days INT NULL,
                valid_days INT NULL,
                pm_valid_days INT NULL,
                stat_start DATE NULL,
                stat_end DATE NULL,
                lastyear_json NVARCHAR(MAX) NULL,
                fetched_at DATETIME2 NOT NULL,
                created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
            );
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_{self.table_name}_PeriodCity'
                AND object_id = OBJECT_ID(N'dbo.{self.table_name}'))
            CREATE UNIQUE INDEX UX_{self.table_name}_PeriodCity
                ON dbo.{self.table_name} (period_type, period, city);
            """
        )

    def save(self, records: list[dict[str, Any]]) -> int:
        if not records:
            raise ValueError("no ranking rows to persist")
        connection = pyodbc.connect(self.connection_string_factory(), timeout=30)
        cursor = connection.cursor()
        try:
            self.ensure_table(cursor)
            for record in records:
                cursor.execute(self._UPSERT_SQL, self._upsert_params(record))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()
        return len(records)

    @staticmethod
    def _upsert_params(record: dict[str, Any]) -> tuple:
        values = (
            record["period_type"],
            record["period"],
            record["city"],
            record["city_rank"],
            record["is_pro_city"],
            record["zong"],
            record["pm25"],
            record["pm10"],
            record["so2"],
            record["no2"],
            record["co"],
            record["o3"],
            record["zong_change_rate"],
            record["change_rate"],
            record["ratio"],
            record["o3_exceed_days"],
            record["heavy_pollution_days"],
            record["valid_days"],
            record["pm_valid_days"],
            record["stat_start"],
            record["stat_end"],
            record["lastyear_json"],
            record["fetched_at"],
        )
        # MERGE 参数顺序: USING键(3) + UPDATE SET(20) 由前一份 values 覆盖,
        # INSERT VALUES(23) 由第二份完整 values 覆盖。
        return values + values


def build_db_records(
    *,
    kind: str,
    period: str,
    payload: dict[str, Any],
    fetched_at: datetime,
) -> list[dict[str, Any]]:
    rows = payload["data"]
    lastyear_by_city = {str(row.get("city")): row for row in payload.get("lastyear") or []}
    ratio_values = payload.get("ratio") or []
    records: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        city = row.get("city")
        if not city:
            continue
        lastyear_row = lastyear_by_city.get(str(city))
        ratio_value = ratio_values[rank - 1] if rank - 1 < len(ratio_values) else None
        zong_change_rate = row.get("zhzsbhl")
        records.append(
            {
                "period_type": kind,
                "period": period,
                "city": str(city),
                "city_rank": rank,
                "is_pro_city": _int(row.get("isprocity")),
                "zong": _number(row.get("zong")),
                "pm25": _number(row.get("pm25")),
                "pm10": _number(row.get("pm10")),
                "so2": _number(row.get("so2")),
                "no2": _number(row.get("no2")),
                "co": _number(row.get("co")),
                "o3": _number(row.get("o3")),
                "zong_change_rate": str(zong_change_rate)
                if zong_change_rate not in (None, "")
                else None,
                "change_rate": _number(row.get("bhl")),
                "ratio": _number(ratio_value),
                "o3_exceed_days": _int(row.get("o3cbts")),
                "heavy_pollution_days": _int(row.get("zdwrts")),
                "valid_days": _int(row.get("cnt")),
                "pm_valid_days": _int(row.get("pmcnt")),
                "stat_start": payload.get("start"),
                "stat_end": payload.get("end"),
                "lastyear_json": (
                    json.dumps(lastyear_row, ensure_ascii=False, separators=(",", ":"))
                    if lastyear_row
                    else None
                ),
                "fetched_at": fetched_at,
            }
        )
    return records


class XuchangHenanMonthYearAccumulateFetcher(DataFetcher):
    """Fetch the Henan city month/year cumulative ranking once per day."""

    def __init__(
        self,
        session: requests.Session | None = None,
        now_factory: Callable[[], datetime] = datetime.now,
        output_root_factory: Callable[[], Path] = accumulate_output_root,
        storage: HenanCityAccumulateStorage | None = None,
    ) -> None:
        super().__init__(
            name="xuchang_henan_month_year_accumulate_fetcher",
            description="抓取河南空气质量APP全省城市月累计/年累计排名数据",
            schedule="40 7 * * *",
            version="1.2.0",
        )
        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": "suyuan-xuchang-accumulate-fetcher/1.2", "Accept": "application/json"}
        )
        self.now_factory = now_factory
        self.output_root_factory = output_root_factory
        self.storage = storage or HenanCityAccumulateStorage()

    def _fetch(self, params: dict[str, str]) -> dict[str, Any]:
        url = f"{CITY_RANKING_URL}?{urlencode(params)}"
        last_error: Exception | None = None
        for attempt in range(1, FETCH_RETRIES + 1):
            try:
                response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
                payload = response.json()
                if payload.get("flag") is not True or not isinstance(payload.get("data"), list):
                    raise ValueError(
                        f"city ranking endpoint returned unusable payload for {params}"
                    )
                return payload
            except (requests.RequestException, ValueError) as error:
                last_error = error
                logger.warning(
                    "xuchang_henan_accumulate_fetch_retry",
                    attempt=attempt,
                    retries=FETCH_RETRIES,
                    error=str(error),
                )
                if attempt < FETCH_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS)
        raise RuntimeError(f"city ranking fetch failed: {last_error}")

    def _build_json_payload(
        self,
        *,
        kind: str,
        period: str,
        query: dict[str, str],
        payload: dict[str, Any],
        fetched_at: datetime,
    ) -> dict[str, Any]:
        rows = payload["data"]
        return {
            "kind": kind,
            "period": period,
            "fetched_at": fetched_at.isoformat(),
            "query": query,
            "range": {
                "start": payload.get("start"),
                "end": payload.get("end"),
                "last_start": payload.get("lastStart"),
            },
            "count": payload.get("count"),
            "days": payload.get("days"),
            "rows": rows,
            "lastyear": payload.get("lastyear"),
            "ratio": payload.get("ratio"),
            "xuchang": _city_rank(rows, XUCHANG_CITY),
        }

    def _fetch_kind(
        self, kind: str, fetched_at: datetime
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        today = fetched_at.date()
        if kind == "monthly":
            period = today.strftime("%Y-%m")
            query = {"month": period}
        else:
            period = str(today.year)
            end = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            query = {"start": f"{today.year}-01-01", "end": end}
        payload = self._fetch(query)
        json_payload = self._build_json_payload(
            kind=kind, period=period, query=query, payload=payload, fetched_at=fetched_at
        )
        db_records = build_db_records(
            kind=kind, period=period, payload=payload, fetched_at=fetched_at
        )
        return json_payload, db_records

    async def fetch_and_store(self) -> dict[str, Any]:
        fetched_at = self.now_factory().replace(microsecond=0)
        results: dict[str, Any] = {}
        for kind in ("monthly", "yearly"):
            json_payload, db_records = self._fetch_kind(kind, fetched_at)
            # 当月/当年的 period 文件每日运行时整体替换, 历史月份归档保留。
            target = self.output_root_factory() / kind / f"{json_payload['period']}.json"
            write_json(target, json_payload)
            saved = self.storage.save(db_records)
            xuchang = json_payload.get("xuchang") or {}
            results[kind] = {
                "period": json_payload["period"],
                "range": json_payload["range"],
                "saved_rows": saved,
                "xuchang_rank": xuchang.get("rank"),
                "xuchang_zong": (xuchang.get("row") or {}).get("zong"),
            }
        logger.info("xuchang_henan_month_year_accumulate_completed", **results)
        return results
