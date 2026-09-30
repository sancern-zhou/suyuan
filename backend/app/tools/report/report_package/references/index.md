# ReportPackage Reference Index

调用 `create_report_package` 前先读取本文件。正式报告收口使用 `create_report_package`；展示型独立 HTML 使用 `create_html_artifact`。

## Required Flow

1. 准备完整 `report.qmd`，包含 YAML front matter 和正文。
2. 图表、图片、表格使用真实本地文件路径传入 `assets`。
3. QMD 中引用报告包内相对路径，例如 `assets/charts/chart_01.png` 或 `assets/table_01.csv`。
4. 调用 `create_report_package` 保存报告包；可指定 `output_formats: ["html", "docx"]`，一次渲染并验收两种导出。程序化定时任务若已生成完整 QMD 文件，可传 `source_qmd_path` 代替 `qmd_content`；真实资源文件仍需列入 `assets`。
5. 检查工具返回的 `report.qmd`、图片引用、HTML 预览和导出产物验收结果；需要独立复验时再调用 `validate_report_package`。

## QMD Rules

- 不写 R 代码块；计算和制图先用 Python 或专用图表工具完成。
- 不在最终 QMD 中使用 `/api/image/{image_id}`、`image_id`、base64 或本地绝对路径。
- 不根据缓存 ID 猜测 `assets/charts/{image_id}.png`；由工具复制真实文件并规范化引用。
- 已支持的专用业务图型必须使用 `create_business_chart`，禁止用 Python/ECharts 重绘替代，此规则优先于模式默认工具；其他静态正式图表优先用 `execute_python`。把工具返回的真实归档图片路径传给 `assets`，已有图片优先复用。
- ECharts 仅在右侧面板展示交互图，不生成报告图片；将问数结果纳入报告时复用原始数据，通过 Python 或业务图表工具重新绘制静态图。
- Python 图表默认一个独立图表一个图片文件，同主题的趋势、分布、排名分别插入并配图注；仅联合阅读确有必要或用户明确要求时合图，业务工具的专用组合布局按其模板处理。
- 绘图阶段即按报告正文宽度设计尺寸、比例和字号，遵循 `execute_python_manual.md` 的报告插图规范。未知模板时按 A4 单栏约 5.8 英寸宽度考虑；插入时保持纵横比，避免将多张独立图排成窄小并列图或拉伸图片。检查最终 HTML/Word 中的标签、图例和标准线是否可读，过小应重新绘制或拆图，提高 DPI 不能代替尺寸调整。

### YAML 目录与编号配置（重要）

Quarto 的 `number-sections: true` 会自动给标题加编号（如 `1.2`、`1.2.1`）。如果 QMD 正文中的标题**已经手动写了编号**（如 `## 1.2 项目立项依据`），会导致双重编号显示为 `1.2 1.2 项目立项依据`。

**Word/DOCX 导出规则**：本项目的 Word 正式稿由 DOCX 后处理统一插入目录并重写 1-3 级标题编号。Agent 生成 QMD 时不要在 `format.docx` 中启用 Quarto 自带目录或章节编号，必须显式写为 `toc: false`、`number-sections: false`，或省略这两个字段。不要在 QMD 正文里手写“目录”页。

推荐 YAML：

```yaml
format:
  html:
    toc: true
    toc-depth: 3
    number-sections: false
  docx:
    toc: false
    number-sections: false
```

**HTML 预览编号规则：二选一，不能同时启用。**

| 方案 | YAML 配置 | 正文标题写法 | 适用场景 |
|------|----------|-------------|----------|
| A（推荐） | `number-sections: false` | `## 1.2 项目立项依据` | 需要自定义编号格式（如中文数字章节 `一、`），或标题已含手动编号 |
| B | `number-sections: true` | `## 项目立项依据`（不写编号） | 标准学术/技术报告，编号格式由 Quarto 统一控制 |

**检查方法**：生成报告后，在右侧预览面板查看 HTML 目录，如出现 `1.2 1.2 xxx` 即说明 HTML 预览发生双重编号，需按方案 A 或 B 修复。Word 下载稿的目录和标题编号以 DOCX 后处理结果为准。

## Assets

`assets` 可传:

- `"/real/path/chart.png"`
- `{"path": "/real/path/chart.png", "type": "image", "name": "chart_01.png"}`
- `{"path": "/real/path/table.csv", "type": "table", "name": "table_01.csv"}`

工具会复制资源到报告包目录，并尽量规范化 QMD 中的图片引用。

## When To Use

- 用户要求正式报告、QMD 报告、Word 下载、HTML 预览或可分享报告时使用。
- 用户只要求演示型网页、deck、dashboard 或视觉展示时使用 `create_html_artifact`。
