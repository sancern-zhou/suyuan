"""河南省环境空气质量月报（PDF 附表）解析入库脚本。

来源: /root/suyuan/data/05省环境质量月报.zip（10 期: 2025年12期 + 2026年1~9期）。
每期 32 页，含 6 张附表（fitz 表格抽取）:
  附表1/2: 全省 + 19 省辖市（区）当月 / 1-N月累计
  附表3/4: 88 个省辖市所辖区 当月 / 累计
  附表5/6: 101 个县（市）当月 / 累计

指标随季节/表型变化（供暖季 2025-12 无 O3 列；区/县表无重污染天列），
列布局由表头分组合数自适应，见 _COLUMN_LAYOUT。

产物 CSV 对应 DataCrawler.ProvinceMonthReport。
运行（宿主机，需 PyMuPDF）:
  /opt/miniconda3/envs/backend_py311/bin/python parse_province_month_reports.py \
    --zip /root/suyuan/data/05省环境质量月报.zip \
    --out /tmp/opencode/province_month_report.csv
"""

from __future__ import annotations

import argparse
import re
import tempfile
import zipfile
from pathlib import Path

import fitz

# 省级报告用简称，统一为库内全称（与 Ssfb*/CountyMonthReport 对齐）
CITY_SHORT_TO_FULL = {
    "郑州": "郑州市", "开封": "开封市", "洛阳": "洛阳市", "平顶山": "平顶山市",
    "安阳": "安阳市", "鹤壁": "鹤壁市", "新乡": "新乡市", "焦作": "焦作市",
    "濮阳": "濮阳市", "许昌": "许昌市", "漯河": "漯河市", "三门峡": "三门峡市",
    "南阳": "南阳市", "商丘": "商丘市", "信阳": "信阳市", "周口": "周口市",
    "驻马店": "驻马店市", "济源": "济源市", "航空港": "郑州航空港区",
}

METRIC_COLUMNS = [
    "PM10", "PM10_YoY", "PM25", "PM25_YoY", "O3", "O3_YoY",
    "GoodDays", "GoodDays_Change", "GoodDays_Ratio", "GoodDays_RatioChg",
    "HeavyDays", "HeavyDays_Change", "HeavyDays_Ratio", "HeavyDays_RatioChg",
    "CompositeIndex", "CompositeIndex_YoY",
]

# 各分组下的列顺序（按表内出现顺序）——与源表结构一一对应
_GROUP_COLUMNS = {
    "PM25": ["PM25", "PM25_YoY"],
    "PM10": ["PM10", "PM10_YoY"],
    "O3": ["O3", "O3_YoY"],
    "GOOD": ["GoodDays", "GoodDays_Change", "GoodDays_Ratio", "GoodDays_RatioChg"],
    "HEAVY": ["HeavyDays", "HeavyDays_Change", "HeavyDays_Ratio", "HeavyDays_RatioChg"],
    "INDEX": ["CompositeIndex", "CompositeIndex_YoY"],
    # 区/县表：综合指数在优良天之前，且各自只有 2 列
    "GOOD_SHORT": ["GoodDays", "GoodDays_Change"],
    "INDEX_SHORT": ["CompositeIndex", "CompositeIndex_YoY"],
}

FILENAME_RE = re.compile(r"(\d{4})\s*年.*?第\s*(\d+)\s*期")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _num(cell) -> float:
    """从单元格提取数值（正则剥离 '\n'、误并的表头字等）；无值返回 nan。"""
    if cell is None:
        return float("nan")
    m = _NUM_RE.search(str(cell).replace(",", ""))
    return float(m.group()) if m else float("nan")


def _norm_header(text) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _detect_layout(header_row) -> tuple[str, list[str]]:
    """由表头分组行推断 (level, 列映射)，列映射按分组顺序展开。

    level: city / district / county。分组识别: PM2.5、PM10、O3、优良天、
    重度及以上污染天、综合指数；区/县表无重污染天，且综合指数在优良天前。
    """
    cells = [_norm_header(c) for c in header_row]
    has_district = any("所辖区" in c for c in cells)
    has_county = any("县市" in c or "县（市）" in c for c in cells)
    has_o3 = any(re.fullmatch(r"O3", c) or c.startswith("O3") for c in cells)

    level = "district" if has_district else ("county" if has_county else "city")
    # 分组顺序
    if level == "city":
        groups = ["PM25", "PM10"] + (["O3"] if has_o3 else []) + ["GOOD", "HEAVY", "INDEX"]
    else:
        groups = ["PM25", "PM10"] + (["O3"] if has_o3 else []) + ["INDEX_SHORT", "GOOD_SHORT"]
    columns: list[str] = []
    for group in groups:
        columns.extend(_GROUP_COLUMNS[group])
    return level, columns


