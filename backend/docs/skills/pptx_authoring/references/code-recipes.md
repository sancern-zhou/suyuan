# python-pptx 代码配方（code-recipes）

配合 design-rules.md 的令牌使用；所有产出文件必须经 `artifact_path()` 获取路径。

## 0. 初始化与保存

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]          # 空白版式，全手工布局
slide = prs.slides.add_slide(BLANK)

out = artifact_path("许昌市空气质量分析_20261107.pptx")
prs.save(out)
```

## 1. 设计令牌（与 design-rules §3 一致，直接复制）

```python
PRIMARY, PRIMARY_DARK, ACCENT = RGBColor(0x0F,0x76,0x6E), RGBColor(0x13,0x4E,0x4A), RGBColor(0xD9,0x77,0x06)
TEXT_STRONG, TEXT_MUTED = RGBColor(0x1E,0x29,0x3B), RGBColor(0x64,0x74,0x8B)
BG, CARD_BG, BORDER = RGBColor(0xFF,0xFF,0xFF), RGBColor(0xF8,0xFA,0xFC), RGBColor(0xE2,0xE8,0xF0)
AQI = {"优": RGBColor(0x22,0xC5,0x5E), "良": RGBColor(0xEA,0xB3,0x08),
       "轻度": RGBColor(0xF9,0x73,0x16), "中度": RGBColor(0xEF,0x44,0x44),
       "重度": RGBColor(0xA8,0x55,0xF7), "严重": RGBColor(0x7F,0x1D,0x1D)}
FONT = "Noto Sans CJK SC"; FONT_LATIN = "Arial"
MARGIN_X, MARGIN_Y, GUTTER = Inches(0.6), Inches(0.45), Inches(0.15)
```

## 2. 文本（含中文字体关键设置）

python-pptx 的 `font.name` 只设 latin 字体；**中文必须额外写 eastasia 节点**，否则服务器
LibreOffice 渲染与字体检测都会漂移：

```python
from pptx.oxml.ns import qn

def set_font(run, size, bold=False, color=TEXT_STRONG, font=FONT):
    f = run.font
    f.size, f.bold, f.name = Pt(size), bold, FONT_LATIN
    f.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {}); rPr.append(ea)
    ea.set("typeface", font)

def add_text(slide, x, y, w, h, text, size, bold=False, color=TEXT_STRONG,
             align="l", line_spacing=1.2, space_after=6):
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    align_map = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}
    for i, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment, p.line_spacing, p.space_after = align_map[align], line_spacing, Pt(space_after)
        set_font(p.add_run(), size, bold, color)
        p.runs[0].text = line
    return box
```

## 3. 卡片（圆角矩形）

```python
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR

def add_card(slide, x, y, w, h, fill=CARD_BG, line=BORDER, radius=0.08):
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    card.adjustments[0] = radius                    # 圆角幅度
    card.fill.solid(); card.fill.fore_color.rgb = fill
    card.line.color.rgb = line; card.line.width = Pt(0.75)
    card.shadow.inherit = False                     # 关闭默认阴影
    return card

# 指标卡：卡片 + 数值 + 标签
def metric_card(slide, x, y, w, label, value, value_color=PRIMARY):
    card = add_card(slide, x, y, w, Inches(1.35))
    tf = card.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.12)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p1 = tf.paragraphs[0]; r = p1.add_run(); r.text = value
    set_font(r, 30, True, value_color)
    p2 = tf.add_paragraph(); r2 = p2.add_run(); r2.text = label
    set_font(r2, 12, False, TEXT_MUTED)
```

## 4. 原生图表（可编辑，优先于贴图）

```python
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION

def add_line_chart(slide, x, y, w, h, categories, series_map):
    data = CategoryChartData()
    data.categories = categories
    for name, values in series_map.items():
        data.add_series(name, values)
    gframe = slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, x, y, w, h, data)
    chart = gframe.chart
    chart.has_title = False
    chart.font.size = Pt(12); chart.font.name = FONT_LATIN
    if len(series_map) <= 4:
        chart.has_legend = False                    # 少系列直接标线端
    else:
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
    plot = chart.plots[0]
    for s in chart.series:
        s.smooth = False
        s.format.line.color.rgb = PRIMARY; s.format.line.width = Pt(2.25)
    va = chart.value_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = BORDER
    va.format.line.color.rgb = BORDER
    va.tick_labels.font.size = Pt(11); va.tick_labels.font.color.rgb = TEXT_MUTED
    ca = chart.category_axis
    ca.format.line.color.rgb = TEXT_MUTED
    ca.tick_labels.font.size = Pt(11); ca.tick_labels.font.color.rgb = TEXT_MUTED
    return chart

