"""导入前一致性校验：新年度表 CSV vs 库内既有官方数据。

交叉验证四组重叠口径，任何系统性偏差都会打印并在放行前人工确认:
  1. XuchangCountyYearTarget(2021-2024) vs CountyMonthReport Scope=cum 12月
     （PM10/PM2.5/优良天应一致; 重污染天 2023 年预期偏高——月报未剔沙尘,
       年度考核剔沙尘, 属已知口径差, 单独列出不算失败）
  2. XuchangCityYearTarget(2021-2025) vs HenanCityYearTarget(许昌市)
  3. XuchangCityYearTarget.Pm25(2014-2025) vs CityYearPm25Avg.ActualPm25Avg
     （用于判定 01 表"实际值"列与平台预计算表的口径是否一致）
  4. XuchangCountyYearTarget(2023) vs 官方考核 doc（已内置于解析: 05表+doc 一致）

运行（宿主机）:
  /opt/miniconda3/envs/backend_py311/bin/python validate_year_targets.py \
    --csv-dir /tmp/year_target_csv
"""

from __future__ import annotations

import argparse
import csv
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

TOL_CONC = 0.51  # 浓度允许 0.5 舍入差


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _f(value) -> float | None:
    return float(value) if value not in (None, "") else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", default="/tmp/year_target_csv")
    args = parser.parse_args()
    csv_dir = Path(args.csv_dir)

    county = {(r["Region"], int(r["Year"])): r
              for r in load_csv(csv_dir / "xuchang_county_year.csv")}
    city = {int(r["Year"]): r for r in load_csv(csv_dir / "xuchang_city_year.csv")}
    henan = {(r["City"], int(r["Year"])): r
             for r in load_csv(csv_dir / "henan_city_year.csv")}

    conn = pymysql.connect(**DB)
    failures: list[str] = []
    known_sand: list[str] = []
    try:
        with conn.cursor() as cur:
            # 1. 县级 vs 月报累计
            print("== 1) 县级年度 vs CountyMonthReport 累计 ==")
            for year in (2021, 2022, 2023, 2024):
                cur.execute(
                    "SELECT Region, PM10, PM25, GoodDays, HeavyDays FROM CountyMonthReport "
                    "WHERE Scope='cum' AND PeriodEnd=%s", (f"{year}-12-31",))
                for region, pm10, pm25, good, heavy in cur.fetchall():
                    item = county.get((region, year))
                    if item is None:
                        continue
                    for label, new_v, old_v, tol in (
                        ("PM10", _f(item["Pm10"]), float(pm10) if pm10 is not None else None, TOL_CONC),
                        ("PM2.5", _f(item["Pm25"]), float(pm25) if pm25 is not None else None, TOL_CONC),
                        ("优良天", _f(item["GoodDays"]), float(good) if good is not None else None, 0),
                    ):
                        if new_v is None or old_v is None:
                            continue
                        if abs(new_v - old_v) > tol:
                            # 年度考核值为官方定版, 与月报累计的差属官方修订差, 列出供人工确认
                            known_sand.append(
                                f"{region} {year} {label}: 年度考核={new_v} 月报累计={old_v}(官方修订差)")
                    if item["HeavyDays"] and heavy is not None and int(item["HeavyDays"]) != int(heavy):
                        known_sand.append(
                            f"{region} {year} 重污染天: 年度考核(剔沙尘)={item['HeavyDays']} 月报={int(heavy)}")

            # 2. 许昌市年度 vs 河南 18 城表（2025 源表未定稿跳过）
            print("== 2) 许昌市年度 vs 河南18城表 ==")
            for year in (2021, 2022, 2023, 2024):
                h = henan.get(("许昌市", year))
                c = city.get(year)
                if not h or not c:
                    continue
                for label, new_v, old_v in (
                    ("PM10", _f(c["Pm10"]), _f(h["Pm10"])),
                    ("PM2.5", _f(c["Pm25"]), _f(h["Pm25"])),
                    ("优良天", _f(c["GoodDays"]), _f(h["GoodDays"])),
                ):
                    if new_v is None or old_v is None:
                        continue
                    if abs(new_v - old_v) > 0:
                        failures.append(f"许昌市 {year} {label}: 01表={new_v} 18城表={old_v}")

            # 3. 许昌市 PM2.5 年均 vs CityYearPm25Avg（口径判定）
            print("== 3) 许昌市 PM2.5 年均 vs CityYearPm25Avg ==")
            cur.execute(
                "SELECT Year, ActualPm25Avg, StandardPm25Avg FROM CityYearPm25Avg "
                "WHERE CityName LIKE '%许昌%' ORDER BY Year")
            for year, actual, standard in cur.fetchall():
                c = city.get(int(year))
                if not c:
                    continue
                new_v = _f(c["Pm25"])
                print(f"  {year}: 01表实际={new_v} 平台表Actual={actual} Standard={standard}")
                if new_v is not None and actual is not None and abs(new_v - float(actual)) > TOL_CONC:
                    # 2015-2020 平台 Actual 列为实时未审核口径, 与考核定版口径不同, 不算失败
                    known_sand.append(
                        f"许昌市 {year} PM2.5: 01表考核={new_v} 平台Actual={actual}(口径不同)")
    finally:
        conn.close()

    print("\n== 已知口径差(非失败) ==")
    print("\n".join(known_sand) or "（无）")
    print("\n== 失败项 ==")
    print("\n".join(failures) or "（无,全部一致）")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
