# Office 技能指导文档

> **MANDATORY**: 遇到 Office 任务时，必须先阅读本文档


## 🚀 快速开始

**工具列表**：
- "unpack_office": "解包Office文件为XML"
- "pack_office": "打包XML为Office文件"
- "word_edit": "Word文档结构化编辑"
- "accept_word_changes": "接受Word文档所有修订"

**Word 编辑决策**：
```
所有 Word 编辑 → word_edit（推荐）
```

**绝对禁止**：
```
❌ 不要用 edit_file 编辑 Word XML（会失败）
```

**Excel/PPT**：
```
Excel → execute_python（使用 openpyxl、pandas 等库）
读取PPT → read_pptx
分析PPT模板 → analyze_pptx_template
基于模板生成PPT → create_pptx_from_template
编辑现有PPT → edit_pptx
创建PPT → create_pptx（PptxGenJS，可编辑PPTX）
复杂自定义PPT处理 → execute_python（使用 python-pptx 库）
```

**核心原则**：
```
1. 编辑前先阅读文档
2. 优先使用专用工具
3. 避免手动 XML 编辑
```

---

## 🔍 编辑前阅读策略（MANDATORY）

**编辑前必须先阅读了解内容！**

### unpack_office + read_file  
```
✅ 先解包文件后再阅读
```

---

## 📤 编辑完成通知（MANDATORY）

**编辑完成后必须告知用户文件位置！**

### word_edit 编辑

**内容格式要求**：
```
❌ 不要使用 Markdown 格式（如 # 标题、**加粗**、- 列表）
✅ 使用纯文本格式，符合文档原有规范
✅ 表达流畅、自然、易读，不要过于结构化，按段落生成
```

**完成后告知用户**：
```
"编辑完成！文件已保存到：[实际文件路径]"
```

### 解包后编辑流程

```
步骤 1：解包
unpack_office(path="[用户提供的文件路径]")

步骤 2：提示用户
"文档已解包到：[解包目录路径]
XML 文件位于：[解包目录]/word/document.xml
请告诉我编辑完成后，我将重新打包为 Word 文档。"

步骤 3：等待用户确认修改完成

步骤 4：重新打包（`word_edit` 编辑完成后不需要手动打包，会自动完成打包）
pack_office(input_dir="[解包目录]", output_file="[输出文件路径]")

步骤 5：告知用户
"编辑完成！文件已保存到：[输出文件路径]"
```

**重要**：
- 解包后必须提示用户编辑位置
- 等待用户确认修改完成
- 重新打包后告知用户文件地址

**⚠️ 已解包文档的处理**：
- 如果解包后需用 `word_edit` 编辑 → 传**原 .docx 路径**（工具自动解包/打包）
- **不要**把解包目录传给 `word_edit`

---


## 📋 必读清单

```
阅读检查：
- [ ] 我已经阅读文档内容了吗？
- [ ] 我确认目标文本的格式了吗？

工具选择：
- [ ] 我知道用什么工具和参数了吗？

内容格式：
- [ ] 避免使用 Markdown 格式了吗？
- [ ] 使用纯文本、表达流畅自然了吗？


编辑完成：
- [ ] 编辑后告知用户文件位置了吗？
- [ ] 解包编辑后重新打包了吗？

安全检查：
- [ ] 我避免使用 edit_file 编辑 Word XML 了吗？

任何 "否" → 向上查看对应章节
```

---

## 1. word_edit - 结构化编辑

复杂 Word 编辑：替换段落、插入、删除

**有效操作类型**：
```
replace_text        → search, replace
replace_paragraph   → contains, content（或 new_content）
insert_after        → marker, content
insert_before       → marker, content
delete_paragraph    → contains
```

**核心参数**：
```
path: 文件路径（必需）
operation: 操作类型（必需）
根据操作类型提供对应参数
```

**重要说明**：
- **marker参数**：使用精确的段落文本，而不是Markdown格式（如## 标题）。
  - ✅ 正确：`marker="4.小结"` 或 `marker="小结"`
  - ❌ 错误：`marker="## 4.小结"`

**示例**：
```
替换段落：word_edit(path="[文件路径]", operation="replace_paragraph", contains="旧内容", new_content="新内容")
插入：word_edit(path="[文件路径]", operation="insert_after", marker="4.小结", content="新段落")
删除：word_edit(path="[文件路径]", operation="delete_paragraph", contains="待删除内容")
```

---

## 2. Excel 操作说明

