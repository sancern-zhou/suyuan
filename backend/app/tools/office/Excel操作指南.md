# Excel 表格操作指南

## 概述

本指南介绍 Excel 文件（.xlsx）的读取、创建、编辑和图表制作方法。

**核心理念**：使用标准库（pandas + openpyxl），避免自定义辅助函数。

---

## 核心原则

### 1. 标准库优先

✅ **使用**：
- `pandas.read_excel()` - 读取数据
- `openpyxl` - 创建/编辑工作簿（支持公式）
- `openpyxl.chart` - 创建图表

❌ **不要使用**：
- 自定义辅助函数（如 `read_excel()`, `create_excel_report()`）

### 2. 公式优先

**始终使用 Excel 公式而不是在 Python 中计算后硬编码**

❌ **错误做法**：
```python
# 在 Python 中计算后硬编码
total = df['Sales'].sum()
sheet['B10'] = total  # 硬编码 5000
```

✅ **正确做法**：
```python
# 使用 Excel 公式
sheet['B10'] = '=SUM(B2:B9)'  # 动态计算
```

**理由**：使用公式可以让 Excel 保持动态可更新，当源数据变化时会自动重新计算。

---

## 读取 Excel

### 基本读取

```python
import pandas as pd

# 读取第一个工作表
df = pd.read_excel('file.xlsx')

# 读取所有工作表（返回字典）
all_sheets = pd.read_excel('file.xlsx', sheet_name=None)

# 读取指定工作表
df = pd.read_excel('file.xlsx', sheet_name='Sheet2')

# 查看数据
print(df.head())        # 前5行
print(df.info())        # 列信息
print(df.describe())    # 统计描述
```

### 处理大型文件

```python
# 只读取特定列
df = pd.read_excel('file.xlsx', usecols=['A', 'C', 'E'])

# 指定数据类型
df = pd.read_excel('file.xlsx', dtype={'id': str})

# 处理日期
df = pd.read_excel('file.xlsx', parse_dates=['date_column'])

# 分块读取大文件
for chunk in pd.read_excel('large_file.xlsx', chunksize=1000):
    process(chunk)
```

---

## 创建和编辑 Excel

### 创建新工作簿

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

# 创建工作簿
wb = Workbook()
ws = wb.active
ws.title = '数据表'

# 添加数据
ws['A1'] = '日期'
ws['B1'] = '数值'
ws.append(['2026-01-01', 100])

# 添加公式
ws['C2'] = '=SUM(B2:B10)'
ws['C3'] = '=AVERAGE(B2:B10)'
ws['C4'] = '=(B4-B3)/B3'  # 增长率

# 格式化
ws['A1'].font = Font(bold=True)
ws['A1'].fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
ws['A1'].alignment = Alignment(horizontal='center')

# 保存
wb.save('output.xlsx')
```

### 编辑现有工作簿

```python
from openpyxl import load_workbook

# 加载现有文件
wb = load_workbook('existing.xlsx')
sheet = wb.active  # 或 wb['SheetName']

# 修改单元格
sheet['A1'] = '新值'

# 插入/删除行列
sheet.insert_rows(2)
sheet.delete_cols(3)

# 遍历所有工作表
for sheet_name in wb.sheetnames:
    sheet = wb[sheet_name]
    print(f"工作表: {sheet_name}")

# 保存
wb.save('modified.xlsx')
```

### 使用 openpyxl 的注意事项

- 单元格索引从 1 开始（row=1, column=1 是 A1）
- 使用 `data_only=True` 读取计算后的值：`load_workbook('file.xlsx', data_only=True)`
- ⚠️ 警告：如果用 `data_only=True` 打开后保存，公式会被永久替换为值
- 对于大文件：读取时用 `read_only=True`，写入时用 `write_only=True`

---

## 公式重算

openpyxl 创建的文件包含公式但未计算值，需要使用 LibreOffice 重算。

### 使用 recalc 脚本

```bash
# 重算所有公式
python backend/scripts/recalc.py output.xlsx

# 指定超时时间（秒）
python backend/scripts/recalc.py output.xlsx 30
```

### 返回结果

```json
{
  "status": "success",
  "total_errors": 0,
  "total_formulas": 42,
  "error_summary": {}
}
```

### 错误类型

脚本会扫描以下 Excel 错误：
- `#REF!` - 无效的单元格引用
- `#DIV/0!` - 除以零
- `#VALUE!` - 错误的数据类型
- `#N/A` - 值不可用
- `#NAME?` - 无法识别的公式名称
- `#NULL!` - 无效的交集运算符
- `#NUM!` - 数值错误

---

## 数据验证和清理

### 检查缺失值

```python
import pandas as pd

df = pd.read_excel('file.xlsx')

# 缺失值统计
missing = df.isnull().sum()
missing_percent = (missing / len(df)) * 100

print("缺失值统计:")
for col in df.columns:
    if df[col].isnull().any():
        print(f"{col}: {missing[col]} ({missing_percent[col]:.2f}%)")
```

### 数据类型转换

```python
# 转换为数值
df['列名'] = pd.to_numeric(df['列名'], errors='coerce')

# 转换为日期
df['日期列'] = pd.to_datetime(df['日期列'], errors='coerce')

# 删除重复行
df = df.drop_duplicates()

# 填充缺失值
df.fillna(0)  # 用 0 填充
df.fillna(method='ffill')  # 前向填充
```

