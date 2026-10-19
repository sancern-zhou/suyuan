"""把 parse_year_targets.py 产出的 CSV 导入 DataCrawler 四张年度/排名表（幂等 upsert）。

  xuchang_city_year.csv   -> XuchangCityYearTarget  (UK: Year)
  xuchang_county_year.csv -> XuchangCountyYearTarget (UK: Region+Year)
  henan_city_year.csv     -> HenanCityYearTarget     (UK: City+Year)
  rank168_monthly.csv     -> Rank168CityMonthly      (UK: City+PeriodType+DataMonth)

运行（宿主机）:
  /opt/miniconda3/envs/backend_py311/bin/python import_year_targets.py \
    --csv-dir /tmp/year_target_csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from pathlib import Path

import pymysql

DB = {
    "host": "127.0.0.1",
    "port": 13307,
    "user": "root",
    "password": "1V4MIHsQGZIbJpec",
    "database": "DataCrawler",
    "charset": "utf8mb4",
}

DDL = [
    """CREATE TABLE IF NOT EXISTS XuchangCityYearTarget (
        ID BIGINT AUTO_INCREMENT PRIMARY KEY,
        Year INT NOT NULL COMMENT '年度',
        Pm10Target DOUBLE NULL COMMENT 'PM10目标(μg/m³,上级下达/市定)',
        Pm25Target DOUBLE NULL COMMENT 'PM2.5目标(μg/m³)',
        GoodDaysTarget DOUBLE NULL COMMENT '优良天目标(天)',
        HeavyDaysTarget DOUBLE NULL COMMENT '重污染天目标(天,2022起下达)',
        Pm10 DOUBLE NULL COMMENT 'PM10年均实际(国家网口径)',
        Pm25 DOUBLE NULL COMMENT 'PM2.5年均实际(国家网口径)',
        So2 DOUBLE NULL COMMENT 'SO2年均(μg/m³,2015-2025)',
        No2 DOUBLE NULL COMMENT 'NO2年均(μg/m³)',
        Co DOUBLE NULL COMMENT 'CO第95百分位(mg/m³)',
        O3 DOUBLE NULL COMMENT 'O3年均(μg/m³,仅2015-2020有)',
        GoodDays INT NULL COMMENT '优良天实际(天)',
        HeavyDays INT NULL COMMENT '重污染天实际(天,剔沙尘)',
        O3ExceedDays INT NULL COMMENT '臭氧超标天(天)',
        Remark VARCHAR(255) NULL,
        SourceFile VARCHAR(255) NULL,
        CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_year (Year)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='许昌市年度空气质量目标vs实际(官方定版,国家网口径)'""",
    """CREATE TABLE IF NOT EXISTS XuchangCountyYearTarget (
        ID BIGINT AUTO_INCREMENT PRIMARY KEY,
        Region VARCHAR(50) NOT NULL COMMENT '区域(许昌市/9县市区)',
        RegionType VARCHAR(20) NOT NULL COMMENT 'city全市/urban市辖区国家平台/county县市省平台',
        Year INT NOT NULL,
        Pm10Target DOUBLE NULL COMMENT 'PM10目标(μg/m³)',
        Pm10 DOUBLE NULL COMMENT 'PM10年均实际(μg/m³)',
        Pm10Completed VARCHAR(4) NULL COMMENT 'PM10目标完成(是/否)',
        Pm25Target DOUBLE NULL COMMENT 'PM2.5目标(μg/m³)',
        Pm25 DOUBLE NULL COMMENT 'PM2.5年均实际(μg/m³)',
        Pm25Completed VARCHAR(4) NULL,
        GoodDaysTarget DOUBLE NULL COMMENT '优良天目标(天)',
        GoodDays INT NULL COMMENT '优良天实际(天)',
        GoodDaysCompleted VARCHAR(4) NULL,
        HeavyDaysTarget INT NULL COMMENT '重污染天目标(天,2022起)',
        HeavyDays INT NULL COMMENT '重污染天实际(天,剔沙尘口径,2020/2021来自剔沙尘表)',
        HeavyDaysCompleted VARCHAR(4) NULL,
        Remark VARCHAR(255) NULL,
        SourceFile VARCHAR(255) NULL,
        CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_region_year (Region, Year)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='许昌县市区年度空气质量目标vs实际(官方考核定版,剔沙尘)'""",
    """CREATE TABLE IF NOT EXISTS HenanCityYearTarget (
        ID BIGINT AUTO_INCREMENT PRIMARY KEY,
        City VARCHAR(50) NOT NULL COMMENT '地市(18个含济源市)',
        Year INT NOT NULL,
        Pm10Target DOUBLE NULL COMMENT 'PM10目标(μg/m³)',
        Pm10 DOUBLE NULL COMMENT 'PM10年均实际(μg/m³)',
        Pm10Completed VARCHAR(4) NULL,
        Pm25Target DOUBLE NULL COMMENT 'PM2.5目标(μg/m³)',
        Pm25 DOUBLE NULL COMMENT 'PM2.5年均实际(μg/m³)',
        Pm25Completed VARCHAR(4) NULL,
        GoodDaysTarget DOUBLE NULL COMMENT '优良天目标(天,2021-2022/2024)',
        GoodDays INT NULL COMMENT '优良天实际(天)',
        GoodDaysRatioTarget DOUBLE NULL COMMENT '优良天比例目标(%)',
        GoodDaysRatio DOUBLE NULL COMMENT '优良天比例实际(%,2023/2025)',
        GoodDaysCompleted VARCHAR(4) NULL,
        HeavyDaysTarget DOUBLE NULL COMMENT '重污染天目标(天)',
        HeavyDays INT NULL COMMENT '重污染天实际(天)',
        HeavyDaysRatioTarget DOUBLE NULL COMMENT '重污染天比例目标(%)',
        HeavyDaysRatio DOUBLE NULL COMMENT '重污染天比例实际(%,2023/2025)',
        HeavyDaysCompleted VARCHAR(4) NULL,
        O3ExceedDaysTarget INT NULL COMMENT '5-9月臭氧超标天目标(天,2022-2023)',
        O3ExceedDays INT NULL COMMENT '5-9月臭氧超标天实际(天)',
        O3ExceedOver INT NULL COMMENT '臭氧超标天超出目标(天)',
        CompletedCount INT NULL COMMENT '完成指标数量',
        Remark VARCHAR(255) NULL,
        SourceFile VARCHAR(255) NULL,
        CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_city_year (City, Year)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='河南省18地市年度空气质量目标完成情况(省考核口径,2021-2025)'""",
    """CREATE TABLE IF NOT EXISTS Rank168CityMonthly (
        ID BIGINT AUTO_INCREMENT PRIMARY KEY,
        City VARCHAR(50) NOT NULL COMMENT '城市(168重点城市)',
        PeriodType VARCHAR(10) NOT NULL COMMENT 'month当月/cum累计',
        DataMonth DATE NOT NULL COMMENT '当月行:当月1日;累计行:截止月1日',
        PeriodEnd DATE NULL COMMENT '累计行:截止月月末',
        PeriodLabel VARCHAR(20) NULL COMMENT '期次标签(1月/1-7月)',
        CompositeIndex DOUBLE NULL COMMENT '环境空气质量综合指数(生态环境部168城排名口径)',
        CompositeIndexRank INT NULL COMMENT '综合指数排名(倒序,1=最差)',
        Pm25 DOUBLE NULL COMMENT 'PM2.5浓度(μg/m³)',
        Pm25Rank INT NULL COMMENT 'PM2.5浓度排名(倒序,1=最差)',
        SourceFile VARCHAR(255) NULL,
        CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_city_pt_dm (City, PeriodType, DataMonth)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='生态环境部168重点城市排名(2026年逐月+累计,仅排名/综合指数,浓度以本地口径为准)'""",
]

JOBS = [
    ("xuchang_city_year.csv", "XuchangCityYearTarget",
     ["Year", "Pm10Target", "Pm25Target", "GoodDaysTarget", "HeavyDaysTarget",
      "Pm10", "Pm25", "So2", "No2", "Co", "O3", "GoodDays", "HeavyDays",
      "O3ExceedDays", "Remark", "SourceFile"],
     ("Year",), {"GoodDays", "HeavyDays", "O3ExceedDays"}),
    ("xuchang_county_year.csv", "XuchangCountyYearTarget",
     ["Region", "RegionType", "Year", "Pm10Target", "Pm10", "Pm10Completed",
      "Pm25Target", "Pm25", "Pm25Completed", "GoodDaysTarget", "GoodDays",
      "GoodDaysCompleted", "HeavyDaysTarget", "HeavyDays", "HeavyDaysCompleted",
      "Remark", "SourceFile"],
     ("Region", "Year"), {"GoodDays", "HeavyDays", "HeavyDaysTarget"}),
    ("henan_city_year.csv", "HenanCityYearTarget",
     ["City", "Year", "Pm10Target", "Pm10", "Pm10Completed", "Pm25Target", "Pm25",
      "Pm25Completed", "GoodDaysTarget", "GoodDays", "GoodDaysRatioTarget",
      "GoodDaysRatio", "GoodDaysCompleted", "HeavyDaysTarget", "HeavyDays",
      "HeavyDaysRatioTarget", "HeavyDaysRatio", "HeavyDaysCompleted",
      "O3ExceedDaysTarget", "O3ExceedDays", "O3ExceedOver", "CompletedCount",
      "Remark", "SourceFile"],
     ("City", "Year"),
     {"GoodDays", "HeavyDays", "O3ExceedDays", "O3ExceedOver", "O3ExceedDaysTarget", "CompletedCount"}),
    ("rank168_monthly.csv", "Rank168CityMonthly",
     ["City", "PeriodType", "DataMonth", "PeriodEnd", "PeriodLabel", "CompositeIndex",
      "CompositeIndexRank", "Pm25", "Pm25Rank", "SourceFile"],
     ("City", "PeriodType", "DataMonth"), {"CompositeIndexRank", "Pm25Rank"}),
]


def convert(col: str, value: str, int_cols: set[str], date_cols: set[str]):
    value = (value or "").strip()
    if value == "":
        return None
    if col in date_cols:
        return date.fromisoformat(value)
    if col in int_cols:
        return int(float(value))
    try:
        return float(value)
    except ValueError:
        return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", default="/tmp/year_target_csv")
    args = parser.parse_args()
    csv_dir = Path(args.csv_dir)

    conn = pymysql.connect(**DB)
    try:
        with conn.cursor() as cur:
            for ddl in DDL:
                cur.execute(ddl)
        conn.commit()

        for filename, table, cols, keys, int_cols in JOBS:
            date_cols = {"DataMonth", "PeriodEnd"} if table == "Rank168CityMonthly" else set()
            update_cols = [c for c in cols if c not in keys]
            sql = (
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                f"ON DUPLICATE KEY UPDATE {', '.join(f'{c}=VALUES({c})' for c in update_cols)}"
            )
            rows: list[tuple] = []
            with open(csv_dir / filename, encoding="utf-8-sig", newline="") as fh:
                for rec in csv.DictReader(fh):
                    rows.append(tuple(convert(c, rec.get(c), int_cols, date_cols) for c in cols))
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"{table}: {cur.fetchone()[0]} 行 (本批 {len(rows)})")
    finally:
        conn.close()
    print(f"导入完成 {datetime.now():%H:%M:%S}")


if __name__ == "__main__":
    main()
