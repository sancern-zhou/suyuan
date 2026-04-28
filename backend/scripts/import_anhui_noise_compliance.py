"""
Import Anhui city noise compliance Excel data into SQL Server.

The source workbook has two sheets:
- 汇总表: monthly province/city summary rows
- 详情表: daily city detail rows
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pyodbc


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings  # noqa: E402


DEFAULT_EXCEL_PATH = (
    r"D:\企业微信\WXWork\1688857397409442\Cache\File\2026-04"
    r"\安徽省16地市2025年11月达标率_2025-11-01_2025-11-30..xlsx"
)

PROVINCE = "安徽"
SUMMARY_TABLE = "dbo.noise_city_compliance_monthly"
DETAIL_TABLE = "dbo.noise_city_compliance_daily"


SUMMARY_COLUMNS = [
    "城市/区域",
    "数据时间",
    "统计天数",
    "站点总数",
    "昼间总采集率(%)",
    "昼间有效采集率(%)",
    "昼间达标率排名",
    "昼间达标率(%)",
    "昼间达标率同比(百分点)",
    "昼间达标率环比(百分点)",
    "夜间总采集率(%)",
    "夜间有效采集率(%)",
    "夜间达标率排名",
    "夜间评价达标率(%)",
    "夜间评价达标率同比(百分点)",
    "夜间评价达标率环比(百分点)",
]

DETAIL_COLUMNS = [
    "城市/区域",
    "数据时间",
    "站点总数（个）",
    "昼间总采集率(%)",
    "昼间有效采集率(%)",
    "昼间达标监测站点数（天）",
    "昼间有效监测站点数（天）",
    "昼间达标率(%)",
    "昼间达标率同比(百分点)",
    "昼间达标率环比(百分点)",
    "夜间总采集率(%)",
    "夜间有效采集率(%)",
    "夜间达标监测站点数（天）",
    "夜间有效监测站点数（天）",
    "夜间评价达标率(%)",
    "夜间评价达标率同比(百分点)",
    "夜间评价达标率环比(百分点)",
    "1类",
    "F19",
    "F20",
    "2类",
    "F22",
    "F23",
    "3类",
    "F25",
    "F26",
    "4a类",
    "F28",
    "F29",
]


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def to_float(value: Any) -> float | None:
    text = clean_text(value)
    if text is None or text == "—":
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def to_int(value: Any) -> int | None:
    number = to_float(value)
    return None if number is None else int(round(number))


def parse_period(value: Any) -> tuple[str, str, str]:
    text = clean_text(value)
    if not text:
        raise ValueError("数据时间为空，无法解析统计周期")
    match = re.match(r"(\d{4}-\d{2}-\d{2})至(\d{4}-\d{2}-\d{2})", text)
    if not match:
        raise ValueError(f"无法解析统计周期: {text}")
    start_date, end_date = match.groups()
    return start_date, end_date, start_date[:7]


def excel_connection_string(path: Path) -> str:
    return (
        "DRIVER={Microsoft Excel Driver (*.xls, *.xlsx, *.xlsm, *.xlsb)};"
        f"DBQ={path};"
        "ReadOnly=1;"
    )


def fetch_excel_rows(path: Path, sheet_name: str) -> list[dict[str, Any]]:
    conn = pyodbc.connect(excel_connection_string(path), autocommit=True)
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT * FROM [{sheet_name}$]")
        columns = [column[0] for column in cursor.description]
        rows = []
        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            city = clean_text(record.get("城市/区域"))
            if not city:
                continue
            rows.append(record)
        return rows
    finally:
        cursor.close()
        conn.close()


def sql_connection() -> pyodbc.Connection:
    settings = Settings(_env_file=str(PROJECT_ROOT / ".env"))
    return pyodbc.connect(settings.sqlserver_connection_string, timeout=30)


def create_tables(cursor: pyodbc.Cursor) -> None:
    cursor.execute(
        f"""
