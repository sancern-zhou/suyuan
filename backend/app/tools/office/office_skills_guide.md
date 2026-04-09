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
PPT → execute_python（使用 python-pptx 库）
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

所有Excel操作请使用 `execute_python` 工具，配合以下库：

**推荐库**：
- **openpyxl** - Excel文件读写（.xlsx格式）
- **pandas** - 数据处理和Excel读写
- **xlsxwriter** - Excel文件写入（支持格式化）

**常用场景**：

```python
# 创建Excel文件
import openpyxl
wb = openpyxl.Workbook()
ws = wb.active
ws.append(['城市', 'AQI', 'PM2.5'])
ws.append(['广州', 85, 45])
wb.save('/home/xckj/suyuan/backend_data_registry/data.xlsx')
```

```python
# 使用pandas读取和处理Excel
import pandas as pd
df = pd.read_excel('/home/xckj/suyuan/backend_data_registry/data.xlsx')
df_filtered = df[df['AQI'] > 100]
df_filtered.to_excel('/home/xckj/suyuan/backend_data_registry/output.xlsx', index=False)
```

```python
# Excel公式重算
import openpyxl
wb = openpyxl.load_workbook('/home/xckj/suyuan/backend_data_registry/data.xlsx')
# openpyxl会自动重算公式
wb.save('/home/xckj/suyuan/backend_data_registry/data.xlsx')
```

---

## 3. PPT 操作说明

所有PPT操作请使用 `execute_python` 工具，配合 **python-pptx** 库：

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