### ⚠️ 重要：辅助函数使用规范

**execute_python 工具已自动注入Excel辅助函数，可直接使用，无需 import**

```python
# ✅ 正确：直接使用辅助函数
result = read_excel_with_preview("file.xlsx")
result = edit_excel_data("file.xlsx", {"A1": "新值"})
result = merge_excel_with_charts(files, "output.xlsx")

# ❌ 错误：不要 import 辅助函数
from app.tools.office.office_skills import merge_excel_with_charts  # 会报错
```

**说明**：
- 辅助函数（`read_excel_with_preview`、`edit_excel_data`、`merge_excel_with_charts`）已自动注入到代码环境中
- 直接调用即可，不需要也不应该 import
- 这些函数在 execute_python 代码执行前已自动添加到用户代码前面

---

所有Excel操作请使用 `execute_python` 工具，配合以下库：

**推荐库**：
- **openpyxl** - Excel文件读写（.xlsx格式）
- **pandas** - 数据处理和Excel读写
- **xlsxwriter** - Excel文件写入（支持格式化）

---

### ⚠️ 重要：保留图表和格式的 Excel 操作规范

**所有 Excel 操作（读取/修改）都会自动生成前端预览**

#### 📖 读取 Excel（推荐使用辅助函数）

```python
# 使用辅助函数读取并自动生成预览
result = read_excel_with_preview("file.xlsx")
print(result["message"])  # "成功读取 Excel 文件，共 100 行 x 10 列"
print(result["data"])     # 前20行数据
print(result["columns"])  # 列名
# ✅ 自动生成前端预览
```

**读取参数**：
- `file_path`: Excel 文件路径（必需）
- `sheet_name`: 工作表名（可选，默认活动工作表）
- `head_rows`: 读取前几行（可选，默认20行）

---

#### ✏️ 修改 Excel（保留图表和格式）

**修改现有 Excel 文件时，必须使用以下方法保留图表和格式**

#### ❌ 错误做法（会丢失图表和格式）

```python
# 错误：pandas.to_excel() 会重写整个文件，丢失所有图表和格式
import pandas as pd
df = pd.read_excel("file.xlsx")
df.to_excel("file.xlsx")  # ❌ 图表和格式全部丢失
```

#### ✅ 正确做法（保留图表和格式）

```python
# 正确：使用 openpyxl 直接修改单元格，保留图表
import openpyxl
wb = openpyxl.load_workbook("file.xlsx")
ws = wb.active
ws["A1"] = "新值"  # 只修改单元格
ws["B2"] = 85      # 修改数据
wb.save("file.xlsx")  # ✅ 图表和格式自动保留
```

#### 使用辅助函数（推荐）

```python
# 使用辅助函数自动处理并生成预览
result = edit_excel_data("file.xlsx", {
    "A1": "城市",
    "B1": "AQI",
    "A2": "北京",
    "B2": 85
})
# 返回: {"success": True, "updated_count": 4, "file_path": "..."}
# ✅ 自动生成前端预览
```

#### 合并多个Excel文件（保留图表和格式）⭐

```python
# 合并多个文件到一个工作簿（保留所有图表和格式）
files = [
    '/tmp/会商文件/全国各省份PM2.5累计平均.xlsx',
    '/tmp/会商文件/全国各省份PM10累计平均.xlsx',
    '/tmp/会商文件/全国各省份NO2累计平均.xlsx',
    '/tmp/会商文件/全国各省份O3累计平均.xlsx',
    '/tmp/会商文件/全国各省份AQI累计平均.xlsx'
]

result = merge_excel_with_charts(files, '/tmp/会商文件/汇总.xlsx')

# 返回
# {"success": True, "merged_count": 5, "message": "成功合并 5 个文件（图表和格式已保留）"}
# ✅ 跨平台，保留图表和格式，自动生成前端预览
```

**原理**：
- 复制第一个文件作为基础（保留原图表）
- 手动复制其他文件的sheet（内容+样式+图表）
- 适用于：Windows、Linux、Mac

#### 批量修改多个单元格

```python
# 批量修改，保留图表
import openpyxl
wb = openpyxl.load_workbook("file.xlsx")
ws = wb.active

# 批量更新
updates = {
    "A1": "城市",
    "B1": "AQI",
    "A2": "北京",
    "B2": 85,
    "A3": "上海",
    "B3": 92
}

for cell, value in updates.items():
    ws[cell] = value

wb.save("file.xlsx")  # ✅ 图表保留
```

