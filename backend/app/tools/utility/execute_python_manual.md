# execute_python 工具指导手册

助手Agent和社交Agent在使用 `execute_python` 处理复杂计算、Excel、可视化或文件生成前，应先阅读本手册。简单的纯 Python 计算可直接调用。

## 适用场景

- 数据处理：`pandas`、`numpy`、`scipy`。
- Excel 读取、修改和生成：优先使用 `openpyxl`，读取分析可用 `pandas`。
- 图表生成：`matplotlib`，保存图片到 `/home/xckj/suyuan/backend/backend_data_registry/`。
- 报告中间资源生成：图表、表格、结构化 JSON、qmd 草稿片段。
- 一次性 Office 文件生成：仅当用户明确要求 Word/Excel 文件，且不需要 qmd 同源报告包时使用。
- 自定义统计：仅当专用查询/统计工具无法直接满足时使用。

## 正式报告边界

正式报告不要通过 `execute_python` 直接交付 DOCX，也不要在 Python 脚本中手写格式转换流程。

标准流程：

1. 用查询工具和 `execute_python` 完成计算、制图、表格整理。
2. 准备 `report.qmd` 内容，图片最终使用报告包内相对路径，例如 `assets/charts/chart_01.png`。
   不要根据 `/api/image/{image_id}` 或缓存 id 推断这个路径；应把真实图片文件路径传给
   `create_report_package.assets`，必要时用 `name` 指定 `chart_01.png`，由报告包工具复制并规范化引用。
3. 调用 `create_report_package` 保存为 `reports/{report_id}/report.qmd` 并触发右侧面板预览。
4. 用户在右侧面板点击下载 QMD/Word，或点击分享生成报告预览链接。

## 一次性 DOCX 兼容格式

只有用户明确要求一次性 Word 文件，且不需要 qmd 同源报告包时，才直接使用 `python-docx`。此时默认使用公共样式工具，避免每次由模型重新决定字体和段落格式。

```python
from docx import Document
from app.services.report.government_docx_style import (
    apply_government_report_style,
    add_government_title,
    add_government_heading,
    add_government_paragraph,
    add_government_table,
    add_government_image,
    resolve_report_image_path,
)

doc = Document()
apply_government_report_style(doc)
add_government_title(doc, "报告标题")
add_government_heading(doc, "一、总体情况", level=1)
add_government_paragraph(doc, "正文内容。")
add_government_table(doc, [["指标", "数值"], ["PM2.5", "30"]])
doc.save("/home/xckj/suyuan/backend/backend_data_registry/report.docx")
```

默认规范：标题小标宋/宋体 fallback、二号居中；正文仿宋三号、首行缩进2字符、固定28磅行距；一级标题黑体三号，二级标题楷体三号，三级标题仿宋加粗三号；页边距上3.7cm、下3.5cm、左右2.8cm。用户明确要求其他格式时，在默认样式基础上局部覆盖。

### DOCX 图片嵌入

正式报告的 Word 导出由报告 API 处理，一般不需要手写图片嵌入逻辑。只有在直接用 `python-docx` 从零生成一次性 Word 文件时，才需要显式调用图片工具：

```python
from pathlib import Path
from docx import Document
from app.services.report.government_docx_style import (
    apply_government_report_style,
    add_government_image,
)

doc = Document()
apply_government_report_style(doc)
image_path = Path("/home/xckj/suyuan/backend/backend_data_registry/charts/demo.png")
add_government_image(doc, image_path, caption="图1 示例图")

doc.save("/home/xckj/suyuan/backend/backend_data_registry/reports/demo/report.docx")
```

## 文件路径

- 生成文件必须保存到项目可访问目录，优先使用 `/home/xckj/suyuan/backend/backend_data_registry/`。
- 禁止保存到 `/home/xckj/suyuan/backend_data_registry/`，该目录在仓库根目录下，前端下载和后端文件管理不会以它作为标准输出目录。
- 代码中打印中间资源保存路径，便于后续工具传给 `create_report_package`。
- 工具会检测 `/home/xckj/suyuan/backend/backend_data_registry/` 中新增文件。

## 输出产物 Schema

- `files`：本次生成的本地文件绝对路径列表。
- `file_path`：主文件路径，用于预览或下载。
- `pdf_preview`：Office/PDF 文件预览信息，适用于 `.docx/.xlsx/.pptx/.pdf`。
- `visuals`：图片或 ECharts 可视化块；`matplotlib` 图片会缓存为 `/api/image/{image_id}`。