IF OBJECT_ID(N'{SUMMARY_TABLE}', N'U') IS NULL
BEGIN
    CREATE TABLE {SUMMARY_TABLE} (
        id INT IDENTITY(1,1) PRIMARY KEY,
        province NVARCHAR(50) NOT NULL,
        city_name NVARCHAR(50) NOT NULL,
        period_text NVARCHAR(50) NOT NULL,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        period_month CHAR(7) NOT NULL,
        stat_days INT NULL,
        station_total INT NULL,
        day_total_collection_rate DECIMAL(8,2) NULL,
        day_valid_collection_rate DECIMAL(8,2) NULL,
        day_compliance_rank INT NULL,
        day_compliance_rate DECIMAL(8,2) NULL,
        day_yoy_pp DECIMAL(8,2) NULL,
        day_mom_pp DECIMAL(8,2) NULL,
        night_total_collection_rate DECIMAL(8,2) NULL,
        night_valid_collection_rate DECIMAL(8,2) NULL,
        night_compliance_rank INT NULL,
        night_compliance_rate DECIMAL(8,2) NULL,
        night_yoy_pp DECIMAL(8,2) NULL,
        night_mom_pp DECIMAL(8,2) NULL,
        night_status AS (
            CASE
                WHEN night_compliance_rate IS NULL THEN N'无有效数据'
                WHEN night_compliance_rate >= 100 THEN N'达标'
                ELSE N'未达标'
            END
        ) PERSISTED,
        is_province_total BIT NOT NULL DEFAULT 0,
        source_file NVARCHAR(500) NOT NULL,
        imported_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
"""
    )
    cursor.execute(
        f"""
IF OBJECT_ID(N'{DETAIL_TABLE}', N'U') IS NULL
BEGIN
    CREATE TABLE {DETAIL_TABLE} (
        id INT IDENTITY(1,1) PRIMARY KEY,
        province NVARCHAR(50) NOT NULL,
        city_name NVARCHAR(50) NOT NULL,
        data_date DATE NOT NULL,
        period_month CHAR(7) NOT NULL,
        station_total INT NULL,
        day_total_collection_rate DECIMAL(8,2) NULL,
        day_valid_collection_rate DECIMAL(8,2) NULL,
        day_compliant_station_days INT NULL,
        day_valid_station_days INT NULL,
        day_compliance_rate DECIMAL(8,2) NULL,
        day_yoy_pp DECIMAL(8,2) NULL,
        day_mom_pp DECIMAL(8,2) NULL,
        night_total_collection_rate DECIMAL(8,2) NULL,
        night_valid_collection_rate DECIMAL(8,2) NULL,
        night_compliant_station_days INT NULL,
        night_valid_station_days INT NULL,
        night_compliance_rate DECIMAL(8,2) NULL,
        night_yoy_pp DECIMAL(8,2) NULL,
        night_mom_pp DECIMAL(8,2) NULL,
        class1_station_total INT NULL,
        class1_day_valid_station_days INT NULL,
        class1_night_valid_station_days INT NULL,
        class2_station_total INT NULL,
        class2_day_valid_station_days INT NULL,
        class2_night_valid_station_days INT NULL,
        class3_station_total INT NULL,
        class3_day_valid_station_days INT NULL,
        class3_night_valid_station_days INT NULL,
        class4a_station_total INT NULL,
        class4a_day_valid_station_days INT NULL,
        class4a_night_valid_station_days INT NULL,
        night_status AS (
            CASE
                WHEN night_compliance_rate IS NULL THEN N'无有效数据'
                WHEN night_compliance_rate >= 100 THEN N'达标'
                ELSE N'未达标'
            END
        ) PERSISTED,
        source_file NVARCHAR(500) NOT NULL,
        imported_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
"""
    )
    cursor.execute(
        f"""
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_noise_city_compliance_monthly_period'
      AND object_id = OBJECT_ID(N'{SUMMARY_TABLE}')
)
CREATE INDEX IX_noise_city_compliance_monthly_period
ON {SUMMARY_TABLE}(province, period_month, is_province_total, night_compliance_rate);
"""
    )
    cursor.execute(
        f"""
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_noise_city_compliance_daily_period'
      AND object_id = OBJECT_ID(N'{DETAIL_TABLE}')
)
CREATE INDEX IX_noise_city_compliance_daily_period
ON {DETAIL_TABLE}(province, period_month, city_name, data_date, night_status);
"""
    )


def normalize_summary(row: dict[str, Any], source_file: str) -> tuple[Any, ...]:
    period_start, period_end, period_month = parse_period(row["数据时间"])
    city_name = clean_text(row["城市/区域"])
    return (
        PROVINCE,
        city_name,
        clean_text(row["数据时间"]),
        period_start,
        period_end,
        period_month,
        to_int(row["统计天数"]),
        to_int(row["站点总数"]),
        to_float(row["昼间总采集率(%)"]),
        to_float(row["昼间有效采集率(%)"]),
        to_int(row["昼间达标率排名"]),
        to_float(row["昼间达标率(%)"]),
        to_float(row["昼间达标率同比(百分点)"]),
        to_float(row["昼间达标率环比(百分点)"]),
        to_float(row["夜间总采集率(%)"]),
        to_float(row["夜间有效采集率(%)"]),
        to_int(row["夜间达标率排名"]),
        to_float(row["夜间评价达标率(%)"]),
        to_float(row["夜间评价达标率同比(百分点)"]),
        to_float(row["夜间评价达标率环比(百分点)"]),
        1 if city_name == "全省" else 0,
        source_file,
    )


def normalize_detail(row: dict[str, Any], source_file: str) -> tuple[Any, ...]:
    data_date = clean_text(row["数据时间"])
    if not data_date:
        raise ValueError("详情表数据时间为空")
    return (
        PROVINCE,
        clean_text(row["城市/区域"]),
        data_date,
        data_date[:7],
        to_int(row["站点总数（个）"]),
        to_float(row["昼间总采集率(%)"]),
        to_float(row["昼间有效采集率(%)"]),
        to_int(row["昼间达标监测站点数（天）"]),
        to_int(row["昼间有效监测站点数（天）"]),
        to_float(row["昼间达标率(%)"]),
        to_float(row["昼间达标率同比(百分点)"]),
        to_float(row["昼间达标率环比(百分点)"]),
        to_float(row["夜间总采集率(%)"]),
        to_float(row["夜间有效采集率(%)"]),
        to_int(row["夜间达标监测站点数（天）"]),
        to_int(row["夜间有效监测站点数（天）"]),
        to_float(row["夜间评价达标率(%)"]),
        to_float(row["夜间评价达标率同比(百分点)"]),
        to_float(row["夜间评价达标率环比(百分点)"]),
        to_int(row["1类"]),
        to_int(row["F19"]),
        to_int(row["F20"]),
        to_int(row["2类"]),
        to_int(row["F22"]),
        to_int(row["F23"]),
        to_int(row["3类"]),
        to_int(row["F25"]),
        to_int(row["F26"]),
        to_int(row["4a类"]),
        to_int(row["F28"]),
        to_int(row["F29"]),
        source_file,
    )


def insert_rows(conn: pyodbc.Connection, excel_path: Path) -> tuple[int, int]:
    summary_rows = fetch_excel_rows(excel_path, "汇总表")
    detail_rows = fetch_excel_rows(excel_path, "详情表")

    summary_data = [normalize_summary(row, str(excel_path)) for row in summary_rows]
    detail_data = [normalize_detail(row, str(excel_path)) for row in detail_rows]

    if not summary_data:
        raise RuntimeError("汇总表没有可导入的数据")

    period_months = sorted({row[5] for row in summary_data})
    if len(period_months) != 1:
        raise RuntimeError(f"源文件包含多个统计月份: {period_months}")
    period_month = period_months[0]

    cursor = conn.cursor()
    cursor.fast_executemany = True
    try:
        create_tables(cursor)
        cursor.execute(
            f"DELETE FROM {SUMMARY_TABLE} WHERE province = ? AND period_month = ? AND source_file = ?",
            (PROVINCE, period_month, str(excel_path)),
        )
        cursor.execute(
            f"DELETE FROM {DETAIL_TABLE} WHERE province = ? AND period_month = ? AND source_file = ?",
            (PROVINCE, period_month, str(excel_path)),
        )

        summary_placeholders = ",".join(["?"] * 22)
        cursor.executemany(
            f"""
