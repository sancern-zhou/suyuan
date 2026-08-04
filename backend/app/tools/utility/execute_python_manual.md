# execute_python 工具指导手册

助手Agent和社交Agent在使用 `execute_python` 处理复杂计算、Excel、可视化或文件生成前，应先阅读本手册。简单的纯 Python 计算可直接调用。

## 适用场景

- 数据处理：`pandas`、`numpy`、`scipy`。
- Excel 读取、修改和生成：优先使用 `openpyxl`，读取分析可用 `pandas`。
- 临时图表或调试图片生成：`matplotlib`，保存图片到 `backend/backend_data_registry/`。正式报告静态图表优先使用 `create_report_chart`。
- 报告中间资源生成：图表、表格、结构化 JSON、qmd 草稿片段。
- 一次性 Office 文件生成：仅当用户明确要求 Word/Excel 文件，且不需要 qmd 同源报告包时使用。
- 自定义统计：仅当专用查询/统计工具无法直接满足时使用。

## 正式报告边界

正式报告不要通过 `execute_python` 直接交付 DOCX，也不要在 Python 脚本中手写格式转换流程。

标准流程：

1. 用查询工具和 `execute_python` 完成计算、表格整理；正式报告静态图表用 `create_report_chart` 生成。
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
doc.save("backend/backend_data_registry/report.docx")
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
image_path = Path("backend/backend_data_registry/charts/demo.png")
add_government_image(doc, image_path, caption="图1 示例图")

doc.save("backend/backend_data_registry/reports/demo/report.docx")
```

## 文件路径

- 生成文件必须保存到项目可访问目录，优先使用 `backend/backend_data_registry/`。
- 禁止保存到 `backend_data_registry/`，该目录在仓库根目录下，前端下载和后端文件管理不会以它作为标准输出目录。
- 代码中打印中间资源保存路径，便于后续工具传给 `create_report_package`。
- 工具会检测 `backend/backend_data_registry/` 中新增文件。

## 输出产物 Schema

- `files`：本次生成的本地文件绝对路径列表。
- `file_path`：主文件路径，用于预览或下载。
- `pdf_preview`：Office/PDF 文件预览信息，适用于 `.docx/.xlsx/.pptx/.pdf`。
- `visuals`：图片或 ECharts 可视化块；`matplotlib` 图片会缓存为 `/api/image/{image_id}`。

正式报告必须使用标准报告包结构：

```text
backend/backend_data_registry/reports/{report_id}/report.qmd
```

不要直接写成根目录文件或绕过报告包：

```text
backend/backend_data_registry/reports/{report_id}.qmd
```

生成正式报告时，调用 `create_report_package`，不要把本地绝对路径作为最终交付方式。

## matplotlib 图片保存

`execute_python` 只负责运行代码和捕获图片保存路径，不负责报告图表字体、字号、画布或布局设计。正式报告图表请改用 `create_report_chart`。

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
save_chart(fig, "debug_chart.png")
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

out = "backend/backend_data_registry/report.docx"
doc = Document()
apply_government_report_style(doc)
add_government_title(doc, "报告")
doc.save(out)
print(out)
```
