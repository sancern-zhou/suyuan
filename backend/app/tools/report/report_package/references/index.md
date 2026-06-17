# ReportPackage Reference Index

调用 `create_report_package` 前先读取本文件。正式报告收口使用 `create_report_package`；展示型独立 HTML 使用 `create_html_artifact`。

## Required Flow

1. 准备完整 `report.qmd`，包含 YAML front matter 和正文。
2. 图表、图片、表格使用真实本地文件路径传入 `assets`。
3. QMD 中引用报告包内相对路径，例如 `assets/charts/chart_01.png` 或 `assets/table_01.csv`。
4. 调用 `create_report_package` 保存报告包并渲染 HTML 预览。
5. 调用 `validate_report_package` 检查 `report.qmd`、图片引用、HTML 预览和导出产物。

## QMD Rules

- 不写 R 代码块；计算和制图先用 Python 或专用图表工具完成。
- 不在最终 QMD 中使用 `/api/image/{image_id}`、`image_id`、base64 或本地绝对路径。
- 不根据缓存 ID 猜测 `assets/charts/{image_id}.png`；由工具复制真实文件并规范化引用。
- 需要静态正式图表时优先用 `create_report_chart`，再把返回的真实文件路径传给 `assets`。

## Assets

`assets` 可传:

- `"/real/path/chart.png"`
- `{"path": "/real/path/chart.png", "type": "image", "name": "chart_01.png"}`
- `{"path": "/real/path/table.csv", "type": "table", "name": "table_01.csv"}`

工具会复制资源到报告包目录，并尽量规范化 QMD 中的图片引用。

## When To Use

- 用户要求正式报告、QMD 报告、Word 下载、HTML 预览或可分享报告时使用。
- 用户只要求演示型网页、deck、dashboard 或视觉展示时使用 `create_html_artifact`。