INSERT INTO {SUMMARY_TABLE} (
    province, city_name, period_text, period_start, period_end, period_month,
    stat_days, station_total, day_total_collection_rate, day_valid_collection_rate,
    day_compliance_rank, day_compliance_rate, day_yoy_pp, day_mom_pp,
    night_total_collection_rate, night_valid_collection_rate, night_compliance_rank,
    night_compliance_rate, night_yoy_pp, night_mom_pp, is_province_total, source_file
) VALUES ({summary_placeholders})
""",
            summary_data,
        )

        detail_placeholders = ",".join(["?"] * 32)
        cursor.executemany(
            f"""
INSERT INTO {DETAIL_TABLE} (
    province, city_name, data_date, period_month, station_total,
    day_total_collection_rate, day_valid_collection_rate, day_compliant_station_days,
    day_valid_station_days, day_compliance_rate, day_yoy_pp, day_mom_pp,
    night_total_collection_rate, night_valid_collection_rate, night_compliant_station_days,
    night_valid_station_days, night_compliance_rate, night_yoy_pp, night_mom_pp,
    class1_station_total, class1_day_valid_station_days, class1_night_valid_station_days,
    class2_station_total, class2_day_valid_station_days, class2_night_valid_station_days,
    class3_station_total, class3_day_valid_station_days, class3_night_valid_station_days,
    class4a_station_total, class4a_day_valid_station_days, class4a_night_valid_station_days,
    source_file
) VALUES ({detail_placeholders})
""",
            detail_data,
        )
        conn.commit()
        return len(summary_data), len(detail_data)
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Anhui noise compliance workbook to SQL Server")
    parser.add_argument("--excel", default=DEFAULT_EXCEL_PATH, help="Path to source xlsx")
    args = parser.parse_args()

    excel_path = Path(args.excel)
    if not excel_path.exists():
        raise FileNotFoundError(excel_path)

    with sql_connection() as conn:
        summary_count, detail_count = insert_rows(conn, excel_path)

    print(f"导入完成: 汇总表 {summary_count} 行，详情表 {detail_count} 行")
    print(f"目标表: {SUMMARY_TABLE}, {DETAIL_TABLE}")
    print(f"导入时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
