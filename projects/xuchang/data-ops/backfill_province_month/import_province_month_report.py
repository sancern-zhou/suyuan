"""把 parse_province_month_reports.py 产出的 CSV 导入 DataCrawler.ProvinceMonthReport。

幂等：按 (Level, City, RegionName, Scope, DataMonth) upsert，可重复执行。
运行（宿主机）:
  /opt/miniconda3/envs/backend_py311/bin/python import_province_month_report.py \
    --csv /tmp/opencode/province_month_report.csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import date

import pymysql

DB = {
    "host": "127.0.0.1",
    "port": 13307,
    "user": "root",
    "password": "1V4MIHsQGZIbJpec",
    "database": "DataCrawler",
    "charset": "utf8mb4",
}

DDL = """
CREATE TABLE IF NOT EXISTS ProvinceMonthReport (
  ID BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  Level VARCHAR(16) NOT NULL COMMENT 'province=全省/city=省辖市/district=省辖市所辖区/county=县（市）',
  City VARCHAR(50) NOT NULL COMMENT '所属省辖市(全省行=全省)',
  RegionName VARCHAR(50) NOT NULL COMMENT '区域名(市全称/区/县市/全省)',
  DataMonth DATE NOT NULL COMMENT '归属月份(1号)',
  Scope VARCHAR(16) NOT NULL COMMENT 'month=当月/cum=1-N月累计',
  PM10 DECIMAL(10,2) NULL COMMENT 'PM10月均或累计均值(ug/m3)',
  PM10_YoY DECIMAL(10,2) NULL COMMENT 'PM10同比变化率(%)',
  PM25 DECIMAL(10,2) NULL,
  PM25_YoY DECIMAL(10,2) NULL,
  O3 DECIMAL(10,2) NULL COMMENT 'O3-8h第90百分位(ug/m3,供暖季无此列)',
  O3_YoY DECIMAL(10,2) NULL,
  GoodDays DECIMAL(10,1) NULL COMMENT '优良天数',
  GoodDays_Change DECIMAL(10,1) NULL COMMENT '优良天数同比变化(天)',
  GoodDays_Ratio DECIMAL(10,2) NULL COMMENT '优良比例(%)',
  GoodDays_RatioChg DECIMAL(10,2) NULL COMMENT '优良比例同比增减(百分点)',
  HeavyDays DECIMAL(10,1) NULL COMMENT '重度及以上污染天数(仅市级表)',
  HeavyDays_Change DECIMAL(10,1) NULL,
  HeavyDays_Ratio DECIMAL(10,2) NULL,
  HeavyDays_RatioChg DECIMAL(10,2) NULL,
  CompositeIndex DECIMAL(10,3) NULL COMMENT '综合指数',
  CompositeIndex_YoY DECIMAL(10,2) NULL COMMENT '综合指数同比变化率(%)',
  SourceFile VARCHAR(255) NOT NULL,
  CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY UK_ProvinceMonthReport (Level, City, RegionName, Scope, DataMonth),
  KEY IDX_ProvinceMonthReport_Month (DataMonth)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='河南省环境空气质量月报附表(2025-12,2026-01~09;官方口径19市/88区/101县市)'
"""

COLUMNS = [
    "Level", "City", "RegionName", "DataMonth", "Scope",
    "PM10", "PM10_YoY", "PM25", "PM25_YoY", "O3", "O3_YoY",
    "GoodDays", "GoodDays_Change", "GoodDays_Ratio", "GoodDays_RatioChg",
    "HeavyDays", "HeavyDays_Change", "HeavyDays_Ratio", "HeavyDays_RatioChg",
    "CompositeIndex", "CompositeIndex_YoY", "SourceFile",
]
NUMERIC = {c for c in COLUMNS if c not in ("Level", "City", "RegionName", "DataMonth", "Scope", "SourceFile")}

UPSERT = "INSERT INTO ProvinceMonthReport ({cols}) VALUES ({ph}) ON DUPLICATE KEY UPDATE {upd}".format(
    cols=", ".join(COLUMNS),
    ph=", ".join(["%s"] * len(COLUMNS)),
    upd=", ".join(f"{c}=VALUES({c})" for c in COLUMNS[5:]),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()

    rows: list[tuple] = []
    with open(args.csv, encoding="utf-8-sig", newline="") as fh:
        for rec in csv.DictReader(fh):
            row = []
            for col in COLUMNS:
                value = (rec.get(col) or "").strip()
                if col == "DataMonth":
                    row.append(date.fromisoformat(value))
                elif col in NUMERIC:
                    row.append(float(value) if value else None)
                else:
                    row.append(value)
            rows.append(tuple(row))

    conn = pymysql.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
            cur.executemany(UPSERT, rows)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT Level, Scope, COUNT(*) FROM ProvinceMonthReport GROUP BY Level, Scope ORDER BY Level, Scope")
            for line in cur.fetchall():
                print("  ", line)
            cur.execute("SELECT COUNT(*) FROM ProvinceMonthReport")
            print("总行数:", cur.fetchone()[0])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
