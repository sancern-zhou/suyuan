# python-docx 代码配方（code-recipes）

配合 design-rules.md 使用；产出文件必须经 `artifact_path()` 获取路径。

## 1. 初始化：样式与中文字体（关键）

python-docx 的 `font.name` 只设西文字体；**中文必须额外写 eastasia 节点**，
否则服务器 LibreOffice 渲染与 validate_office 字体检测都会漂移：

```python
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

FONT = "Noto Sans CJK SC"; FONT_LATIN = "Arial"

def apply_cjk_font(style, size, bold=False, color=None):
    style.font.name = FONT_LATIN
    style.font.size = Pt(size)
    style.font.bold = bold
    if color: style.font.color.rgb = RGBColor(*color)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

doc = Document()
# 页面与边距
section = doc.sections[0]
section.top_margin = section.bottom_margin = Cm(2.54)
section.left_margin = section.right_margin = Cm(3.18)

apply_cjk_font(doc.styles["Normal"], 11)
doc.styles["Normal"].paragraph_format.line_spacing = 1.5
for name, size in (("Heading 1", 16), ("Heading 2", 14), ("Heading 3", 12)):
    apply_cjk_font(doc.styles[name], size, bold=True, color=(0x1E, 0x29, 0x3B))
```

## 2. 正文与标题

```python
def heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)   # 使用标准 Heading 样式（QA 依赖）
    return h

def para(doc, text, indent=True):
    p = doc.add_paragraph(text)
    if indent:
        p.paragraph_format.first_line_indent = Pt(22)  # 约 2 字符
    return p
```

## 3. 页码（页脚 PAGE 字段）

```python
def add_page_number(doc):
    footer = doc.sections[0].footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    fld = run._r.makeelement(qn("w:fldSimple"), {qn("w:instr"): "PAGE"})
    run._r.append(fld)
```

## 4. 目录字段（>3 页文档；打开时需更新域）

```python
def add_toc(doc):
    p = doc.add_paragraph()
    run = p.add_run()
    fld = run._r.makeelement(qn("w:fldSimple"),
                             {qn("w:instr"): r'TOC \o "1-3" \h \z \u'})
    run._r.append(fld)
```

注意：目录域在 LibreOffice/Word 打开时按 F9 更新前显示占位；渲染页图中
目录页可能显示为空——这不是 QA 失败项，交付说明中提示用户打开后更新域即可。

## 5. 表格（三线表风格）

```python
from docx.enum.table import WD_TABLE_ALIGNMENT

def add_table(doc, header, rows):
    table = doc.add_table(rows=len(rows) + 1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for c, text in enumerate(header):
        cell = table.rows[0].cells[c]
        cell.text = text
        for r in cell.paragraphs[0].runs:
            r.font.bold = True
    for ri, row in enumerate(rows, start=1):
        for ci, text in enumerate(row):
            table.rows[ri].cells[ci].text = str(text) if text is not None else "—"
    return table
```

## 6. 图片（宽 5.8in，图题在下）

```python
def add_figure(doc, image_path, caption):
    doc.add_picture(image_path, width=Inches(5.8))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap = doc.add_paragraph(caption)
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for r in cap.runs: r.font.size = Pt(10.5)
```

图片路径只能来自工具返回值（create_business_chart 的 file_path 或
read_file 声明过的输入文件），不得自行推断。

## 7. 保存

```python
out = artifact_path("许昌市数据说明_20261107.docx")
doc.save(out)
```

## 8. 常见坑

- `doc.add_heading` 默认样式名即 Heading N——不要手工伪造加粗大字当标题，
  QA 按样式名识别层级。
- 表格默认无边框：必须设 `table.style = "Table Grid"` 或逐 cell 设边框。
- Normal 样式未设 eastasia 字体 → 整篇中文回退宋体，`expected_font_missing`。
- 大量 `add_paragraph` 后行距失控：统一在 Normal 样式上设行距，不要逐段设。

## 9. 表格跨页三件套（长表必设）

跨页表格不设这三项，WPS/Word 里会从行中间断开、次页丢失表头：

```python
from docx.oxml.ns import qn

def table_cross_page(table, title_paragraph=None):
    """表头跨页重复 + 行内不断开 + 表题与表粘连。"""
    for row_index, row in enumerate(table.rows):
        trPr = row._tr.get_or_add_trPr()
        if row_index == 0:
            trPr.append(trPr.makeelement(qn("w:tblHeader"), {}))   # 跨页重复表头
        trPr.append(trPr.makeelement(qn("w:cantSplit"), {}))        # 行内禁止断页
    if title_paragraph is not None:
        title_paragraph.paragraph_format.keep_with_next = True      # 表题不与表分离
```

## 10. TOC 与分节页码纪律

- **TOC 域后必须紧跟一个含分页符的段落**——否则目录和正文同页（TOC 排版第一失败原因）。
- 正文页码从 1 起：TOC 放独立节；正式文档三节编号——封面节无页码 → 前置节罗马数字
  （`w:pgNumType w:fmt="upperRoman" w:start="1"`）→ 正文节阿拉伯数字重新起 1。
- 页码域指令用 `PAGE \* arabic \* MERGEFORMAT`——**\* 后是 `arabic` 不是 `decimal`**
  （decimal 是库的枚举名，不是 Word 域开关；写错会渲染成"1decimal"。WPS 还会忽略 pgNumType 的 fmt，
  所以域指令必须显式写）。

## 11. 空白页防治三规则

- 节末（NEXT_PAGE 分节）前**不要再加**手动分页符——双分页 = 空白页。
- 分页符所在段落应含可见文字（节尾空段+分页是唯一合法例外，如封面后）。
- 连续空段落 ≤3 个；大间距用 `space_before` 造，不用空段落堆。