#### 创建新文件（不涉及图表保留）

```python
# 创建新文件可以使用 pandas
import pandas as pd
df = pd.DataFrame({
    '城市': ['广州', '深圳'],
    'AQI': [85, 72]
})
df.to_excel('new_file.xlsx', index=False)
```

---

**常用场景**：

```python
# 读取Excel（用于数据分析）
import pandas as pd
df = pd.read_excel('/home/xckj/suyuan/backend_data_registry/data.xlsx')

# 分析数据
df_filtered = df[df['AQI'] > 100]

# ⚠️ 如果是修改原文件：用 openpyxl
import openpyxl
wb = openpyxl.load_workbook('/home/xckj/suyuan/backend_data_registry/data.xlsx')
ws = wb.active
ws["A1"] = "更新后的值"
wb.save('/home/xckj/suyuan/backend_data_registry/data.xlsx')

# ✅ 如果是保存新文件：可以用 pandas
df_filtered.to_excel('/home/xckj/suyuan/backend_data_registry/output.xlsx', index=False)
```

---

## 3. PPT 操作说明

### 3.1 读取 PPT

优先使用 `read_pptx` 工具，直接提取每页文本、表格、图片元数据和备注，并可自动生成PDF预览。

```text
read_pptx(path="演示文稿.pptx", include_notes=true, include_images=true, export_images=true)
```

### 3.2 创建 PPT

### 3.2 分析 PPT 模板

当用户提供现有PPT作为模板，优先使用 `analyze_pptx_template` 获取模板地图，再决定是否新建或后续编辑。

```text
analyze_pptx_template(path="template.pptx", include_layouts=true, write_report=true)
```

返回内容包括：

```text
slides[].classification        → 页面类型推断
slides[].layout                → 使用的版式名称/索引
slides[].placeholders          → 占位符类型、位置、当前文本
slides[].replaceable_slots     → 可替换槽位，包括 text/image/table/chart
slides[].pictures/tables/charts → 图片、表格、图表结构
report_path                    → template_map.json
```

模板化生成或编辑时，先根据 `replaceable_slots` 做内容映射，不要直接猜测 XML 位置。

### 3.3 基于模板生成 PPT

当用户要保留已有模板样式，只替换模板中的内容，使用 `create_pptx_from_template`。

推荐流程：

```text
1. analyze_pptx_template(path="template.pptx")
2. 根据返回的 replaceable_slots 组织 replacements
3. create_pptx_from_template(template_path="template.pptx", replacements={...}, quality="standard")
```

`replacements` 使用 slot_id 映射：

```json
{
  "s001_slot001": "新的标题",
  "s002_slot006": [["指标", "值"], ["AQI", "85"]],
  "s003_slot009": {"type": "image", "path": "backend/backend_data_registry/images/photo.png"}
}
```

当前支持：

```text
text / placeholder → 替换文本
table              → 填充现有表格单元格
image              → 按原槽位位置替换图片
```

注意：`create_pptx_from_template` 只负责从模板复制并填充内容；如果需要对已有PPT做删除页、重排页或局部文本替换，使用 `edit_pptx`。

### 3.4 编辑 PPT

当用户要求修改现有PPT，优先使用 `edit_pptx`，并在复杂替换前先用 `read_pptx` 或 `analyze_pptx_template` 确认页码和 slot_id。

支持操作：

```text
replace_text   → 全局或指定页替换文本
replace_slot   → 按 analyze_pptx_template 返回的 slot_id 替换文本/表格/图片
delete_slides  → 删除指定页，页码从 1 开始
reorder_slides → 重排全部页面，order 必须包含当前全部页码
```

示例：

```json
{
  "path": "backend/backend_data_registry/presentations/report.pptx",
  "operations": [
    {"type": "replace_text", "old_text": "旧结论", "new_text": "新结论"},
    {"type": "delete_slides", "slides": [2]},
    {"type": "reorder_slides", "order": [2, 1]}
  ],
  "output_file": "backend/backend_data_registry/presentations/report_edited.pptx",
  "quality": "standard"
}
```

按 slot 编辑：

```json
{
  "path": "backend/backend_data_registry/presentations/template_filled.pptx",
  "replacements": {
    "s001_slot001": "更新后的标题",
    "s002_slot006": [["指标", "值"], ["AQI", "85"]]
  }
}
```

### 3.5 创建 PPT

优先使用 `create_pptx` 工具。该工具使用 PptxGenJS 生成可编辑的 `.pptx`，适合一步生成正式演示文稿。

