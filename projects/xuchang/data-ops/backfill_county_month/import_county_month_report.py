"""把 parse_county_month_reports.py 产出的 CSV 导入 DataCrawler.CountyMonthReport。

幂等：按 (Region, Scope, DataMonth) upsert，可重复执行。

运行（宿主机）:
  /opt/miniconda3/envs/backend_py311/bin/python import_county_month_report.py \
    --csv /tmp/opencode/county_month_report.csv
"""

from __future__ import annotations

import argparse
from datetime import date, datetime

import pymysql

DB = {
    "host": "127.0.0.1",
    "port": 13307,
    "user": "root",
    "password": "1V4MIHsQGZIbJpec",
    "database": "DataCrawler",
    "charset": "utf8mb4",
}

COLUMNS = ["Region", "RegionType", "DataMonth", "PeriodEnd", "Scope",
           "PM10", "PM25", "SO2", "NO2", "CO", "O3_8H",
           "GoodDays", "HeavyDays", "CompositeIndex", "SourceCol", "SourceFile"]

UPSERT = """
INSERT INTO CountyMonthReport ({cols})
VALUES ({ph})
ON DUPLICATE KEY UPDATE {upd}
""".format(
    cols=", ".join(COLUMNS),
    ph=", ".join(["%s"] * len(COLUMNS)),
    upd=", ".join(f"{c}=VALUES({c})" for c in COLUMNS[2:]),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()

    import csv

    rows: list[tuple] = []
    with open(args.csv, encoding="utf-8-sig", newline="") as fh:
        for rec in csv.DictReader(fh):
            row = []
            for col in COLUMNS:
                value = (rec.get(col) or "").strip()
                if col in ("DataMonth", "PeriodEnd"):
                    row.append(date.fromisoformat(value))
                elif col in ("GoodDays", "HeavyDays"):
                    row.append(int(float(value)) if value else None)
                elif col in ("PM10", "PM25", "SO2", "NO2", "CO", "O3_8H", "CompositeIndex"):
                    row.append(float(value) if value else None)
                else:
                    row.append(value or None)
            rows.append(tuple(row))

    conn = pymysql.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.executemany(UPSERT, rows)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT Scope, COUNT(*) FROM CountyMonthReport GROUP BY Scope")
            print("导入完成:", cur.fetchall(), f"(输入 {len(rows)} 行, {datetime.now():%H:%M:%S})")
            nan_free = cur.execute(
                "SELECT COUNT(*) FROM CountyMonthReport "
                "WHERE SourceCol='prior' AND DataMonth < '2020-01-01'"
            )
            print("异常 prior 行(应=0):", nan_free)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