def _parse_table(rows: list[list], file_year: int, month: int, scope: str,
                 source_file: str) -> list[dict]:
    """解析单张附表（可能跨页合并后的行列表）。"""
    # 找表头行（含"环境空气质量"/'序号' 的第一个样式行）与数据行
    header_idx = next(
        (i for i, r in enumerate(rows)
         if r and any("PM" in _norm_header(c) for c in r if c)),
        None,
    )
    if header_idx is None:
        return []
    level, column_map = _detect_layout(rows[header_idx])
    # 序号列之后的名称列数：city=1（市名），区/县=2（市名+区/县名）
    name_cols = 1 if level == "city" else 2
    numeric_start = 1 + name_cols

    out: list[dict] = []
    for row in rows[header_idx + 1:]:
        if not row:
            continue
        first = _norm_header(row[0])
        if first in ("", "序号") or "省辖市" in first or "PM" in first:
            continue
        # 数据行的序号列可能是数字，或全省/全省平均类行
        is_province = first.startswith("全省")
        if not is_province and not re.fullmatch(r"\d+", first):
            continue
        if is_province:
            # 2025-12 期有两条全省平均（除济源、港区 / 含济源、除港区），
            # 统一：含济源不含港区口径记为 '全省'，另一口径保留原文标签。
            region = "全省" if "含济源" in first or first == "全省" else "全省(除济源港区)"
            city = region
            level_row = "province"
        else:
            names = [str(row[i]).strip() for i in range(1, 1 + name_cols)]
            city = CITY_SHORT_TO_FULL.get(names[0], names[0])
            region = names[-1]
            level_row = level
            if level_row == "city":
                region = city  # 市级行的区域名即全称市名
        values = row[numeric_start:]
        record = {
            "Level": level_row,
            "City": city,
            "RegionName": region,
            "DataMonth": f"{file_year:04d}-{month:02d}-01",
            "Scope": scope,
            "SourceFile": source_file,
        }
        # 校验数值列数（源表列数 = 已识别分组列数）
        numeric = values[: len(column_map)]
        if len(numeric) < len(column_map):
            raise ValueError(
                f"{source_file} 附表列数不足: 识别 {len(column_map)} 列, 实际 {len(numeric)}"
            )
        for column, cell in zip(column_map, numeric):
            record[column] = _num(cell)
        out.append(record)
    return out


def parse_pdf(path: Path) -> list[dict]:
    matched = FILENAME_RE.search(path.name)
    if not matched:
        raise ValueError(f"文件名无法识别年份/期数: {path.name}")
    file_year, month = int(matched.group(1)), int(matched.group(2))
    doc = fitz.open(path)
    current: int | None = None
    titles: dict[int, str] = {}
    collected: dict[int, list[list]] = {}
    for page in doc:
        text = page.get_text()
        title_match = re.search(r"附表\s*(\d)\s*\n([^\n]*)", text)
        if title_match and ("环境空气质量" in text[:300] or "主要指标" in text[:300]):
            current = int(title_match.group(1))
            titles.setdefault(current, title_match.group(2).strip())
        tables = page.find_tables().tables
        if current is None or not tables:
            continue
        for table in tables:
            extracted = table.extract()
            if not extracted:
                continue
            # 跨页续表的表头重复出现：合并进同一附表的数据行里
            collected.setdefault(current, []).extend(extracted)
    rows: list[dict] = []
    for section in sorted(collected):
        scope = "cum" if re.search(r"1-\d+\s*月", titles.get(section, "")) else "month"
        rows.extend(_parse_table(collected[section], file_year, month, scope, path.name))
    doc.close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import csv

    all_rows: list[dict] = []
    with tempfile.TemporaryDirectory(), zipfile.ZipFile(args.zip) as zf:
        for info in zf.infolist():
            if not info.filename.lower().endswith(".pdf"):
                continue
            try:
                name = info.filename.encode("cp437").decode("gbk")
            except (UnicodeEncodeError, UnicodeDecodeError):
                name = info.filename
            with zf.open(info) as fh:
                data = fh.read()
            local = Path(tempfile.gettempdir()) / Path(name).name
            local.write_bytes(data)
            all_rows.extend(parse_pdf(local))
            local.unlink()

    columns = ["Level", "City", "RegionName", "DataMonth", "Scope"] + METRIC_COLUMNS + ["SourceFile"]
    with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    # 校验摘要
    from collections import Counter
    level_month = Counter((r["Scope"], r["Level"], r["DataMonth"][:7]) for r in all_rows)
    print(f"总行数: {len(all_rows)}")
    for (scope, level, datamonth), count in sorted(level_month.items()):
        print(f"  {datamonth} {scope:5s} {level:8s}: {count}")


if __name__ == "__main__":
    main()