---

## 常见任务示例

### 任务1：汇总多个工作表

```python
import pandas as pd

# 读取所有工作表
all_sheets = pd.read_excel('report.xlsx', sheet_name=None)

# 合并所有数据
combined = pd.concat(all_sheets.values(), ignore_index=True)

# 保存
combined.to_excel('combined.xlsx', index=False)
```

### 任务2：数据透视表

```python
import pandas as pd

df = pd.read_excel('sales.xlsx')

# 创建数据透视表
pivot = df.pivot_table(
    values='销售额',
    index='地区',
    columns='产品',
    aggfunc='sum'
)

# 保存
pivot.to_excel('pivot_report.xlsx')
```

### 任务3：条件格式化

```python
from openpyxl import load_workbook
from openpyxl.styles import PatternFill
from openpyxl.formatting.rule import ColorScaleRule

wb = load_workbook('data.xlsx')
ws = wb.active

# 添加条件格式规则
rule = ColorScaleRule(
    start_type='min', start_color='63BE7B',
    mid_type='percentile', mid_value=50, mid_color='FFEB84',
    end_type='max', end_color='F8696B'
)
ws.conditional_formatting.add('B2:B100', rule)

wb.save('formatted.xlsx')
```

### 任务4：批量处理多个文件

```python
import pandas as pd
from pathlib import Path

# 处理目录下所有 Excel 文件
for file in Path('data/').glob('*.xlsx'):
    df = pd.read_excel(file)

    # 数据处理
    summary = df.describe()

    # 保存摘要
    output_file = f'output/{file.stem}_summary.xlsx'
    summary.to_excel(output_file)
```

---

## Excel 图表最佳实践

### 核心原则

**图表必须动态**：直接引用原始数据范围，不要硬编码到临时列。

❌ **错误**：
```python
# 硬编码到临时列（静态）
for i, val in enumerate(values):
    ws.cell(row=i, column=10).value = val
data = Reference(ws, min_col=10, min_row=2, max_row=...)
```

✅ **正确**：
```python
# 直接引用原始数据（动态）
data = Reference(ws, min_col=3, min_row=2, max_row=max_row)
chart.add_data(data)
```

### 完整示例

```python
from openpyxl import load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList

wb = load_workbook('file.xlsx')
ws = wb.active
max_row = ws.max_row

# 创建图表
chart = BarChart()
chart.type = 'col'
chart.style = 10
chart.title = '各省份PM2.5累计平均值'
chart.y_axis.title = 'PM2.5浓度 (μg/m³)'

# 数据标签
chart.dataLabels = DataLabelList()
chart.dataLabels.showVal = True

# ✅ 关键：直接引用原始数据范围
data = Reference(ws, min_col=3, min_row=2, max_row=max_row)
categories = Reference(ws, min_col=1, min_row=2, max_row=max_row)
chart.add_data(data)
chart.set_categories(categories)

# 清除旧图表并添加新图表
for chart_obj in ws._charts:
    ws._charts.remove(chart_obj)
ws.add_chart(chart, 'E2')

wb.save('file.xlsx')
```

---

## 最佳实践

### 1. 公式验证清单

- [ ] 测试 2-3 个示例引用，确保它们拉取正确的值
- [ ] 确认 Excel 列映射正确（例如：第 64 列 = BL，不是 BK）
- [ ] 记住 Excel 行从 1 开始（DataFrame 第 5 行 = Excel 第 6 行）

### 2. 常见错误

- [ ] **NaN 处理**：用 `pd.notna()` 检查空值
- [ ] **右侧列**：财年数据通常在第 50+ 列
- [ ] **多个匹配**：搜索所有出现位置，不只是第一个
- [ ] **除以零**：在公式中使用 `/` 之前检查分母（#DIV/0!）
- [ ] **错误引用**：验证所有单元格引用指向预期的单元格（#REF!）
- [ ] **跨表引用**：使用正确格式（Sheet1!A1）链接工作表

### 3. 公式测试策略

- [ ] **从小开始**：在广泛应用之前，先在 2-3 个单元格上测试公式
- [ ] **验证依赖**：检查公式中引用的所有单元格都存在
- [ ] **测试边界情况**：包含零、负数和非常大的值

---

## 故障排查

### 问题：找不到文件

```
FileNotFoundError: [Errno 2] No such file or directory: 'file.xlsx'
```

**解决**：检查文件路径是否正确，使用绝对路径

---

### 问题：公式显示为文本

```
单元格显示 =SUM(A1:A10) 而不是计算结果
```

**解决**：使用 LibreOffice 重算：`python backend/scripts/recalc.py file.xlsx`

---

### 问题：数据类型不匹配

```
ValueError: cannot convert to numeric
```

**解决**：使用 `pd.to_numeric(column, errors='coerce')` 强制转换

---

### 问题：公式错误

```
返回 {"status": "errors_found", "error_summary": {"#REF!": {...}}}
```

**解决**：检查 error_summary 中的错误位置，修复单元格引用

---

## 相关资源

- [pandas 文档](https://pandas.pydata.org/docs/reference/api/pandas.read_excel.html)
- [openpyxl 文档](https://openpyxl.readthedocs.io/)
- Anthropic xlsx Skill: https://github.com/anthropics/skills/tree/main/skills/xlsx
