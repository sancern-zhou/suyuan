"""县市区空气质量月报（剔除沙尘）解析入库脚本。

来源: /root/suyuan/data/县市区空气质量数据月报.zip（2021-01 ~ 2026-09 每月一份，
每份含"1-N月累计"+"当月"两张上下叠放的表，每个指标带上年同期对照列）。

产物: 县市区 × 月 统一宽表 CSV（Scope=month 当月 / cum 累计），字段与
DataCrawler.CountyMonthReport 表一一对应。2020 年全年数值取自 2021 年文件的
"上年同期"列（SourceCol=prior）；同年月份以当年列（SourceCol=cur）优先，
prior 仅用于填补没有当年文件的月份（目前即 2020 全年）。

运行（宿主机 conda 环境需 xlrd，纯解析无库依赖）:
  PYTHONPATH=/tmp/opencode/pylibs \
  /opt/miniconda3/envs/backend_py311/bin/python parse_county_month_reports.py \
    --zip /root/suyuan/data/县市区空气质量数据月报.zip \
    --out /tmp/opencode/county_month_report.csv

注意口径: 官方剔除沙尘统计；魏都区/开发区/东城区/示范区/建安区为国家平台数据，
鄢陵县/襄城县/禹州市/长葛市为省平台数据（文件内"注"行原文，随年份略有措辞变化）。
2026 年起文件另含望田路/市一国控站点列，非县市区，解析时跳过。
"""

from __future__ import annotations

import argparse
import calendar
import re
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

# 指标表头前缀 → 库列（前缀匹配，须把长前缀放前面）
METRIC_COLUMNS = [
    ("PM10", "PM10"),
    ("PM2.5", "PM25"),
    ("SO2", "SO2"),
    ("NO2", "NO2"),
    ("CO", "CO"),
    ("O3", "O3_8H"),
    ("优良天", "GoodDays"),
    ("重污染天", "HeavyDays"),
    ("综合指数", "CompositeIndex"),
]
METRIC_ORDER = ["PM10", "PM25", "SO2", "NO2", "CO", "O3_8H", "GoodDays", "HeavyDays", "CompositeIndex"]

REGION_TYPES = {
    "许昌市": "city",
    "魏都区": "urban",
    "开发区": "urban",
    "东城区": "urban",
    "示范区": "urban",
    "建安区": "urban",
    "鄢陵县": "county",
    "襄城县": "county",
    "禹州市": "county",
    "长葛市": "county",
}
SKIP_REGIONS = {"望田路", "市一中"}  # 2026 起混入的国控站点列，非县市区

FILENAME_RE = re.compile(r"^(\d{4})年及同期(\d{1,2})月")
TITLE_KEYWORD = "环境空气质量数据"


