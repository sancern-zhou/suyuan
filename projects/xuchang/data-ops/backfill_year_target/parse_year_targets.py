"""解析《00重要基础数据.zip》官方年度统计表为 CSV，供 import_year_targets.py 入库。

产出四张表的数据（年度粒度，官方定版口径，非明细聚合）:
  xuchang_city_year.csv   -> DataCrawler.XuchangCityYearTarget  许昌市 2015-2026 目标 vs 实际
  xuchang_county_year.csv -> DataCrawler.XuchangCountyYearTarget 许昌 10 县市区 2020-2025
  henan_city_year.csv     -> DataCrawler.HenanCityYearTarget     河南 18 地市 2021-2025
  rank168_monthly.csv     -> DataCrawler.Rank168CityMonthly      168 重点城市 2026 逐月+累计

源文件（/root/suyuan/data/00重要基础数据_extracted/，data/ 目录不入 git）:
  01_xuchang_city_year.xlsx        原件即 xlsx（zip 内 01许昌市2011-2025...xlsx）
  03_henan_city_year.xlsx          .et 经 LibreOffice 转换
  04_county_heavy_days_sandfree.xlsx .et 经 LibreOffice 转换（剔沙尘重污染天）
  05_xuchang_county_year.xlsx      .xls 经 LibreOffice 转换
  06_rank168_monthly.xlsx          原件即 xlsx（许昌市2026年1-7月168城市排名统计.xlsx）

.et/.xls 转换命令（宿主机）:
  HOME=/tmp soffice --headless --convert-to xlsx --outdir <dir> <源文件>

口径说明:
  - 01 表"实际完成情况"取国家网口径（实际值列）；"APP数据"两列（省发布平台口径）
    不入库，避免同年度双浓度口径。
  - 05 表许昌市 2025 年 PM10 目标为"/"（市定 70 不下达县区），存 NULL 并在 Remark 注明。
  - 县级重污染天以剔沙尘口径为准：05 表与剔沙尘表重叠年份必须一致（parse 时校验），
    2020/2021 重污染天仅剔沙尘表有。
  - 空单元格一律存 NULL，不填 0。

运行（宿主机，需 openpyxl）:
  /opt/miniconda3/envs/backend_py311/bin/python parse_year_targets.py \
    --src /root/suyuan/data/00重要基础数据_extracted --outdir /tmp/year_target_csv
"""

from __future__ import annotations

import argparse
import calendar
import csv
import re
from datetime import date
from pathlib import Path

import openpyxl

# 县市区归属（与 CountyMonthReport.RegionType 同口径）
COUNTY_REGION_TYPE = {
    "许昌市": "city",
    "魏都区": "urban", "建安区": "urban", "示范区": "urban", "开发区": "urban", "东城区": "urban",
    "禹州市": "county", "长葛市": "county", "鄢陵县": "county", "襄城县": "county",
}

SRC01 = "00重要基础数据.zip/01许昌市2011-2025年环境空气质量指标统计表.xlsx"
SRC03 = "00重要基础数据.zip/03河南省2021-2025年各城市空气质量目标完成情况统计表.et"
SRC04 = "00重要基础数据.zip/2020-2025县市区重污染天剔沙尘后(1).et"
SRC05 = "00重要基础数据.zip/05各县（市、区）2021年-2025年空气质量目标完成情况统计表.xls"
SRC06 = "00重要基础数据.zip/许昌市2026年1-7月168城市排名统计.xlsx"

# 省考核表与市口径表的已知数值差（原值入库, Remark 注明）
REMARK_OVERRIDES = {
    ("许昌市", 2022): "省考核表PM2.5为47,市口径(01表/月报累计)为46,两表并存",
}


def _num(value) -> tuple[float | None, str]:
    """数值解析；'/'（市定不下达）返回 (None, note)；'70 (市定)' 返回 (70.0, note)。"""
    if value is None:
        return None, ""
    text = str(value).strip()
    if not text or text in {"——", "/", "-"}:
        return None, "" if not text or text == "-" else "市定目标不下达" if text == "/" else ""
    note = ""
    if "市定" in text:
        note = "PM10目标为市定(未下达县区)"
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None, note
    return float(m.group()), note


def _flag(value) -> str | None:
    text = "" if value is None else str(value).strip()
    return text if text in {"是", "否"} else None


def _int(value) -> int | None:
    """容忍 '#N/A' 等非数值单元格。"""
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