# 只标关键点标签：
point = chart.series[0].points[peak_idx]
point.data_label.has_text_frame = True
point.data_label.text_frame.text = "峰值 182"
set_font(point.data_label.text_frame.paragraphs[0].runs[0], 12, True, ACCENT)
```

柱状图换 `XL_CHART_TYPE.COLUMN_CLUSTERED`，单系列时 `plot.gap_width = 60`；条形图用
`BAR_CLUSTERED`（类别轴反转保持读序自上而下）。

## 5. 表格

```python
def add_table(slide, x, y, w, rows, col_widths, header):
    shape = slide.shapes.add_table(len(rows) + 1, len(header), x, y, w, Inches(0.38 * (len(rows) + 1)))
    table = shape.table
    for i, cw in enumerate(col_widths):             # 列宽必须显式分配
        table.columns[i].width = Inches(cw)
    for c, text in enumerate(header):
        cell = table.cell(0, c)
        cell.fill.solid(); cell.fill.fore_color.rgb = PRIMARY
        p = cell.text_frame.paragraphs[0]; r = p.add_run(); r.text = text
        set_font(r, 12, True, RGBColor(0xFF, 0xFF, 0xFF))
    for ri, row in enumerate(rows, start=1):
        for ci, text in enumerate(row):
            cell = table.cell(ri, ci)
            cell.fill.solid()
            cell.fill.fore_color.rgb = BG if ri % 2 else CARD_BG   # 隔行
            p = cell.text_frame.paragraphs[0]; r = p.add_run(); r.text = str(text)
            set_font(r, 12, False, TEXT_STRONG)
    return table
```

行数 >8 时拆页或改图表（design-rules §4）。

## 6. 图片嵌入（业务图/截图）

```python
from PIL import Image

def add_image_fit(slide, path, x, y, w=None, h=None):
    with Image.open(path) as im:
        iw, ih = im.size
    if w is not None and h is None:
        h = Emu(int(w * ih / iw))
    elif h is not None and w is None:
        w = Emu(int(h * iw / ih))
    return slide.shapes.add_picture(path, x, y, w, h)

# 业务图表（create_business_chart 产物）：
chart = create_business_chart(...)            # 按其契约调用，取返回的 file_path
add_image_fit(slide, chart["file_path"], Inches(0.6), Inches(1.2), w=Inches(6.8))
```

## 7. 页脚与页码

```python
def add_footer(slide, page_no, total, source=None):
    if source:
        add_text(slide, MARGIN_X, Inches(7.05), Inches(9), Inches(0.3),
                 f"数据来源：{source}", 10, color=TEXT_MUTED)
    add_text(slide, Inches(12.2), Inches(7.05), Inches(0.55), Inches(0.3),
             f"{page_no}/{total}", 10, color=TEXT_MUTED, align="r")
```

## 8. 栅格定位辅助

```python
def grid(col, row, colspan=1, rowspan=1, col_w=Inches(0.740), row_h=Inches(0.5)):
    """12 列栅格：col 从 0 起。返回 (x, y, w, h)。"""
    x = MARGIN_X + Emu(int(col * (col_w + GUTTER)))
    y = MARGIN_Y + Emu(int(row * (row_h + GUTTER)))
    return x, y, Emu(int(colspan * col_w + (colspan - 1) * GUTTER)), Emu(int(rowspan * row_h + (rowspan - 1) * GUTTER))
```

## 9. 常见坑

- 元素坐标为负或超出画布会被 QA 判 `shape_out_of_bounds`：所有 x/y/w/h 先在纸上（或栅格表）算好。
- `tf.word_wrap = False` 会让长文本水平溢出，默认必须 True。
- 表格默认样式带主题蓝：必须逐 cell 覆盖填充与字体（§5 已做）。
- 原生图表默认含标题与网格线：显式关闭/设色（§4 已做）。
- 连续两页相同结构会被判 `repeated_layout_pattern`：交替使用版式库。

## 10. OOXML 地雷（PowerPoint 修复风险）

- **堆叠图禁用 outEnd 数据标签**：OOXML 限制 `c:dLblPos` 按分组类型——stacked/percentStacked 只允许
  ctr/inBase/inEnd，`outEnd` 仅 clustered 合法。设错后 LibreOffice 渲染正常，**只有真 PowerPoint
  打不开并触发"修复"**。要高亮单根柱子：用逐点配色（point.format.fill），不要挪标签位置。
- 文本与形状对齐时把文本框 `margin_left/right` 设 0（默认内边距会让文字和形状错位半格）。
- python-pptx 的 chart.series 点级标签见 §4；表格样式覆盖见 §5——两处都是默认样式坑。