def _to_number(value) -> float:
    """xls 数值/字符串统一转 float；'-'、'—'、空等按缺测处理。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "—", "–", "/", "无"}:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def parse_sheet(df: pd.DataFrame, file_year: int, month: int, source_file: str) -> list[dict]:
    """解析单个 Sheet 内上下叠放的多张表，返回行字典列表。"""
    rows: list[dict] = []
    n = len(df)
    title_idx = [
        i for i in range(n)
        if isinstance(df.iat[i, 0], str) and TITLE_KEYWORD in df.iat[i, 0]
    ]
    for ti in title_idx:
        title = str(df.iat[ti, 0])
        scope = "cum" if re.match(r"^1-\d+", title.strip()) else "month"
        # 表头三行: 指标名（合并单元格需前向填充）/ 年份 / 期间
        metric_row, year_row = df.iloc[ti + 1], df.iloc[ti + 2]
        col_metrics: dict[int, tuple[str, int]] = {}  # 列号 → (库列, 年份偏移 0=当年 1=上年)
        current_metric = None
        for col in range(1, df.shape[1]):
            header = metric_row.iat[col]
            if isinstance(header, str) and header.strip():
                name = header.strip()
                current_metric = next(
                    (db for prefix, db in METRIC_COLUMNS if name.startswith(prefix)), None
                )
            if current_metric is None:
                continue
            year_val = year_row.iat[col]
            if pd.isna(year_val):
                continue
            try:
                offset = int(str(year_val).strip()[:4]) - file_year
            except ValueError:
                continue
            if offset in (0, -1):  # 0=当年列, -1=上年同期列
                col_metrics[col] = (current_metric, offset)
        if not col_metrics:
            continue
        # 数据行: 指标行下方三行起到"注"或空行
        for ri in range(ti + 4, n):
            region = df.iat[ri, 0]
            if not isinstance(region, str) or not region.strip():
                break
            region = region.strip()
            if region.startswith("注") or TITLE_KEYWORD in region:
                break
            if region in SKIP_REGIONS or region not in REGION_TYPES:
                continue
            row = {
                "Region": region,
                "RegionType": REGION_TYPES[region],
                "DataMonth": f"{file_year:04d}-{month:02d}-01",
                "PeriodEnd": f"{file_year:04d}-{month:02d}-{calendar.monthrange(file_year, month)[1]:02d}",
                "Scope": scope,
                "SourceFile": source_file,
            }
            for col, (db_col, offset) in col_metrics.items():
                row[db_col if offset == 0 else f"_{db_col}"] = _to_number(df.iat[ri, col])
            row["SourceCol"] = "cur"
            rows.append(row)
    return rows


def collapse_prior(rows: list[dict]) -> list[dict]:
    """当年列优先；把上年同期列拆成独立年份行（仅保留当年文件覆盖不到的月份）。"""
    metric_rows: list[dict] = []
    covered: set[tuple] = set()
    for row in rows:
        cur = {"SourceCol": "cur", **{k: v for k, v in row.items() if not k.startswith("_")}}
        metric_rows.append(cur)
        covered.add((row["Region"], row["Scope"], row["DataMonth"]))
        prior = {
            "Region": row["Region"],
            "RegionType": row["RegionType"],
            "Scope": row["Scope"],
            "SourceFile": row["SourceFile"],
            "SourceCol": "prior",
            **{db_col: float("nan") for db_col in METRIC_ORDER},
        }
        year, month, _ = row["DataMonth"].split("-")
        prior_year = int(year) - 1
        prior["DataMonth"] = f"{prior_year:04d}-{month}-01"
        prior["PeriodEnd"] = f"{prior_year:04d}-{month}-{row['PeriodEnd'][-2:]}"
        for db_col in METRIC_ORDER:
            prior[db_col] = row.get(f"_{db_col}", float("nan"))
        metric_rows.append(prior)

    frame = pd.DataFrame(metric_rows)
    frame["DataMonth"] = pd.to_datetime(frame["DataMonth"])
    frame = frame.sort_values(
        by=["Region", "Scope", "DataMonth", "SourceCol"],
        key=lambda s: s.map({"cur": 0, "prior": 1}) if s.name == "SourceCol" else s,
    )
    deduped = frame.drop_duplicates(subset=["Region", "Scope", "DataMonth"], keep="first")
    return deduped.sort_values(["Scope", "Region", "DataMonth"]).to_dict("records")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True, help="县市区空气质量数据月报.zip 路径")
    parser.add_argument("--out", required=True, help="输出 CSV 路径")
    args = parser.parse_args()

    all_rows: list[dict] = []
    with tempfile.TemporaryDirectory(), zipfile.ZipFile(args.zip) as zf:
        for info in zf.infolist():
            if not info.filename.endswith(".xls"):
                continue
            # zip 内文件名为 GBK 编码（decode 乱码时按 cp936 还原）
            try:
                name = info.filename.encode("cp437").decode("gbk")
            except (UnicodeEncodeError, UnicodeDecodeError):
                name = info.filename
            matched = FILENAME_RE.match(Path(name).name)
            if not matched:
                continue
            file_year, month = int(matched.group(1)), int(matched.group(2))
            with zf.open(info) as fh:
                df = pd.read_excel(fh, sheet_name="Sheet1", header=None, engine="xlrd")
            all_rows.extend(parse_sheet(df, file_year, month, Path(name).name))

    rows = collapse_prior(all_rows)
    columns = (
        ["Region", "RegionType", "DataMonth", "PeriodEnd", "Scope", "SourceCol", "SourceFile"]
        + METRIC_ORDER
    )
    out = pd.DataFrame(rows)[columns]
    out["DataMonth"] = out["DataMonth"].dt.strftime("%Y-%m-%d")
    out.to_csv(args.out, index=False, encoding="utf-8-sig")

    # 校验摘要
    print(f"总行数: {len(out)}（Region×Scope×月）")
    summary = out.groupby(["Scope", out["DataMonth"].str[:4]]).size().unstack(fill_value=0)
    print(summary.to_string())
    covered = out[out["SourceCol"] == "cur"].groupby(out["DataMonth"].str[:4]).size()
    prior = out[out["SourceCol"] == "prior"].groupby(out["DataMonth"].str[:4]).size()
    print("当年列覆盖年份:", dict(covered))
    print("同期列补缺年份:", dict(prior))
    dup = out.duplicated(subset=["Region", "Scope", "DataMonth"]).sum()
    print(f"重复键: {dup}")
    spot = out[
        (out["Region"] == "魏都区") & (out["Scope"] == "month")
        & (out["DataMonth"].isin(["2020-01-01", "2021-01-01", "2024-06-01"]))
    ][["DataMonth", "SourceCol", "PM10", "PM25", "GoodDays", "CompositeIndex"]]
    print("抽样(魏都区/当月, 2021-01 预期 PM10=126.6 优良天=12 综合指数=7.12):")
    print(spot.to_string(index=False))


if __name__ == "__main__":
    main()
