# openpyxl 代码配方（code-recipes）

配合 design-rules.md 的令牌使用；产出必须经 `artifact_path()`。

## 1. 设计令牌

```python
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

HEADER_FILL = PatternFill("solid", fgColor="F8FAFC")
HEADER_FONT = Font(name="Noto Sans CJK SC", bold=True, size=11)
BODY_FONT = Font(name="Noto Sans CJK SC", size=11)
THIN = Side(style="thin", color="E2E8F0")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center")
```

## 2. 建表模板（表头 + 冻结 + 筛选 + 列宽）

```python
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

def build_sheet(workbook, title, header, rows, col_widths=None, number_formats=None):
    ws = workbook.create_sheet(title)
    ws.append(header)
    for cell in ws[1]:
        cell.font, cell.fill, cell.border, cell.alignment = HEADER_FONT, HEADER_FILL, BORDER, CENTER
    ws.row_dimensions[1].height = 20
    for row in rows:
        ws.append(row)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font, cell.border = BODY_FONT, BORDER
            cell.alignment = LEFT
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    # 列宽：显式设置（中文按 2 宽估算）
    widths = col_widths or [
        max(12, max(_display_width(r[i]) for r in [header, *rows]) + 2)
        for i in range(len(header))
    ]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    # 数字格式：{列号(1-based): 格式}
    for col, fmt in (number_formats or {}).items():
        for cell in ws.iter_cols(min_col=col, max_col=col, min_row=2):
            for c in cell: c.number_format = fmt
    return ws

def _display_width(value):
    return sum(2 if ord(ch) > 127 else 1 for ch in str(value or ""))

wb = Workbook(); wb.remove(wb.active)
build_sheet(wb, "站点明细", ["站点", "PM2.5 浓度 (μg/m³)", "达标"],
            [["图书馆", 34.2, "是"], ["开发区", 41.8, "否"]],
            number_formats={2: "0.0"})
```

## 3. 汇总行（公式，不硬编码）

```python
last = ws.max_row + 1
ws.cell(row=last, column=1, value="全市均值")
ws.cell(row=last, column=2, value=f"=ROUND(AVERAGE(B2:B{last-1}),1)")
ws.cell(row=last, column=2).number_format = "0.0"
for cell in ws[last]:
    cell.font = Font(name="Noto Sans CJK SC", bold=True, size=11)
```

## 4. 修改现有文件（保样式）

```python
from openpyxl import load_workbook
wb = load_workbook(path)          # 不用 pandas.to_excel（会清样式/公式/合并）
ws = wb["站点明细"]
ws["D2"] = "=B2*1.15"             # 直接改单元格，样式保留
wb.save(path)
```

## 5. 保存与读回核验（data_manual 继承）

```python
out = artifact_path("许昌市站点台账_20261107.xlsx")
wb.save(out)
# 读回核验：表/关键单元格/行列数
check = load_workbook(out)
assert check.sheetnames == ["站点明细"] and check["站点明细"]["B2"].value is not None
```

## 6. 常见坑

- 站点代码/编号列写成数字 → 前导零丢失：先设 `number_format="@"` 再赋值。
- 日期字符串与真日期混用：统一 `datetime.date` 对象 + `YYYY-MM-DD` 格式。
- 合并单元格做数据区 → 排序筛选失效：只允许装饰性合并（如大标题行）。
- 大表逐 cell 设样式慢：用 `iter_rows` 批量；>5 万行考虑分 sheet。