正式报告必须使用标准报告包结构：

```text
/home/xckj/suyuan/backend/backend_data_registry/reports/{report_id}/report.qmd
```

不要直接写成根目录文件或绕过报告包：

```text
/home/xckj/suyuan/backend/backend_data_registry/reports/{report_id}.qmd
```

生成正式报告时，调用 `create_report_package`，不要把本地绝对路径作为最终交付方式。

## matplotlib 中文和化学式

使用无界面后端：

```python
import matplotlib
matplotlib.use("Agg")
```

中文字体推荐直接指定字体文件：

```python
from matplotlib.font_manager import FontProperties
chinese_font = FontProperties(fname="/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc")
```

不要使用 Unicode 下标字符，例如 `O₃`、`PM₂.₅`、`NO₂`，部分字体会显示方框。使用 mathtext：

```python
ax.set_title(r"O$_3$浓度变化", fontproperties=chinese_font)
ax.set_ylabel(r"PM$_{2.5}$ ($\mu$g/m$^3$)", fontproperties=chinese_font)
```

常用写法：`O$_3$`、`NO$_2$`、`SO$_2$`、`PM$_{2.5}$`、`PM$_{10}$`。

## 政府报告图表默认排版

- `execute_python` 会自动注入这套默认模板，常规 `plt.subplots()` 会直接继承更大的画布、字号、网格和导出分辨率。
- 如需进一步收紧某张图，可显式调用 `apply_government_report_style(fig, ax)`。
- `figsize` 建议从 `10x6` 起步，复杂图表可到 `12x7`。
- `savefig(dpi=200)` 或更高，避免导出后文字发虚。
- 标题字号建议 `14-18`，轴标签 `12-14`，刻度 `10-12`，图例 `10-12`。
- 如果同一张图的类别很多，优先旋转 x 轴标签、缩短标签、拆分为横向条形图，而不是继续缩小字体。
- 图表要兼顾印刷和屏幕展示，默认不要把字号压到 10 以下。
- 对长标题、长图例、密集类别，优先使用 `tight_layout()` 或 `constrained_layout=True`。

```python
fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
ax.set_title('图表标题', fontsize=16)
ax.set_xlabel('横轴', fontsize=13)
ax.set_ylabel('纵轴', fontsize=13)
ax.tick_params(axis='both', labelsize=11)
ax.legend(fontsize=11)
save_chart(fig, 'report_chart.png', dpi=200)
```

如果需要二次收紧：
```python
apply_government_report_style(fig, ax)
```

## 图表组织规则

- 默认一张图片只表达一个核心图表或一个分析问题。
- 除非用户明确要求“多子图”“组合图”“仪表盘”“一页多图对比”，不要在单个 Figure 中使用 `subplot`、`subplots` 或多个 `Axes` 拼接多个图表。
- 同一数据源可以支持多个分析视角，但应先选择与用户问题最相关的一张图。
- 确需多个独立图表时，分别保存为多个图片文件，例如 `trend_pm25.png`、`ranking_city.png`，不要合并进单张图片。
- 单个坐标轴中的多条折线、多组柱或多系列散点用于对比是允许的；这属于一个图表，不属于多图拼接。

## Excel 规则

- 修改现有 Excel 时优先用 `openpyxl`，避免 `pandas.to_excel()` 覆盖导致图表和格式丢失。
- 创建新文件可用 `pandas` 或 `openpyxl`。
- 公式优先保留为公式，不要硬编码可计算结果。
- 会商文件合并、图表保留等项目约定，以对应技能文档为准。

## 常见错误

- JSON/数据库读取的数值可能是字符串，计算前显式 `float()` 或 `int()`。
- 字典字段可能缺失，使用 `.get()` 并处理默认值。
- 使用变量前检查 `None`。
- 超时默认 30 秒，复杂任务应拆分或提高 `timeout`。

## 一次性 DOCX 最小示例

```python
from docx import Document
from app.services.report.government_docx_style import apply_government_report_style, add_government_title

out = "/home/xckj/suyuan/backend/backend_data_registry/report.docx"
doc = Document()
apply_government_report_style(doc)
add_government_title(doc, "报告")
doc.save(out)
print(out)
```