def _year(value) -> int | None:
    m = re.match(r"^(20\d{2})年$", str(value or "").strip())
    return int(m.group(1)) if m else None


def parse_city_year(src_dir: Path) -> list[dict]:
    """01 表 sheet「2015-2025」: 年度|目标PM10/PM2.5/优良天/重污染天|实际PM10/APP/PM2.5/APP/
    SO2/NO2/CO/O3/优良天/重污染天/臭氧超标天。只取国家网口径实际值，APP 两列丢弃。"""
    wb = openpyxl.load_workbook(src_dir / "01_xuchang_city_year.xlsx", read_only=True, data_only=True)
    ws = wb["2015-2025"]
    rows: list[dict] = []
    for row in ws.iter_rows(min_row=4, max_col=16, values_only=True):
        year = _year(row[0])
        if year is None:  # 跳过降幅汇总行
            continue
        pm10_target, note = _num(row[1])
        pm10, note_app = _num(row[5])
        pm25, _ = _num(row[7])
        so2, _ = _num(row[9])
        no2, _ = _num(row[10])
        co, _ = _num(row[11])
        o3, _ = _num(row[12])
        good_days, _ = _num(row[13])
        heavy_days, _ = _num(row[14])
        o3_exceed, _ = _num(row[15])
        remarks = [n for n in (note, note_app) if n]
        rows.append({
            "Year": year,
            "Pm10Target": pm10_target, "Pm25Target": _num(row[2])[0],
            "GoodDaysTarget": _num(row[3])[0], "HeavyDaysTarget": _num(row[4])[0],
            "Pm10": pm10, "Pm25": pm25, "So2": so2, "No2": no2, "Co": co, "O3": o3,
            "GoodDays": int(good_days) if good_days is not None else None,
            "HeavyDays": int(heavy_days) if heavy_days is not None else None,
            "O3ExceedDays": int(o3_exceed) if o3_exceed is not None else None,
            "Remark": ";".join(remarks), "SourceFile": SRC01,
        })
    return rows


