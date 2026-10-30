# -*- coding: utf-8 -*-
"""生成智能体平台放行账号名单（xlsx）。数据源：生产名册快照。"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

XLSX_SKILL_DIR = r"C:\Users\Administrator\.zcode\cli\plugins\cache\zcode-plugins-official\spreadsheets\0.2.0\skills\xlsx"
for sub in (XLSX_SKILL_DIR, os.path.join(XLSX_SKILL_DIR, "templates")):
    if sub not in sys.path:
        sys.path.insert(0, sub)

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from base import (
    setup_sheet, style_header_row, style_data_row,
    auto_fit_columns, auto_fit_row_heights,
    font_body, font_caption, align_text, align_number,
    PRIMARY, NEUTRAL_900,
)

ROSTER = r"M:\suyuan-guangdong\backend\backend_data_registry_guangdong\operation_access\roster.json"
OUT = r"M:\suyuan-guangdong\docs\运维账号放行名单_20261030.xlsx"

USERTYPE_LABEL = {
    "1": "省中心（局方）",
    "2": "技术支持",
    "3": "运维单位",
    "4": "现场检查",
    "5": "市级（局方）",
    "6": "数据复审",
}

data = json.load(open(ROSTER, encoding="utf-8"))
synced_utc = datetime.fromisoformat(data["synced_at"])
synced_local = synced_utc.astimezone(timezone(timedelta(hours=8)))
entries = [e for e in data["entries"] if e.get("login_id")]
by_login = {}
for e in entries:
    by_login[e["login_id"].strip().lower()] = e

allowed = sorted(
    (e for e in by_login.values() if e["decision"] == "allowed"),
    key=lambda e: (e["usertype"], e["department"], e["login_id"]),
)
blocked_count = sum(1 for e in by_login.values() if e["decision"] != "allowed")
allowed_count = len(allowed)
total_count = len(by_login)
type_counts = {}
dept_counts = {}
for e in allowed:
    type_counts[e["usertype"]] = type_counts.get(e["usertype"], 0) + 1
    dept = e["department"] or "（未填写）"
    dept_counts[dept] = dept_counts.get(dept, 0) + 1

wb = Workbook()

# ---------------------------------------------------------------- Sheet 1
ws = wb.active
ws.title = "放行账号名单"
headers = ["序号", "登录名", "姓名", "用户类型", "所属部门", "角色", "账户状态", "数据状态"]
last_col = len(headers) + 1

setup_sheet(ws, title="智能体平台放行账号名单（局方账户）", last_col=last_col)
ws.cell(row=3, column=2,
        value=f"数据来源：运维平台库 Operation_SC_GD（172.20.105.179）  ｜  "
              f"名册同步时间：{synced_local:%Y-%m-%d %H:%M}（北京时间）  ｜  "
              f"共放行 {allowed_count} 个账户")
ws.cell(row=3, column=2).font = font_caption()

for col_idx, header in enumerate(headers, start=2):
    ws.cell(row=4, column=col_idx, value=header)
style_header_row(ws, row_num=4, col_start=2, col_end=last_col)

for i, e in enumerate(allowed):
    row_num = 5 + i
    values = [
        i + 1,
        e["login_id"],
        e["display_name"],
        USERTYPE_LABEL.get(e["usertype"], f"未知（{e['usertype']}）"),
        e["department"],
        e["roles"],
        "启用" if e["status"] == "Enabled" else e["status"],
        "有效" if e.get("data_state", "1") == "1" else "已失效",
    ]
    for col_idx, value in enumerate(values, start=2):
        ws.cell(row=row_num, column=col_idx, value=value)
    style_data_row(ws, row_num=row_num, col_start=2, col_end=last_col, row_index=i)
    ws.cell(row=row_num, column=2).alignment = align_number()
    ws.cell(row=row_num, column=6).alignment = align_text()

note_row = 5 + len(allowed) + 1
ws.cell(row=note_row, column=2,
        value="说明：放行口径为局方账号（USERTYPE=1 省中心、5 市级），另含管理员与例外白名单；"
              "其余类型（运维单位、技术支持、现场检查、数据复审）一律拦截。名单随名册每 5 分钟自动同步。")
ws.cell(row=note_row, column=2).font = font_caption()
ws.merge_cells(start_row=note_row, start_column=2, end_row=note_row, end_column=last_col)

auto_fit_columns(ws, min_width=8, max_width=34, header_row=4, data_start_row=5)
auto_fit_row_heights(ws, header_row=4, data_start_row=5)

# ---------------------------------------------------------------- Sheet 2
ws2 = wb.create_sheet("统计与说明")
setup_sheet(ws2, title="统计与权限说明", last_col=6)

rows = [
    ("统计项", "数值", "说明"),
    ("有效登录名总数", total_count, "运维平台 SYS_USER 去重后的登录名"),
    ("放行账户数", allowed_count, "局方账号（省中心 + 市级）"),
    ("拦截账户数", blocked_count, "运维单位 / 技术支持 / 现场检查 / 数据复审及未知账号"),
    ("名册同步时间", f"{synced_local:%Y-%m-%d %H:%M}", "北京时间，每 5 分钟自动同步"),
]
for r, row in enumerate(rows, start=4):
    for c, value in enumerate(row, start=2):
        ws2.cell(row=r, column=c, value=value)
style_header_row(ws2, row_num=4, col_start=2, col_end=4)
for i, row in enumerate(rows[1:]):
    row_num = 5 + i
    style_data_row(ws2, row_num=row_num, col_start=2, col_end=4, row_index=i)
    ws2.cell(row=row_num, column=3).alignment = align_number()

start = 4 + len(rows) + 1
ws2.cell(row=start, column=2, value="按用户类型统计（放行账户）").font = font_caption()
hdr_row = start + 1
for c, header in enumerate(("用户类型", "账户数"), start=2):
    ws2.cell(row=hdr_row, column=c, value=header)
style_header_row(ws2, row_num=hdr_row, col_start=2, col_end=3)
type_order = [t for t in ("1", "5", "2", "3", "4", "6") if t in type_counts]
for i, t in enumerate(type_order):
    row_num = hdr_row + 1 + i
    ws2.cell(row=row_num, column=2, value=USERTYPE_LABEL.get(t, t))
    ws2.cell(row=row_num, column=3, value=type_counts[t]).alignment = align_number()
    style_data_row(ws2, row_num=row_num, col_start=2, col_end=3, row_index=i)

start2 = hdr_row + 1 + len(type_order) + 1
ws2.cell(row=start2, column=2, value="按所属部门统计（放行账户）").font = font_caption()
hdr_row2 = start2 + 1
for c, header in enumerate(("所属部门", "账户数"), start=2):
    ws2.cell(row=hdr_row2, column=c, value=header)
style_header_row(ws2, row_num=hdr_row2, col_start=2, col_end=3)
for i, (dept, count) in enumerate(sorted(dept_counts.items(), key=lambda kv: (-kv[1], kv[0]))):
    row_num = hdr_row2 + 1 + i
    ws2.cell(row=row_num, column=2, value=dept)
    ws2.cell(row=row_num, column=3, value=count).alignment = align_number()
    style_data_row(ws2, row_num=row_num, col_start=2, col_end=3, row_index=i)

rules_start = hdr_row2 + 1 + len(dept_counts) + 1
rules = [
    "权限说明",
    "1. 放行：USERTYPE=1（省中心）、5（市级）的局方账号；AUTH_OPERATION_ALLOWED_USERNAMES 例外名单与管理员账号无条件放行。",
    "2. 拦截：USERTYPE=2 技术支持、3 运维单位、4 现场检查、6 数据复审，以及名册同步成功后的未知账号。",
    "3. 同名冲突：登录名优先于显示名；同一登录名多条记录按活性取活账户（DATASTATE=1 → Enabled → 局方类型）。",
    "4. 拦截按请求生效，8 小时会话令牌不能绕过；被拒用户显示“无访问权限”页。",
    "5. 数据变化：运维平台侧调整账号类型/单位后，最迟 5 分钟自动生效，无需重启服务。",
]
for i, line in enumerate(rules):
    cell = ws2.cell(row=rules_start + i, column=2, value=line)
    cell.font = font_body()
    cell.alignment = align_text()
    if i > 0:
        ws2.merge_cells(start_row=rules_start + i, start_column=2,
                        end_row=rules_start + i, end_column=6)

auto_fit_columns(ws2, min_width=10, max_width=46, header_row=4, data_start_row=5)
auto_fit_row_heights(ws2, header_row=4, data_start_row=5)

wb.properties.creator = "Z.ai"
wb.properties.title = "智能体平台放行账号名单"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
wb.save(OUT)
print(f"OK {OUT}")
print(f"allowed={allowed_count} blocked={blocked_count} total={total_count}")
print("type_counts:", type_counts)
