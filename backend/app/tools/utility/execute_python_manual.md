# execute_python 工具指导手册

助手Agent和社交Agent在使用 `execute_python` 处理复杂计算、Excel、可视化或文件生成前，应先阅读本手册。简单的纯 Python 计算可直接调用。

## 适用场景

- 数据处理：`pandas`、`numpy`、`scipy`。
- Excel 读取、修改和生成：优先使用 `openpyxl`，读取分析可用 `pandas`。
- 图表生成：`matplotlib`，保存图片到 `/home/xckj/suyuan/backend/backend_data_registry/`。
- 文档生成：`python-docx`。
- HTML 报告生成：优先使用自动注入的 `save_html_report(report_id, html_content, assets_dir=None)`。
- 自定义统计：仅当专用查询/统计工具无法直接满足时使用。

## DOCX 政府报告默认格式

生成正式报告 DOCX 时，默认使用公共样式工具，避免每次由模型重新决定字体和段落格式：

```python
from docx import Document
from app.services.report.government_docx_style import (
    apply_government_report_style,
    add_government_title,
    add_government_heading,
    add_government_paragraph,
    add_government_table,
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

## 文件路径

- 生成文件必须保存到项目可访问目录，优先使用 `/home/xckj/suyuan/backend/backend_data_registry/`。
- 禁止保存到 `/home/xckj/suyuan/backend_data_registry/`，该目录在仓库根目录下，前端下载和后端文件管理不会以它作为标准输出目录。
- 代码中打印保存路径，便于前端和后续工具定位。
- 工具会检测 `/home/xckj/suyuan/backend/backend_data_registry/` 中新增文件。

## 输出产物 Schema

- `files`：本次生成的本地文件绝对路径列表。
- `file_path`：主文件路径，用于预览或下载。
- `pdf_preview`：Office/PDF 文件预览信息，适用于 `.docx/.xlsx/.pptx/.pdf`。
- `html_preview`：HTML 预览信息；Notebook 使用 `/api/notebook/html/{html_id}`，HTML 报告使用 `/api/reports/{report_id}/html`。
- `visuals`：图片或 ECharts 可视化块；`matplotlib` 图片会缓存为 `/api/image/{image_id}`。

HTML 报告必须使用标准报告包结构：

```text
/home/xckj/suyuan/backend/backend_data_registry/reports/{report_id}/report.html
```

不要直接写成：

```text
/home/xckj/suyuan/backend/backend_data_registry/reports/{report_id}.html
```

推荐写法：

```python
html = "<!doctype html><html><body><h1>报告</h1></body></html>"
result = save_html_report("my_report", html)
print(result["html_preview"]["html_url"])
```

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

## 最小示例

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