def _norm_city(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    if text.startswith("济源"):
        return "济源市"
    return text if text.endswith("市") else text + "市"


def parse_henan_city_year(src_dir: Path) -> list[dict]:
    """03 表按年度 sheet 结构各异，逐 sheet 定列解析（2023年新 sheet 不规范弃用）。"""
    wb = openpyxl.load_workbook(src_dir / "03_henan_city_year.xlsx", read_only=True, data_only=True)
    rows: list[dict] = []

    def base(city: str, year: int) -> dict:
        return {"City": _norm_city(city), "Year": year, "SourceFile": SRC03,
                "Remark": "", "CompletedCount": None,
                "Pm10Target": None, "Pm10": None, "Pm10Completed": None,
                "Pm25Target": None, "Pm25": None, "Pm25Completed": None,
                "GoodDaysTarget": None, "GoodDays": None, "GoodDaysRatioTarget": None,
                "GoodDaysRatio": None, "GoodDaysCompleted": None,
                "HeavyDaysTarget": None, "HeavyDays": None, "HeavyDaysRatioTarget": None,
                "HeavyDaysRatio": None, "HeavyDaysCompleted": None,
                "O3ExceedDaysTarget": None, "O3ExceedDays": None, "O3ExceedOver": None}

    def fill_triple(row: dict, cells, kind: str, ratio_actual: bool) -> None:
        """cells = (目标/实际, 完成情况) 三元组; ratio_actual 时实际列为比例%。"""
        prefix = {"good": "GoodDays", "heavy": "HeavyDays"}[kind]
        if ratio_actual:
            row[f"{prefix}Ratio"] = _num(cells[1])[0]
        else:
            row[f"{prefix}Target"] = _num(cells[0])[0]
            row[prefix] = int(_num(cells[1])[0]) if _num(cells[1])[0] is not None else None
        row[f"{prefix}Completed"] = _flag(cells[2])

    def fill_pm(row: dict, cells) -> None:
        row["Pm10Target"], row["Pm10"], row["Pm10Completed"] = _num(cells[0])[0], _num(cells[1])[0], _flag(cells[2])
        row["Pm25Target"], row["Pm25"], row["Pm25Completed"] = _num(cells[3])[0], _num(cells[4])[0], _flag(cells[5])

    # 2021年: 1地市 2-4 PM10 5-7 PM2.5 8-10 优良天(天数) 11 完成项数; 数据行 4-21
    ws = wb["2021年"]
    for row in ws.iter_rows(min_row=4, max_row=21, values_only=True):
        city = _norm_city(row[0])
        if not city:
            continue
        item = base(city, 2021)
        fill_pm(item, row[1:7])
        fill_triple(item, row[7:10], "good", ratio_actual=False)
        item["CompletedCount"] = _int(row[10])
        rows.append(item)

    # 2022年: 1序号 2城市 3-5 PM10 6-8 PM2.5 9-11 优良天(天数) 12-14 重污染天(天数)
    #          15-17 O3超标(目标/实际/超出) 18 完成项数; 数据行 4-22
    # 2023年: 同 2022 布局，但优良天/重污染天目标空、实际为比例%; 数据行 4-21
    for sheet, year, ratio in (("2022年", 2022, False), ("2023年", 2023, True)):
        ws = wb[sheet]
        for row in ws.iter_rows(min_row=4, max_row=21 if year == 2023 else 22, values_only=True):
            city = _norm_city(row[1])
            if not city:
                continue
            item = base(city, year)
            if (city, year) in REMARK_OVERRIDES:
                item["Remark"] = REMARK_OVERRIDES[(city, year)]
            fill_pm(item, row[2:8])
            fill_triple(item, row[8:11], "good", ratio_actual=ratio)
            fill_triple(item, row[11:14], "heavy", ratio_actual=ratio)
            item["O3ExceedDaysTarget"] = _num(row[14])[0]
            item["O3ExceedDays"] = _num(row[15])[0]
            item["O3ExceedOver"] = _num(row[16])[0]
            item["CompletedCount"] = _int(row[17])
            rows.append(item)

    # 2024年: 1序号 2省辖市 3-5 PM10 6-8 PM2.5 9优良天比例(小数) 10优良天目标(天)
    #   11优良天实际(天) 12优良天完成 13重污染天比例(小数) 14重污染天目标 15重污染天实际
    #   16重污染天完成 17完成项数; 数据行 3-20
    ws = wb["2024年"]
    for row in ws.iter_rows(min_row=3, max_row=20, values_only=True):
        city = _norm_city(row[1])
        if not city:
            continue
        item = base(city, 2024)
        item["Pm10Target"], item["Pm10"], item["Pm10Completed"] = _num(row[2])[0], _num(row[3])[0], _flag(row[4])
        item["Pm25Target"], item["Pm25"], item["Pm25Completed"] = _num(row[5])[0], _num(row[6])[0], _flag(row[7])
        if row[8] is not None:
            item["GoodDaysRatioTarget"] = round(float(row[8]) * 100, 1)
        item["GoodDaysTarget"] = _num(row[9])[0]
        item["GoodDays"] = int(row[10]) if row[10] is not None else None
        item["GoodDaysCompleted"] = _flag(row[11])
        if row[12] is not None:
            item["HeavyDaysRatioTarget"] = round(float(row[12]) * 100, 1)
        item["HeavyDaysTarget"] = _num(row[13])[0]
        item["HeavyDays"] = int(row[14]) if row[14] is not None else None
        item["HeavyDaysCompleted"] = _flag(row[15])
        item["CompletedCount"] = int(row[16]) if row[16] is not None else None
        rows.append(item)

    # 2025年: 比 2024 少 PM10完成列, 共 16 列; 数据行 3-20
    ws = wb["2025年"]
    for row in ws.iter_rows(min_row=3, max_row=20, values_only=True):
        city = _norm_city(row[1])
        if not city:
            continue
        item = base(city, 2025)
        item["Pm10Target"], item["Pm10"] = _num(row[2])[0], _num(row[3])[0]
        item["Pm25Target"], item["Pm25"], item["Pm25Completed"] = _num(row[4])[0], _num(row[5])[0], _flag(row[6])
        item["GoodDaysRatio"] = round(float(row[7]) * 100, 1) if row[7] is not None else None
        item["GoodDaysTarget"] = _num(row[8])[0]
        item["GoodDays"] = int(row[9]) if row[9] is not None else None
        item["GoodDaysCompleted"] = _flag(row[10])
        item["HeavyDaysRatio"] = round(float(row[11]) * 100, 1) if row[11] is not None else None
        item["HeavyDaysTarget"] = _num(row[12])[0]
        item["HeavyDays"] = int(row[13]) if row[13] is not None else None
        item["HeavyDaysCompleted"] = _flag(row[14])
        item["CompletedCount"] = _int(row[15])
        item["Remark"] = "源表2025年sheet未定稿(实际值列疑沿用2024草稿),实际值勿引用,以许昌市年度表为准"
        rows.append(item)
    return rows


def parse_county_year(src_dir: Path) -> list[dict]:
    """05 表 2021-2025 年度 sheet（行 4-13: 序号|区域|PM10目标/实际/完成|PM2.5|优良天|重污染天）
    + 剔沙尘表 2020-2025 重污染天（目标/实际）合并；重叠值必须一致。"""
    wb = openpyxl.load_workbook(src_dir / "05_xuchang_county_year.xlsx", read_only=True, data_only=True)
    merged: dict[tuple[str, int], dict] = {}

    for sheet_name, year in (("2021年", 2021), ("2022年", 2022), ("2023年", 2023),
                             ("2024年", 2024), ("2025年", 2025)):
        ws = wb[[s for s in wb.sheetnames if s.strip() == sheet_name][0]]
        for row in ws.iter_rows(min_row=4, max_row=13, values_only=True):
            region = str(row[1] or "").strip()
            if region not in COUNTY_REGION_TYPE:
                continue
            pm10_target, note = _num(row[2])
            item = {
                "Region": region, "RegionType": COUNTY_REGION_TYPE[region], "Year": year,
                "Pm10Target": pm10_target, "Pm10": _num(row[3])[0], "Pm10Completed": _flag(row[4]),
                "Pm25Target": _num(row[5])[0], "Pm25": _num(row[6])[0], "Pm25Completed": _flag(row[7]),
                "GoodDaysTarget": _num(row[8])[0], "GoodDays": int(_num(row[9])[0]) if _num(row[9])[0] is not None else None,
                "GoodDaysCompleted": _flag(row[10]),
                "HeavyDaysTarget": None, "HeavyDays": None, "HeavyDaysCompleted": None,
                "Remark": note, "SourceFile": SRC05,
            }
            heavy_target, heavy_actual = _num(row[11])[0], _num(row[12])[0]
            item["HeavyDaysTarget"] = int(heavy_target) if heavy_target is not None else None
            item["HeavyDays"] = int(heavy_actual) if heavy_actual is not None else None
            item["HeavyDaysCompleted"] = _flag(row[13])
            merged[(region, year)] = item

    # 剔沙尘表: 行 4-13, 每年 3 列(目标/实际/完成), 2020-2025
    wb4 = openpyxl.load_workbook(src_dir / "04_county_heavy_days_sandfree.xlsx", read_only=True, data_only=True)
    ws = wb4["Sheet1"]
    conflicts: list[str] = []
    for row in ws.iter_rows(min_row=4, max_row=13, values_only=True):
        region = str(row[1] or "").strip()
        if region not in COUNTY_REGION_TYPE:
            continue
        for idx, year in enumerate((2020, 2021, 2022, 2023, 2024, 2025)):
            target, actual = _num(row[2 + idx * 3])[0], _num(row[3 + idx * 3])[0]
            item = merged.get((region, year))
            from_sandfree = item is None
            if item is None:
                item = {
                    "Region": region, "RegionType": COUNTY_REGION_TYPE[region], "Year": year,
                    "Pm10Target": None, "Pm10": None, "Pm10Completed": None,
                    "Pm25Target": None, "Pm25": None, "Pm25Completed": None,
                    "GoodDaysTarget": None, "GoodDays": None, "GoodDaysCompleted": None,
                    "HeavyDaysTarget": None, "HeavyDays": None, "HeavyDaysCompleted": None,
                    "Remark": "", "SourceFile": SRC04,
                }
                merged[(region, year)] = item
            # 冲突仲裁: 05表与官方 2023 年度考核 doc/Sheet1 一致, 以 05表为准并注明
            if item["HeavyDays"] is not None and actual is not None and item["HeavyDays"] != int(actual):
                conflicts.append(
                    f"{region} {year}: 05表={item['HeavyDays']} 剔沙尘表={int(actual)}(取05表,已注明)")
                item["Remark"] = ";".join(
                    x for x in (item["Remark"], f"剔沙尘表为{int(actual)},以05表为准") if x)
            if item["HeavyDaysTarget"] is not None and target is not None and item["HeavyDaysTarget"] != int(target):
                conflicts.append(f"{region} {year} 目标: 05表={item['HeavyDaysTarget']} 剔沙尘表={int(target)}")
            if item["HeavyDays"] is None and actual is not None:
                item["HeavyDays"] = int(actual)
                item["Remark"] = ";".join(x for x in (item["Remark"], "重污染天取自剔沙尘表") if x)
            if item["HeavyDaysTarget"] is None and target is not None:
                item["HeavyDaysTarget"] = int(target)
            if not from_sandfree:
                item["SourceFile"] = f"{SRC05}+{SRC04}"

    if conflicts:
        print("重污染天两表不一致(已按 05表 定版):")
        print("\n".join(conflicts))
    return sorted(merged.values(), key=lambda x: (x["Region"], x["Year"]))


def parse_rank168(src_dir: Path) -> list[dict]:
    """168 表 1-7月 sheet: 城市|当月综合指数/排名/PM2.5/排名|1-N月累计同4列; 数据行 3-170。"""
    wb = openpyxl.load_workbook(src_dir / "06_rank168_monthly.xlsx", read_only=True, data_only=True)
    rows: list[dict] = []
    month_match = re.compile(r"^(\d{1,2})月$")
    for sheet_name in wb.sheetnames:
        m = month_match.match(sheet_name.strip())
        if not m:
            continue
        month = int(m.group(1))
        ws = wb[sheet_name]
        for row in ws.iter_rows(min_row=3, values_only=True):
            city = str(row[0] or "").strip()
            if not city:
                continue
            day = date(2026, month, 1)
            for period_type, cells in (("month", row[1:5]), ("cum", row[5:9])):
                ci, ci_rank, pm25, pm25_rank = (cells + (None,) * 4)[:4]
                if ci is None and pm25 is None:
                    continue
                last_day = calendar.monthrange(2026, month)[1]
                rows.append({
                    "City": city, "PeriodType": period_type, "DataMonth": day.isoformat(),
                    "PeriodEnd": date(2026, month, last_day).isoformat()
                                 if period_type == "cum" else "",
                    "PeriodLabel": f"{month}月" if period_type == "month" else f"1-{month}月",
                    "CompositeIndex": _num(ci)[0],
                    "CompositeIndexRank": _int(ci_rank),
                    "Pm25": _num(pm25)[0],
                    "Pm25Rank": _int(pm25_rank),
                    "SourceFile": SRC06,
                })
    return rows


CITY_COLS = ["Year", "Pm10Target", "Pm25Target", "GoodDaysTarget", "HeavyDaysTarget",
             "Pm10", "Pm25", "So2", "No2", "Co", "O3", "GoodDays", "HeavyDays",
             "O3ExceedDays", "Remark", "SourceFile"]
COUNTY_COLS = ["Region", "RegionType", "Year", "Pm10Target", "Pm10", "Pm10Completed",
               "Pm25Target", "Pm25", "Pm25Completed", "GoodDaysTarget", "GoodDays",
               "GoodDaysCompleted", "HeavyDaysTarget", "HeavyDays", "HeavyDaysCompleted",
               "Remark", "SourceFile"]
HENAN_COLS = ["City", "Year", "Pm10Target", "Pm10", "Pm10Completed", "Pm25Target", "Pm25",
              "Pm25Completed", "GoodDaysTarget", "GoodDays", "GoodDaysRatioTarget",
              "GoodDaysRatio", "GoodDaysCompleted", "HeavyDaysTarget", "HeavyDays",
              "HeavyDaysRatioTarget", "HeavyDaysRatio", "HeavyDaysCompleted",
              "O3ExceedDaysTarget", "O3ExceedDays", "O3ExceedOver", "CompletedCount",
              "Remark", "SourceFile"]
RANK_COLS = ["City", "PeriodType", "DataMonth", "PeriodEnd", "PeriodLabel", "CompositeIndex",
             "CompositeIndexRank", "Pm25", "Pm25Rank", "SourceFile"]


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{path.name}: {len(rows)} 行")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="/root/suyuan/data/00重要基础数据_extracted")
    parser.add_argument("--outdir", default="/tmp/year_target_csv")
    args = parser.parse_args()
    src_dir, out_dir = Path(args.src), Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    write_csv(out_dir / "xuchang_city_year.csv", parse_city_year(src_dir), CITY_COLS)
    write_csv(out_dir / "xuchang_county_year.csv", parse_county_year(src_dir), COUNTY_COLS)
    write_csv(out_dir / "henan_city_year.csv", parse_henan_city_year(src_dir), HENAN_COLS)
    write_csv(out_dir / "rank168_monthly.csv", parse_rank168(src_dir), RANK_COLS)


if __name__ == "__main__":
    main()