主题字段使用固定合同：

```text
primary, secondary, accent, text, muted, bg, surface, line, headFontFace, bodyFontFace
```

颜色使用 6 位 hex，传 `#2563EB` 或 `2563EB` 都可以，工具会统一清洗为 `2563EB`。不要使用 8 位 hex 透明色、渐变、动画或 Unicode 项目符号；列表内容传纯文本数组，工具会使用 PptxGenJS 原生 bullet。

常用 slide 类型：

```text
title, section, bullets, text, two_column, table, image, image_text, chart, quote,
toc, summary, comparison, timeline, process, metrics
```

质量参数：

```text
quality="draft"    → 只生成PPTX
quality="standard" → 生成后渲染PDF/PNG并生成montage/report
quality="strict"   → 额外执行渲染级溢出检测
```

示例：

```json
{
  "title": "项目汇报",
  "theme": {
    "primary": "2563EB",
    "secondary": "0F766E",
    "accent": "DC2626",
    "text": "1F2937",
    "bg": "FFFFFF",
    "headFontFace": "Microsoft YaHei",
    "bodyFontFace": "Microsoft YaHei"
  },
  "slides": [
    {"type": "title", "title": "项目汇报", "subtitle": "2026年"},
    {"type": "bullets", "title": "核心结论", "bullets": ["结论一", "结论二"]},
    {"type": "table", "title": "指标对比", "table": [["指标", "数值"], ["AQI", "85"]]}
  ],
  "output_file": "backend/backend_data_registry/presentations/report.pptx"
}
```

### 3.6 复杂自定义处理

复杂的局部编辑、特殊模板处理、非常规版式可使用 `execute_python` 工具，配合 **python-pptx** 库：

### 3.7 验证 PPT

交付前建议使用 `validate_pptx`。它会将PPTX渲染为PDF/PNG，生成montage总览图，并检查空页、形状越界、渲染级溢出和字体信息。渲染转换支持直接PPTX转PDF失败后的ODP fallback。

```text
validate_pptx(path="backend/backend_data_registry/presentations/report.pptx", expected_fonts=["Microsoft YaHei"])
```

`create_pptx` 也支持 `run_validation=true` 或 `quality="standard"/"strict"`，可在生成后直接返回验证报告。

**推荐库**：
- **python-pptx** - PPT文件读写和编辑

**常用场景**：

```python
# 创建PPT文件
from pptx import Presentation

prs = Presentation()
title_slide = prs.slides.add_slide(prs.slide_layouts[0])
title = title_slide.shapes.title
title.text = "演示标题"

prs.save('/home/xckj/suyuan/backend_data_registry/presentation.pptx')
```

```python
# 读取和编辑PPT
from pptx import Presentation

prs = Presentation('/home/xckj/suyuan/backend_data_registry/presentation.pptx')

# 访问第一张幻灯片
slide = prs.slides[0]

# 添加文本框
left = top = width = height = Inches(1)
textbox = slide.shapes.add_textbox(left, top, width, height)
text_frame = textbox.text_frame
text_frame.text = "新文本内容"

# 保存
prs.save('/home/xckj/suyuan/backend_data_registry/presentation.pptx')
```

```python
# 添加图片到PPT
from pptx import Presentation
from pptx.util import Inches

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[0])

# 添加图片
pic = slide.shapes.add_picture(
    '/home/xckj/suyuan/backend_data_registry/image.png',
    Inches(1), Inches(1),
    width=Inches(6)
)

prs.save('/home/xckj/suyuan/backend_data_registry/presentation_with_image.pptx')
```

---

## 4. accept_word_changes - 接受修订

**示例**：`accept_word_changes(input_file="[输入文件路径]", output_file="[输出文件路径]")`

---

## 5. 图片处理

**限制**：当前工具无法直接编辑图片

**读取**：解包后查看
unpack_office(path="file.docx") → 图片位于 unpacked/word/media/ 目录 →  、analyze_image(path="image1.png", operation="describe",prompt="[图片分析描述]")
图片读取时间较长，对于多个图片的读取优先并发调用完成。


---

## ⚠️ 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| old_string 未找到 | read_file 返回 markdown，无法匹配 XML | 用 word_edit |
| 未知操作类型 | 操作名称错误 | 用有效类型：replace_text, replace_paragraph, insert_after, insert_before, delete_paragraph |
| 缺少必需参数 | 参数与操作类型不匹配 | 根据操作类型提供正确参数 |
